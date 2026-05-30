"""
app/webrtc.py — Direct WebRTC voice endpoint (browser-native, no Twilio)

Architecture
------------
  Browser mic → WebRTC DTLS/SRTP (opus) → RTCPeerConnection (aiortc)
              → PCM frames → Deepgram nova-2 STT
  agent_turn() → Google Neural2-D TTS → MP3 chunks → RTCDataChannel → browser

vs Twilio Media Streams (/phone/stream):
  - No PSTN/SIP — pure browser-to-server WebRTC
  - Lower latency (no Twilio relay hop)
  - WebRTC handles NAT traversal, DTLS encryption, jitter buffer
  - Same agent_turn() / TTS pipeline underneath

Signaling (non-trickle ICE)
----------------------------
  1. Browser creates SDP offer (getUserMedia → RTCPeerConnection.createOffer)
  2. POST /webrtc/offer  { sdp, type, session_id }
  3. Server creates answer, waits for ICE gathering to complete
  4. Returns { pc_id, sdp, type }  (answer with embedded ICE candidates)
  5. Browser calls setRemoteDescription(answer) — connection established

Data channel protocol "agent" (mirrors WebSocket pipeline)
-----------------------------------------------------------
  Server → client (JSON text frames):
    {"type": "transcript", "text": "..."}   — Deepgram STT result
    {"type": "reply",      "text": "..."}   — agent reply text
    {"type": "audio_end"}                   — TTS stream complete
    {"type": "audio_cancelled"}             — TTS interrupted by barge-in
  Server → client (binary frames): MP3 chunks (TTS audio)

  Client → server (JSON text frames):
    {"type": "barge_in"}                    — user interrupts TTS
    {"type": "stop_session"}               — end session

Dependencies
------------
  pip install aiortc>=1.9.0
  apt-get install libsrtp2-dev libopus-dev pkg-config
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Dict, List, Optional

from opentelemetry import trace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional aiortc import — degrades gracefully if not installed
# ---------------------------------------------------------------------------
try:
    import numpy as np
    from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
    _HAS_AIORTC = True
except ImportError:
    _HAS_AIORTC = False
    logger.warning("aiortc not installed — WebRTC endpoint will return 503")


# ---------------------------------------------------------------------------
# Per-connection session state
# ---------------------------------------------------------------------------

class WebRTCSession:
    """All state for one active WebRTC peer connection."""

    def __init__(self, pc_id: str, session_id: str) -> None:
        from .models.state import State
        from .session_store import load_session
        from .turn_state import TurnStateMachine

        self.pc_id = pc_id
        self.session_id = session_id
        self.pc: "RTCPeerConnection" = RTCPeerConnection()
        self.channel = None                    # RTCDataChannel (created by client)
        self.transcript_queue: asyncio.Queue[str] = asyncio.Queue()
        self.tts_cancel = asyncio.Event()
        self.done = asyncio.Event()
        self.fsm = TurnStateMachine(session_id)
        self.state = load_session(session_id) or State(source="webrtc")
        self._tasks: List[asyncio.Task] = []


# In-memory registry — one entry per active peer connection
_peer_connections: Dict[str, WebRTCSession] = {}


# ---------------------------------------------------------------------------
# Audio frame conversion: aiortc → PCM bytes for Deepgram
# ---------------------------------------------------------------------------

def _audio_frame_to_pcm(frame) -> Optional[bytes]:
    """
    Convert an aiortc av.AudioFrame to signed 16-bit mono PCM bytes.

    aiortc delivers opus-decoded frames; format is typically 's16' (packed int16)
    or 'fltp' (float planar).  We normalise to mono int16 for Deepgram linear16.
    """
    try:
        arr = frame.to_ndarray()           # shape (channels, samples) or (samples,)

        if arr.ndim > 1:
            # Multi-channel → average to mono
            arr = arr.mean(axis=0)

        fmt = frame.format.name
        if "fltp" in fmt or "flt" in fmt:
            # Float planar/packed in [-1, 1] → int16
            arr = (arr * 32768.0).clip(-32768, 32767)

        return arr.astype(np.int16).tobytes()

    except Exception as exc:
        logger.debug("PCM conversion error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Audio track → Deepgram STT
# ---------------------------------------------------------------------------

async def _process_audio_track(track: "MediaStreamTrack", session: WebRTCSession) -> None:
    """
    Receive WebRTC audio frames and forward as PCM to Deepgram STT.

    Each is_final transcript is pushed to session.transcript_queue for
    the agent loop to consume.
    """
    from deepgram import DeepgramClient, LiveTranscriptionEvents

    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        logger.error("DEEPGRAM_API_KEY not set — WebRTC STT unavailable")
        return

    client = DeepgramClient(api_key)
    dg_connection = client.listen.asyncwebsocket.v("1")

    async def on_transcript(self, result, **kwargs) -> None:
        try:
            alt = result.channel.alternatives[0]
            text = alt.transcript.strip()
            if result.is_final and text:
                logger.info("webrtc DG: text=%r session=%s", text, session.session_id)
                await session.transcript_queue.put(text)
        except Exception as exc:
            logger.warning("webrtc on_transcript error: %s", exc)

    async def on_speech_started(self, speech_started, **kwargs) -> None:
        if session.fsm.can_barge_in:
            logger.info("webrtc barge_in session=%s", session.session_id)
            session.tts_cancel.set()

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
    dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)

    started = await dg_connection.start({
        "model": "nova-2",
        "language": "en-US",
        "encoding": "linear16",
        "sample_rate": 48000,      # WebRTC standard sample rate
        "endpointing": 150,
        "utterance_end_ms": 1000,
        "punctuate": True,
        "interim_results": True,
        "vad_events": True,
    })

    if not started:
        logger.error("Deepgram failed to start for WebRTC session=%s", session.session_id)
        return

    logger.info("webrtc Deepgram connected session=%s", session.session_id)

    try:
        while not session.done.is_set():
            try:
                frame = await asyncio.wait_for(track.recv(), timeout=1.0)
                pcm = _audio_frame_to_pcm(frame)
                if pcm:
                    await dg_connection.send(pcm)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.debug("audio track ended session=%s: %s", session.session_id, exc)
                break
    finally:
        await dg_connection.finish()


# ---------------------------------------------------------------------------
# TTS → data channel
# ---------------------------------------------------------------------------

async def _tts_to_datachannel(text: str, session: WebRTCSession) -> bool:
    """
    Synthesise *text* via Google Neural2-D and send MP3 chunks over the data channel.
    Returns True if completed normally, False if cancelled (barge-in).
    """
    from .voice import _split_sentences, _tts_bytes

    sentences = _split_sentences(text)
    if not sentences:
        return True

    tasks = [asyncio.create_task(_tts_bytes(s)) for s in sentences]
    cancelled = False

    for task in tasks:
        if session.tts_cancel.is_set():
            for t in tasks:
                if not t.done():
                    t.cancel()
            cancelled = True
            break

        cancel_waiter = asyncio.ensure_future(session.tts_cancel.wait())
        try:
            await asyncio.wait({task, cancel_waiter}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            if not cancel_waiter.done():
                cancel_waiter.cancel()

        if session.tts_cancel.is_set():
            for t in tasks:
                if not t.done():
                    t.cancel()
            cancelled = True
            break

        try:
            audio = task.result()
        except Exception:
            audio = None

        if audio and session.channel:
            chunk_size = 4096
            for i in range(0, len(audio), chunk_size):
                try:
                    session.channel.send(audio[i : i + chunk_size])
                except Exception:
                    cancelled = True
                    break

    return not cancelled


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def _agent_loop(session: WebRTCSession) -> None:
    """Process transcripts → agent_turn() → TTS → data channel."""
    from .agent import agent_turn
    from .session_store import save_session
    from .voice import _clean_reply

    tracer = trace.get_tracer("recruiter-agent")

    while not session.done.is_set():
        try:
            transcript = await asyncio.wait_for(
                session.transcript_queue.get(), timeout=0.5
            )
        except asyncio.TimeoutError:
            continue

        if not session.channel:
            continue

        try:
            with tracer.start_as_current_span("webrtc.turn") as span:
                span.set_attribute("session_id", session.session_id)
                span.set_attribute("transcript_len", len(transcript))
                session.fsm.on_transcript(transcript, span=span)

                try:
                    session.channel.send(
                        json.dumps({"type": "transcript", "text": transcript.strip(".,!?;: ")})
                    )
                except Exception:
                    pass

                with tracer.start_as_current_span("webrtc.agent_turn"):
                    result = agent_turn(session.state, transcript)

                reply = result.get("reply", "")
                session.state = result.get("state", session.state)
                save_session(session.session_id, session.state)
                span.set_attribute("reply_len", len(reply))

            reply_clean = _clean_reply(reply)
            try:
                session.channel.send(json.dumps({"type": "reply", "text": reply_clean}))
            except Exception:
                pass

            session.tts_cancel.clear()
            session.fsm.on_tts_start(span=span)

            with tracer.start_as_current_span("webrtc.tts"):
                completed = await _tts_to_datachannel(reply_clean, session)

            if completed:
                session.fsm.on_tts_end(span=span)
                try:
                    session.channel.send(json.dumps({"type": "audio_end"}))
                except Exception:
                    pass
            else:
                session.fsm.on_barge_in(span=span)
                try:
                    session.channel.send(json.dumps({"type": "audio_cancelled"}))
                except Exception:
                    pass

        except Exception as exc:
            logger.error(
                "webrtc agent_loop error session=%s: %s", session.session_id, exc, exc_info=True
            )

    logger.info("webrtc session_end | %s", json.dumps(session.fsm.summary()))


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

async def _cleanup_session(pc_id: str) -> None:
    session = _peer_connections.pop(pc_id, None)
    if not session:
        return
    session.done.set()
    for task in session._tasks:
        task.cancel()
    try:
        await session.pc.close()
    except Exception:
        pass
    logger.info("webrtc cleanup pc_id=%s session=%s", pc_id, session.session_id)


# ---------------------------------------------------------------------------
# Public handlers (called from server.py)
# ---------------------------------------------------------------------------

async def webrtc_offer_handler(
    offer_sdp: str,
    offer_type: str,
    session_id: str,
) -> Dict:
    """
    Handle a WebRTC SDP offer.

    Full ICE (non-trickle): waits for all ICE candidates to be gathered before
    returning the answer.  Simpler for the client — one round-trip, no trickle
    ICE polling needed.

    Returns {"pc_id": ..., "sdp": ..., "type": "answer"}.
    """
    if not _HAS_AIORTC:
        return {"error": "aiortc not installed — WebRTC unavailable", "status": 503}

    pc_id = uuid.uuid4().hex[:8]
    session = WebRTCSession(pc_id, session_id)
    _peer_connections[pc_id] = session
    pc = session.pc

    # ---- Wire up PC events ----
    @pc.on("datachannel")
    def on_datachannel(channel) -> None:
        session.channel = channel
        logger.info("webrtc datachannel open pc_id=%s", pc_id)

        @channel.on("message")
        def on_message(msg) -> None:
            if isinstance(msg, str):
                try:
                    ctrl = json.loads(msg)
                    if ctrl.get("type") == "barge_in":
                        session.tts_cancel.set()
                    elif ctrl.get("type") == "stop_session":
                        session.done.set()
                except Exception:
                    pass

    @pc.on("track")
    def on_track(track) -> None:
        if track.kind == "audio":
            t = asyncio.ensure_future(_process_audio_track(track, session))
            session._tasks.append(t)
            logger.info("webrtc audio track attached pc_id=%s", pc_id)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        logger.info("webrtc connectionState=%s pc_id=%s", pc.connectionState, pc_id)
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await _cleanup_session(pc_id)

    # ---- SDP negotiation ----
    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type=offer_type))
    answer = await pc.createAnswer()

    # ---- Full ICE: wait for all candidates before returning ----
    ice_complete = asyncio.Event()

    @pc.on("icegatheringstatechange")
    def on_ice_state() -> None:
        if pc.iceGatheringState == "complete":
            ice_complete.set()

    await pc.setLocalDescription(answer)

    # Handle race: may already be complete by the time we set the handler
    if pc.iceGatheringState == "complete":
        ice_complete.set()

    try:
        await asyncio.wait_for(ice_complete.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("webrtc ICE gathering timed out pc_id=%s — proceeding", pc_id)

    # ---- Start agent loop ----
    loop_task = asyncio.ensure_future(_agent_loop(session))
    session._tasks.append(loop_task)

    logger.info("webrtc offer answered pc_id=%s session=%s", pc_id, session_id)

    return {
        "pc_id": pc_id,
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
    }


async def webrtc_cleanup_handler(pc_id: str) -> Dict:
    """Explicit cleanup — client calls DELETE /webrtc/{pc_id} on session end."""
    await _cleanup_session(pc_id)
    return {"status": "closed", "pc_id": pc_id}


def webrtc_active_sessions() -> int:
    """Return count of active peer connections (for /outbound/status)."""
    return len(_peer_connections)
