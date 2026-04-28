from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from deepgram import DeepgramClient, LiveTranscriptionEvents
from fastapi import WebSocket, WebSocketDisconnect
from google.cloud import texttospeech
from opentelemetry import trace

from .agent import agent_turn
from .models.state import State
from .session_store import load_session, save_session

logger = logging.getLogger(__name__)

_tts_client = texttospeech.TextToSpeechClient()

_MD_STRIP = re.compile(r"\*{1,2}([^*]+)\*{1,2}|`([^`]+)`|#{1,6}\s*")
_EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0\U000024C2-\U0001F251\U0001F1E0-\U0001F1FF]+",
    re.UNICODE,
)
_TTS_VOICE = texttospeech.VoiceSelectionParams(
    language_code="en-US", name="en-US-Neural2-D"
)
_TTS_AUDIO_CFG = texttospeech.AudioConfig(
    audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=1.05
)


def _strip_markdown(text: str) -> str:
    text = _MD_STRIP.sub(lambda m: m.group(1) or m.group(2) or "", text)
    return text.strip()


def _clean_reply(text: str) -> str:
    """Remove emojis from agent reply before sending to UI / TTS."""
    text = _EMOJI_RE.sub("", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    """Split reply into TTS-sized chunks at sentence/line boundaries."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        clean = _strip_markdown(part).strip()
        if not clean:
            continue
        buf += (" " if buf else "") + clean
        if re.search(r"[.!?]$", buf) or len(buf) > 120:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _get_deepgram_key() -> str:
    return os.environ.get("DEEPGRAM_API_KEY", "").strip()


async def _tts_bytes(text: str) -> bytes | None:
    """Synthesise a single sentence via Google Cloud Neural2-D. Returns MP3 bytes."""
    if not text.strip():
        return None
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _tts_client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=_TTS_VOICE,
                audio_config=_TTS_AUDIO_CFG,
            ),
        )
        return response.audio_content
    except Exception as exc:
        logger.error("TTS error: %s", exc)
        return None


async def _tts_stream(
    text: str, ws: WebSocket, cancel: asyncio.Event | None = None
) -> None:
    """Stream TTS sentence-by-sentence.  Aborts mid-stream if *cancel* is set —
    even while a synthesis task is in-flight — so barge-in is truly instant."""
    sentences = _split_sentences(text)
    if not sentences:
        await ws.send_text(json.dumps({"type": "audio_end"}))
        return

    # Kick off all synthesis tasks in parallel upfront
    tasks = [asyncio.create_task(_tts_bytes(s)) for s in sentences]

    for task in tasks:
        if cancel and cancel.is_set():
            for t in tasks:
                if not t.done():
                    t.cancel()
            break

        if cancel:
            # Wait for this sentence OR a barge-in — whichever comes first
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
                break

            try:
                audio = task.result()
            except Exception:
                audio = None
        else:
            audio = await task

        if audio:
            await ws.send_bytes(audio)

    await ws.send_text(json.dumps({"type": "audio_end"}))


async def voice_handler(ws: WebSocket, session_id: str, sample_rate: int = 48000) -> None:
    """
    Continuous conversation loop.

    Design:
    - One WebSocket = one full session; Deepgram stays open throughout.
    - Each is_final Deepgram transcript triggers an agent turn + TTS automatically.
    - Mic muting during TTS is handled entirely on the frontend (ttsPlaying flag),
      so we don't need is_speaking on the server — removing it eliminates the race
      where a transcript arrives before barge_in resets the flag.
    - Barge-in: stop button → frontend sends barge_in → tts_cancel event set →
      _tts_stream exits immediately (even mid-synthesis) → process() free at once.
    - Press mic again → stop_session → clean shutdown.
    """
    await ws.accept()

    deepgram_key = _get_deepgram_key()
    if not deepgram_key:
        await ws.send_text(json.dumps({"type": "error", "message": "DEEPGRAM_API_KEY not configured"}))
        await ws.close()
        return

    ctx = {"state": load_session(session_id) or State()}
    transcript_queue: asyncio.Queue[str] = asyncio.Queue()
    session_done = asyncio.Event()
    tts_cancel = asyncio.Event()  # set by barge_in to abort the current TTS stream

    deepgram = DeepgramClient(deepgram_key)
    dg_connection = deepgram.listen.asyncwebsocket.v("1")

    async def on_transcript(self, result, **kwargs) -> None:
        try:
            alt = result.channel.alternatives[0]
            transcript = alt.transcript.strip()
            is_final = result.is_final
            speech_final = result.speech_final
            logger.info("DG: is_final=%s speech_final=%s text=%r session=%s",
                        is_final, speech_final, transcript, session_id)
            if is_final and transcript:
                await transcript_queue.put(transcript)
        except Exception as exc:
            logger.warning("on_transcript error: %s", exc)

    async def on_metadata(self, metadata, **kwargs) -> None:
        logger.info("Deepgram connected session=%s metadata=%s", session_id, metadata)

    async def on_speech_started(self, speech_started, **kwargs) -> None:
        logger.info("Deepgram: speech started session=%s", session_id)

    async def on_utterance_end(self, utterance_end, **kwargs) -> None:
        logger.info("Deepgram: utterance end session=%s", session_id)

    async def on_close(self, close, **kwargs) -> None:
        logger.info("Deepgram closed session=%s close=%s", session_id, close)

    async def on_error(self, error, **kwargs) -> None:
        logger.error("Deepgram error: %s session=%s", error, session_id)

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
    dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
    dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
    dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

    logger.info("voice_handler sample_rate=%d session=%s", sample_rate, session_id)
    options = {
        "model": "nova-2",
        "language": "en-US",
        "encoding": "linear16",
        "sample_rate": sample_rate,
        "endpointing": 150,        # ms silence before is_final — lower = faster for short commands
        "utterance_end_ms": 1000,  # force finalize if speech detected but no clear endpoint
        "punctuate": True,
        "interim_results": True,
        "vad_events": True,
    }

    try:
        started = await dg_connection.start(options)
        if not started:
            await ws.send_text(json.dumps({"type": "error", "message": "Deepgram connection failed to start"}))
            await ws.close()
            return

        logger.info("Deepgram SDK connected session=%s", session_id)
        await ws.send_text(json.dumps({"type": "ready"}))

        async def process() -> None:
            tracer = trace.get_tracer("recruiter-agent")
            while not session_done.is_set():
                try:
                    transcript = await asyncio.wait_for(transcript_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                try:
                    display = transcript.strip(".,!?;: ")
                    logger.info("voice turn session=%s text=%r", session_id, display)
                    await ws.send_text(json.dumps({"type": "transcript", "text": display}))

                    with tracer.start_as_current_span("voice.turn") as span:
                        span.set_attribute("session_id", session_id)
                        span.set_attribute("transcript_len", len(transcript))
                        with tracer.start_as_current_span("voice.agent_turn"):
                            result = agent_turn(ctx["state"], transcript)
                        reply = result.get("reply", "")
                        ctx["state"] = result.get("state", ctx["state"])
                        save_session(session_id, ctx["state"])
                        span.set_attribute("reply_len", len(reply))

                    reply = _clean_reply(reply)
                    await ws.send_text(json.dumps({"type": "reply", "text": reply}))

                    tts_cancel.clear()
                    with tracer.start_as_current_span("voice.tts"):
                        await _tts_stream(reply, ws, cancel=tts_cancel)

                except Exception as exc:
                    logger.error("process() turn error session=%s: %s", session_id, exc, exc_info=True)
                    try:
                        await ws.send_text(json.dumps({
                            "type": "reply",
                            "text": f"⚠️ Something went wrong processing your request. Please try again.",
                        }))
                        await ws.send_text(json.dumps({"type": "audio_end"}))
                    except Exception:
                        pass

        proc_task = asyncio.create_task(process())

        chunk_count = 0
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    logger.info("client disconnected after %d chunks session=%s", chunk_count, session_id)
                    break
                if msg.get("bytes"):
                    chunk_count += 1
                    if chunk_count <= 3 or chunk_count % 50 == 0:
                        logger.info("audio chunk #%d size=%d session=%s", chunk_count, len(msg["bytes"]), session_id)
                    await dg_connection.send(msg["bytes"])
                elif msg.get("text"):
                    try:
                        ctrl = json.loads(msg["text"])
                        if ctrl.get("type") == "stop_session":
                            logger.info("stop_session after %d chunks session=%s", chunk_count, session_id)
                            break
                        elif ctrl.get("type") == "barge_in":
                            tts_cancel.set()
                            # Drain transcripts that queued while TTS was playing —
                            # otherwise stale commands (e.g. three "one"s) all fire at once.
                            drained = 0
                            while not transcript_queue.empty():
                                try:
                                    transcript_queue.get_nowait()
                                    drained += 1
                                except asyncio.QueueEmpty:
                                    break
                            logger.info(
                                "barge_in: tts_cancel set, drained %d stale transcripts session=%s",
                                drained, session_id,
                            )
                    except Exception:
                        pass
        except WebSocketDisconnect:
            logger.info("WebSocketDisconnect after %d chunks session=%s", chunk_count, session_id)
        except Exception as exc:
            logger.warning("relay error after %d chunks: %s session=%s", chunk_count, exc, session_id)

        session_done.set()
        await dg_connection.finish()
        try:
            await asyncio.wait_for(proc_task, timeout=30.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        proc_task.cancel()

    except Exception as exc:
        logger.exception("voice_handler error: %s", exc)
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass
    finally:
        try:
            await ws.close(code=1000)
        except Exception:
            pass


async def voice_bench_handler(ws: WebSocket, session_id: str) -> None:
    """Benchmark endpoint — text transcript in, reply + MP3 out."""
    await ws.accept()
    ctx = {"state": load_session(session_id) or State()}

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            transcript = msg.get("transcript", "").strip()
            if not transcript:
                continue

            await ws.send_text(json.dumps({"type": "transcript", "text": transcript}))
            result = agent_turn(ctx["state"], transcript)
            reply = result.get("reply", "")
            ctx["state"] = result.get("state", ctx["state"])
            save_session(session_id, ctx["state"])
            await ws.send_text(json.dumps({"type": "reply", "text": reply}))
            await _tts_stream(reply, ws)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("voice_bench_handler error: %s", exc)
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass
