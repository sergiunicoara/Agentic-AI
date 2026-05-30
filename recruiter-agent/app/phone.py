"""
app/phone.py — Twilio Media Streams telephony bridge (PSTN/SIP → voice agent)

Architecture
------------
  PSTN call → Twilio SIP trunk → Twilio Media Streams WebSocket
  inbound:  mulaw 8 kHz (base64-encoded JSON frames) → Deepgram nova-2 (native mulaw)
  outbound: agent_turn() → Google Neural2-D TTS (MULAW 8 kHz) → Twilio WebSocket

No transcoding required: Deepgram accepts mulaw 8 kHz natively; Google TTS emits
mulaw 8 kHz when AudioEncoding.MULAW + sample_rate_hertz=8000 are configured.

Endpoints
---------
  POST /phone/twiml   — Twilio calls this when a call is received.
                        Returns TwiML that directs Twilio to connect to /phone/stream.
  WS   /phone/stream  — Twilio Media Streams WebSocket.
                        Receives mulaw audio, streams back TTS responses.

Barge-in
--------
  Deepgram SpeechStarted fires while FSM is in SPEAKING →
    1. tts_cancel event is set → _tts_stream_phone() exits mid-synthesis
    2. {"event": "clear", "streamSid": ...} flushes Twilio's audio buffer
    3. FSM transitions SPEAKING → INTERRUPTED → LISTENING

Twilio Media Streams protocol
------------------------------
  Inbound  {"event": "connected" | "start" | "media" | "stop"}
  Outbound {"event": "media",  "streamSid": "...", "media": {"payload": "<b64 mulaw>"}}
  Outbound {"event": "clear",  "streamSid": "..."}   ← flush buffer (barge-in)
  Outbound {"event": "mark",   "streamSid": "...", "mark": {"name": "..."}}

Env vars
--------
  DEEPGRAM_API_KEY        — required
  PUBLIC_URL              — optional override for the WebSocket URL in TwiML
                            (e.g. "https://recruiter-agent-xxxx.run.app")
                            Falls back to request Host header.
  TWILIO_AUTH_TOKEN       — optional; enables Twilio webhook signature validation
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import Optional

from deepgram import DeepgramClient, LiveTranscriptionEvents
from fastapi import Request, WebSocket, WebSocketDisconnect
from google.cloud import texttospeech
from opentelemetry import trace

from .agent import agent_turn
from .models.state import State
from .session_store import load_session, save_session
from .turn_state import TurnStateMachine
from .voice import _clean_reply, _split_sentences

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTS — mulaw 8 kHz for Twilio
# ---------------------------------------------------------------------------

_tts_client = texttospeech.TextToSpeechClient()

_TTS_VOICE = texttospeech.VoiceSelectionParams(
    language_code="en-US",
    name="en-US-Neural2-D",
)
_TTS_CFG_PHONE = texttospeech.AudioConfig(
    # MULAW 8 kHz: directly playable by Twilio without any client-side decoding
    audio_encoding=texttospeech.AudioEncoding.MULAW,
    sample_rate_hertz=8000,
    speaking_rate=1.0,  # slightly slower than browser (phone audio quality)
)

# Twilio audio chunk size: 400 ms of mulaw @ 8 kHz = 3 200 bytes
_TWILIO_CHUNK_BYTES = 3200


async def _tts_bytes_phone(text: str) -> Optional[bytes]:
    """Synthesise a single sentence as raw mulaw 8 kHz bytes."""
    if not text.strip():
        return None
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _tts_client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=_TTS_VOICE,
                audio_config=_TTS_CFG_PHONE,
            ),
        )
        return response.audio_content
    except Exception as exc:
        logger.error("TTS phone error: %s", exc)
        return None


async def _tts_stream_phone(
    text: str,
    ws: WebSocket,
    stream_sid: str,
    cancel: Optional[asyncio.Event] = None,
) -> bool:
    """
    Synthesise *text* sentence-by-sentence and stream mulaw chunks to Twilio.

    Returns True if the stream completed normally, False if cancelled (barge-in).
    Sends a Twilio 'clear' event on cancellation to flush their audio buffer.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return True

    # Kick off all synthesis tasks in parallel (same pattern as browser TTS)
    tasks = [asyncio.create_task(_tts_bytes_phone(s)) for s in sentences]
    cancelled = False

    for task in tasks:
        if cancel and cancel.is_set():
            for t in tasks:
                if not t.done():
                    t.cancel()
            cancelled = True
            break

        if cancel:
            cancel_waiter = asyncio.ensure_future(cancel.wait())
            try:
                done, _ = await asyncio.wait(
                    {task, cancel_waiter},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not cancel_waiter.done():
                    cancel_waiter.cancel()

            if cancel.is_set():
                for t in tasks:
                    if not t.done():
                        t.cancel()
                cancelled = True
                break

            try:
                audio = task.result()
            except Exception:
                audio = None
        else:
            audio = await task

        if audio:
            # Send in ~400 ms chunks so Twilio doesn't buffer the whole response
            for i in range(0, len(audio), _TWILIO_CHUNK_BYTES):
                chunk = audio[i : i + _TWILIO_CHUNK_BYTES]
                await ws.send_text(
                    json.dumps(
                        {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": base64.b64encode(chunk).decode()},
                        }
                    )
                )

    if cancelled:
        # Flush Twilio's audio buffer so the user doesn't hear the tail end
        try:
            await ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
        except Exception:
            pass
        return False

    return True


# ---------------------------------------------------------------------------
# TwiML webhook
# ---------------------------------------------------------------------------

async def phone_twiml_handler(request: Request) -> str:
    """
    Return TwiML that instructs Twilio to connect to our Media Streams WebSocket.

    Twilio calls this URL when an inbound call arrives (configure in Twilio console
    under Phone Numbers → Voice → A CALL COMES IN → Webhook).

    The session_id is derived from the CallSid so it matches the stream handler.
    PUBLIC_URL env var (or request Host) determines the wss:// URL.
    """
    public_url = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not public_url:
        host = request.headers.get("host", "localhost")
        # Twilio always calls over HTTPS, so our stream must be wss://
        public_url = f"https://{host}"

    # Twilio will set streamSid and callSid in the "start" event; we use callSid
    # as session_id so HTTP /chat and /phone/stream share the same SQLite session.
    stream_url = f"{public_url.replace('https://', 'wss://').replace('http://', 'ws://')}/phone/stream"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        "  <Connect>\n"
        f'    <Stream url="{stream_url}" />\n'
        "  </Connect>\n"
        "</Response>"
    )
    return xml


