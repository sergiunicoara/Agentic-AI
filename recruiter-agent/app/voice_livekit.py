"""
app/voice_livekit.py — LiveKit Agents adapter (reference integration)

Shows how the existing deterministic agent_turn() orchestrator plugs into the
LiveKit Agents v0.8+ framework without rewriting business logic.

Why this project uses a custom WebSocket pipeline instead of LiveKit
--------------------------------------------------------------------
  1. Cloud Run + Browser WebSocket — no TURN/media relay server needed.
     LiveKit requires a LiveKit server (or LiveKit Cloud) for WebRTC signalling.

  2. Finer STT control — direct Deepgram WebSocket gives us endpointing=150ms
     and utterance_end_ms=1000 which are not exposed by the LiveKit Deepgram plugin.

  3. Twilio Media Streams integration — PSTN calls use raw WebSocket (mulaw 8 kHz),
     not WebRTC. LiveKit cannot bridge Twilio Media Streams directly.

  4. Simpler ops — one Cloud Run service, no extra LiveKit infra.

When to prefer LiveKit
----------------------
  - Multi-participant rooms (group interviews, panel sessions)
  - Native mobile apps (WebRTC > browser WS for mobile reliability/battery)
  - Existing LiveKit infrastructure already deployed
  - Complex room management (mute, screenshare, participant events)

How to activate this adapter
-----------------------------
  1. pip install livekit-agents livekit-plugins-deepgram livekit-plugins-google
  2. Set env vars: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
  3. Run:  python -m app.voice_livekit dev
     or:   python -m app.voice_livekit start

This module is intentionally NOT imported by server.py so it has zero
runtime cost when using the default WebSocket pipeline.

LiveKit Agents version: v0.8.x (2025)
Docs: https://docs.livekit.io/agents/
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guard: only import LiveKit if installed (optional dependency)
# ---------------------------------------------------------------------------
try:
    from livekit import rtc
    from livekit.agents import (
        AutoSubscribe,
        JobContext,
        WorkerOptions,
        cli,
        llm,
    )
    from livekit.agents.voice_assistant import VoiceAssistant
    from livekit.plugins import deepgram, google, silero
    _HAS_LIVEKIT = True
except ImportError:
    _HAS_LIVEKIT = False
    logger.info("livekit-agents not installed — voice_livekit adapter inactive")


# ---------------------------------------------------------------------------
# Adapter: wraps agent_turn() as a LiveKit LLM plugin
# ---------------------------------------------------------------------------

if _HAS_LIVEKIT:

    class RecruiterAgentLLM(llm.LLM):
        """
        Thin adapter that wraps our deterministic agent_turn() as a LiveKit LLM.

        LiveKit calls chat() with a ChatContext; we extract the last user message,
        call agent_turn(), and yield the reply as a streaming LLMStream.

        State is maintained per-session in _sessions dict (mirrors session_store.py).
        """

        def __init__(self) -> None:
            super().__init__()
            self._sessions: dict = {}

        def _get_state(self, session_id: str):
            from .models.state import State
            from .session_store import load_session
            if session_id not in self._sessions:
                self._sessions[session_id] = load_session(session_id) or State(source="livekit")
            return self._sessions[session_id]

        def _save_state(self, session_id: str, state) -> None:
            from .session_store import save_session
            self._sessions[session_id] = state
            save_session(session_id, state)

        def chat(
            self,
            chat_ctx: "llm.ChatContext",
            fnc_ctx: "llm.FunctionContext | None" = None,
        ) -> "llm.LLMStream":
            return _RecruiterLLMStream(self, chat_ctx)


    class _RecruiterLLMStream(llm.LLMStream):
        """Single-turn stream: calls agent_turn() and yields the reply token-by-token."""

        def __init__(self, lk_llm: RecruiterAgentLLM, chat_ctx: "llm.ChatContext") -> None:
            super().__init__(lk_llm, chat_ctx=chat_ctx, fnc_ctx=None)
            self._lk_llm = lk_llm

        async def _run(self) -> None:
            from .agent import agent_turn
            from .voice import _clean_reply

            # Extract session_id from metadata (set by entrypoint below)
            session_id = getattr(self._chat_ctx, "_session_id", "livekit-default")

            # Get last user message
            user_msg = ""
            for msg in reversed(self._chat_ctx.messages):
                if msg.role == "user" and isinstance(msg.content, str):
                    user_msg = msg.content
                    break

            if not user_msg:
                self._event_ch.send_nowait(
                    llm.ChatChunk(
                        request_id="",
                        choices=[llm.Choice(delta=llm.ChoiceDelta(role="assistant", content=""))],
                    )
                )
                return

            state = self._lk_llm._get_state(session_id)
            result = agent_turn(state, user_msg)
            reply = _clean_reply(result.get("reply", ""))
            new_state = result.get("state", state)
            self._lk_llm._save_state(session_id, new_state)

            # Yield as a single chunk (LiveKit streams word-by-word to TTS plugin)
            self._event_ch.send_nowait(
                llm.ChatChunk(
                    request_id="",
                    choices=[
                        llm.Choice(
                            delta=llm.ChoiceDelta(role="assistant", content=reply)
                        )
                    ],
                )
            )


    # ---------------------------------------------------------------------------
    # LiveKit Agent entrypoint
    # ---------------------------------------------------------------------------

    async def entrypoint(ctx: JobContext) -> None:
        """
        Called by LiveKit Workers when a new job (call) is dispatched.

        Pipeline:
          WebRTC audio → Silero VAD → Deepgram STT → RecruiterAgentLLM → Google TTS
        """
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

        session_id = ctx.room.name or "livekit-default"
        logger.info("LiveKit agent entrypoint room=%s session=%s", ctx.room.name, session_id)

        agent_llm = RecruiterAgentLLM()

        assistant = VoiceAssistant(
            vad=silero.VAD.load(),
            stt=deepgram.STT(
                model="nova-2",
                language="en-US",
                endpointing_ms=150,   # match our WebSocket pipeline tuning
            ),
            llm=agent_llm,
            tts=google.TTS(
                voice_name="en-US-Neural2-D",
                speaking_rate=1.05,
            ),
            # Interrupt sensitivity: mirror our RMS threshold of 0.050
            interrupt_speech_duration=0.5,
            interrupt_min_words=1,
        )

        # Attach session_id to chat context so RecruiterAgentLLM can look up state
        assistant.chat_ctx._session_id = session_id  # type: ignore[attr-defined]

        assistant.start(ctx.room)
        await assistant.say("Welcome! What role are you hiring for?", allow_interruptions=True)

        # Keep the job alive until the room is empty
        await ctx.wait_for_disconnect()
        logger.info("LiveKit session ended room=%s session=%s", ctx.room.name, session_id)


    # ---------------------------------------------------------------------------
    # Entry point for `python -m app.voice_livekit dev/start`
    # ---------------------------------------------------------------------------

    if __name__ == "__main__":
        cli.run_app(
            WorkerOptions(
                entrypoint_fnc=entrypoint,
                # Worker connects to LiveKit server via LIVEKIT_URL env var
            )
        )

else:
    # Graceful no-op when livekit-agents is not installed
    logger.debug("voice_livekit: livekit-agents not available, module is a no-op")
