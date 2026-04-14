from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents
from fastapi import WebSocket, WebSocketDisconnect
from google.cloud import texttospeech
from opentelemetry import trace

from .agent import agent_turn
from .models.state import State
from .session_store import load_session, save_session

logger = logging.getLogger(__name__)

_tts_client = texttospeech.TextToSpeechClient()

_MD_STRIP = re.compile(r"\*{1,2}([^*]+)\*{1,2}|`([^`]+)`|#{1,6}\s*")
_TTS_VOICE = texttospeech.VoiceSelectionParams(
    language_code="en-US", name="en-US-Neural2-D"
)
_TTS_AUDIO_CFG = texttospeech.AudioConfig(
    audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=1.05
)


def _strip_markdown(text: str) -> str:
    text = _MD_STRIP.sub(lambda m: m.group(1) or m.group(2) or "", text)
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
    """Synthesise a single sentence via Google Cloud TTS. Returns MP3 bytes."""
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
        logger.error("TTS sentence error: %s", exc)
        return None


async def _tts_stream(text: str, ws: WebSocket) -> None:
    """
    Split reply into sentences, TTS each in parallel, stream MP3 bytes to client.
    """
    sentences = _split_sentences(text)
    if not sentences:
        await ws.send_text(json.dumps({"type": "audio_end"}))
        return

    tasks = [asyncio.create_task(_tts_bytes(s)) for s in sentences]
    for task in tasks:
        audio = await task
        if audio:
            await ws.send_bytes(audio)

    await ws.send_text(json.dumps({"type": "audio_end"}))


async def voice_handler(ws: WebSocket, session_id: str) -> None:
    await ws.accept()

    deepgram_key = _get_deepgram_key()
    if not deepgram_key:
        await ws.send_text(json.dumps({"type": "error", "message": "DEEPGRAM_API_KEY not configured"}))
        await ws.close()
        return

    ctx = {"state": load_session(session_id) or State()}
    transcript_queue: asyncio.Queue[str] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # --- Deepgram SDK setup ---
    deepgram = DeepgramClient(deepgram_key)
    dg_connection = deepgram.listen.asynclive.v("1")

    async def on_transcript(self, result, **kwargs) -> None:
        try:
            alt = result.channel.alternatives[0]
            transcript = alt.transcript.strip()
            is_final = result.is_final
            speech_final = result.speech_final
            logger.info("DG result: is_final=%s speech_final=%s text=%r session=%s",
                        is_final, speech_final, transcript, session_id)
            if is_final and transcript:
                await transcript_queue.put(transcript)
        except Exception as exc:
            logger.warning("on_transcript error: %s", exc)

    async def on_metadata(self, metadata, **kwargs) -> None:
        logger.info("Deepgram connected: session=%s metadata=%s", session_id, metadata)

    async def on_speech_started(self, speech_started, **kwargs) -> None:
        logger.info("Deepgram: speech started session=%s", session_id)

    async def on_utterance_end(self, utterance_end, **kwargs) -> None:
        logger.info("Deepgram: utterance end session=%s", session_id)

    async def on_close(self, close, **kwargs) -> None:
        logger.info("Deepgram connection closed session=%s close=%s", session_id, close)

    async def on_error(self, error, **kwargs) -> None:
        logger.error("Deepgram error: %s session=%s", error, session_id)

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
    dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
    dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
    dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

    options = LiveOptions(
        model="nova-2",
        language="en-US",
        encoding="opus",
        container="webm",
        sample_rate=48000,
        endpointing=500,
        punctuate=True,
        interim_results=True,
        vad_events=True,
    )

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
            while True:
                transcript = await transcript_queue.get()
                logger.info("voice transcript session=%s text=%s", session_id, transcript)
                await ws.send_text(json.dumps({"type": "transcript", "text": transcript}))

                with tracer.start_as_current_span("voice.turn") as span:
                    span.set_attribute("session_id", session_id)
                    span.set_attribute("transcript_len", len(transcript))

                    with tracer.start_as_current_span("voice.agent_turn"):
                        result = agent_turn(ctx["state"], transcript)
                    reply = result.get("reply", "")
                    ctx["state"] = result.get("state", ctx["state"])
                    save_session(session_id, ctx["state"])
                    span.set_attribute("reply_len", len(reply))

                await ws.send_text(json.dumps({"type": "reply", "text": reply}))

                with tracer.start_as_current_span("voice.tts"):
                    await _tts_stream(reply, ws)

        proc_task = asyncio.create_task(process())

        chunk_count = 0
        try:
            async for chunk in ws.iter_bytes():
                chunk_count += 1
                if chunk_count <= 3 or chunk_count % 20 == 0:
                    logger.info("audio chunk #%d size=%d session=%s", chunk_count, len(chunk), session_id)
                await dg_connection.send(chunk)
        except WebSocketDisconnect:
            logger.info("client disconnected after %d chunks session=%s", chunk_count, session_id)
        except Exception as exc:
            logger.warning("relay error after %d chunks: %s", chunk_count, exc)
        finally:
            proc_task.cancel()
            await dg_connection.finish()

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
    """
    Benchmark endpoint — accepts text transcript directly, bypasses Deepgram STT.
    Send: {"transcript": "your message"}
    Receive: {"type": "reply", "text": "..."} then binary MP3 bytes then {"type": "audio_end"}
    """
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