# ---------------------------------------------------------------------------
# Twilio Media Streams WebSocket handler
# ---------------------------------------------------------------------------

async def phone_stream_handler(ws: WebSocket, session_id: str = "phone-default") -> None:
    """
    Full-duplex voice loop over Twilio Media Streams.

    The handler:
    1. Waits for Twilio "start" event to get the real streamSid / callSid.
    2. Connects Deepgram with mulaw 8 kHz encoding (no transcoding needed).
    3. Sends an opening greeting via TTS.
    4. Runs the agent conversation loop: transcript → agent_turn() → TTS → Twilio.
    5. Cleans up on "stop" event or WebSocket disconnect.
    """
    await ws.accept()

    deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not deepgram_key:
        logger.error("DEEPGRAM_API_KEY not configured — rejecting phone call")
        await ws.close(code=1011)
        return

    tracer = trace.get_tracer("recruiter-agent")

    # Mutable ref so both coroutines share stream_sid without closure issues
    ref: dict = {"stream_sid": None, "call_sid": None}
    stream_started = asyncio.Event()  # set when Twilio "start" event received

    ctx = {"state": load_session(session_id) or State(source="phone")}
    fsm = TurnStateMachine(session_id)
    tts_cancel = asyncio.Event()
    transcript_queue: asyncio.Queue[str] = asyncio.Queue()
    session_done = asyncio.Event()

    # ------------------------------------------------------------------
    # Deepgram setup — mulaw 8 kHz, same tuning as browser pipeline
    # ------------------------------------------------------------------
    deepgram = DeepgramClient(deepgram_key)
    dg_connection = deepgram.listen.asyncwebsocket.v("1")

    async def on_transcript(self, result, **kwargs) -> None:
        try:
            alt = result.channel.alternatives[0]
            transcript = alt.transcript.strip()
            if result.is_final and transcript:
                logger.info(
                    "phone DG: is_final text=%r session=%s", transcript, session_id
                )
                await transcript_queue.put(transcript)
        except Exception as exc:
            logger.warning("on_transcript error: %s", exc)

    async def on_speech_started(self, speech_started, **kwargs) -> None:
        """Barge-in: user started speaking while agent is TTS-ing."""
        if fsm.can_barge_in:
            logger.info("phone barge_in detected session=%s", session_id)
            tts_cancel.set()
            # Flush Twilio's audio buffer immediately (clear event sent by _tts_stream_phone)

    async def on_utterance_end(self, utterance_end, **kwargs) -> None:
        logger.info("phone utterance_end session=%s", session_id)

    async def on_close(self, close, **kwargs) -> None:
        logger.info("phone Deepgram closed session=%s", session_id)

    async def on_error(self, error, **kwargs) -> None:
        logger.error("phone Deepgram error session=%s: %s", session_id, error)

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
    dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
    dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

    dg_options = {
        "model": "nova-2",
        "language": "en-US",
        "encoding": "mulaw",        # Twilio sends mulaw — no transcoding needed
        "sample_rate": 8000,        # Twilio Media Streams: 8 kHz
        "endpointing": 150,         # ms silence before is_final
        "utterance_end_ms": 1000,
        "punctuate": True,
        "interim_results": True,
        "vad_events": True,
    }

    try:
        started = await dg_connection.start(dg_options)
        if not started:
            logger.error("Deepgram failed to start for phone session=%s", session_id)
            await ws.close(code=1011)
            return

        logger.info("phone_stream_handler ready session=%s", session_id)

        # ------------------------------------------------------------------
        # Agent process loop
        # ------------------------------------------------------------------
        async def process() -> None:
            # Wait until Twilio sends "start" (gives us stream_sid + call metadata)
            try:
                await asyncio.wait_for(stream_started.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("phone: timed out waiting for Twilio start event session=%s", session_id)
                return

            stream_sid = ref["stream_sid"]
            if not stream_sid:
                return

            # ---- Opening greeting ----
            with tracer.start_as_current_span("phone.greeting") as span:
                greeting = agent_turn(ctx["state"], "recruiter_auto_start")
                ctx["state"] = greeting.get("state", ctx["state"])
                reply_text = _clean_reply(greeting.get("reply", ""))
                save_session(session_id, ctx["state"])
                span.set_attribute("session_id", session_id)

            tts_cancel.clear()
            fsm.on_tts_start()
            completed = await _tts_stream_phone(reply_text, ws, stream_sid, tts_cancel)
            if completed:
                fsm.on_tts_end()
            else:
                fsm.on_barge_in()

            # ---- Conversation loop ----
            while not session_done.is_set():
                try:
                    transcript = await asyncio.wait_for(
                        transcript_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    display = transcript.strip(".,!?;: ")
                    logger.info("phone turn session=%s text=%r", session_id, display)

                    with tracer.start_as_current_span("phone.turn") as span:
                        span.set_attribute("session_id", session_id)
                        span.set_attribute("transcript_len", len(transcript))
                        fsm.on_transcript(transcript, span=span)

                        with tracer.start_as_current_span("phone.agent_turn"):
                            result = agent_turn(ctx["state"], transcript)

                        reply_text = result.get("reply", "")
                        ctx["state"] = result.get("state", ctx["state"])
                        save_session(session_id, ctx["state"])
                        span.set_attribute("reply_len", len(reply_text))

                    reply_text = _clean_reply(reply_text)

                    # Drain stacked transcripts — keep only freshest
                    stacked = 0
                    while transcript_queue.qsize() > 1:
                        try:
                            transcript_queue.get_nowait()
                            stacked += 1
                        except asyncio.QueueEmpty:
                            break
                    if stacked:
                        logger.info(
                            "phone: dropped %d stacked transcripts session=%s",
                            stacked,
                            session_id,
                        )

                    tts_cancel.clear()
                    fsm.on_tts_start()
                    # stream_sid may have been updated; re-read from ref
                    current_sid = ref["stream_sid"] or stream_sid
                    with tracer.start_as_current_span("phone.tts"):
                        completed = await _tts_stream_phone(
                            reply_text, ws, current_sid, tts_cancel
                        )
                    if completed:
                        fsm.on_tts_end()
                    else:
                        fsm.on_barge_in()

                except Exception as exc:
                    logger.error(
                        "phone process() error session=%s: %s", session_id, exc, exc_info=True
                    )

            logger.info("phone session_end | %s", json.dumps(fsm.summary()))

        proc_task = asyncio.create_task(process())

        # ------------------------------------------------------------------
        # Twilio Media Streams relay loop
        # ------------------------------------------------------------------
        chunk_count = 0
        try:
            while True:
                raw = await ws.receive_text()
                data = json.loads(raw)
                event = data.get("event")

                if event == "connected":
                    logger.info("phone: Twilio connected session=%s", session_id)

                elif event == "start":
                    start_data = data.get("start", {})
                    ref["stream_sid"] = start_data.get("streamSid")
                    ref["call_sid"] = start_data.get("callSid")
                    # Use callSid as session_id so it's stable for the whole call
                    if ref["call_sid"]:
                        session_id = ref["call_sid"]
                        ctx["state"] = load_session(session_id) or ctx["state"]
                        fsm.session_id = session_id
                    logger.info(
                        "phone: stream started streamSid=%s callSid=%s",
                        ref["stream_sid"],
                        ref["call_sid"],
                    )
                    stream_started.set()

                elif event == "media":
                    payload = data.get("media", {}).get("payload", "")
                    if payload:
                        chunk_count += 1
                        audio_bytes = base64.b64decode(payload)
                        await dg_connection.send(audio_bytes)

                elif event == "stop":
                    logger.info(
                        "phone: Twilio stop after %d chunks session=%s",
                        chunk_count,
                        session_id,
                    )
                    break

        except WebSocketDisconnect:
            logger.info(
                "phone: WebSocketDisconnect after %d chunks session=%s",
                chunk_count,
                session_id,
            )
        except Exception as exc:
            logger.warning(
                "phone: relay error after %d chunks session=%s: %s",
                chunk_count,
                session_id,
                exc,
            )

        session_done.set()
        await dg_connection.finish()
        try:
            await asyncio.wait_for(proc_task, timeout=30.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        proc_task.cancel()

    except Exception as exc:
        logger.exception("phone_stream_handler error: %s", exc)
        try:
            await ws.close(code=1011)
        except Exception:
            pass
    finally:
        try:
            await ws.close(code=1000)
        except Exception:
            pass
