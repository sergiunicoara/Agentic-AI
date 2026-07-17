"""
app/tts_streaming.py — Shared sentence-parallel TTS streaming core.

Extracted from three near-identical copies in voice.py (browser WebSocket),
phone.py (Twilio Media Streams), and webrtc.py (WebRTC data channel). Each
transport differs in encoding, chunking, and cancel/end signaling — but all
three fire TTS synthesis for every sentence in parallel up front, then
stream audio back in sentence order, racing each task against a `cancel`
event so barge-in aborts instantly even mid-synthesis.

This module owns only that shared algorithm. Synthesis and delivery are
injected as callables so the core has no dependency on WebSocket, Twilio,
or aiortc — which also makes it testable without any of those.
"""

from __future__ import annotations

import asyncio
import re
from typing import Awaitable, Callable, Optional

Synth = Callable[[str], Awaitable[Optional[bytes]]]
Send = Callable[[bytes], Awaitable[None]]

_MD_STRIP = re.compile(r"\*{1,2}([^*]+)\*{1,2}|`([^`]+)`|#{1,6}\s*")


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


async def stream_tts_sentences(
    text: str,
    synth: Synth,
    send: Send,
    cancel: Optional[asyncio.Event] = None,
) -> bool:
    """
    Split *text* into sentences, synthesise all of them in parallel via
    *synth*, then deliver audio in sentence order via *send*. If *cancel*
    fires — including mid-synthesis — outstanding tasks are cancelled and
    the function returns immediately.

    Returns True if the stream completed normally, False if cancelled.
    Callers own transport-specific signaling (audio_end / clear / etc.) —
    this function has no I/O beyond the injected callables.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return True

    tasks = [asyncio.create_task(synth(s)) for s in sentences]
    cancelled = False

    for task in tasks:
        if cancel is None:
            audio = await task
            if audio:
                await send(audio)
            continue

        if cancel.is_set() and not task.done():
            for t in tasks:
                if not t.done():
                    t.cancel()
            cancelled = True
            break

        if not task.done():
            cancel_waiter = asyncio.ensure_future(cancel.wait())
            try:
                await asyncio.wait(
                    {task, cancel_waiter}, return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                if not cancel_waiter.done():
                    cancel_waiter.cancel()

        # A result already in hand is never discarded, even if `cancel`
        # fired concurrently while this task was completing. The naive
        # "check cancel right after the wait" order — present in the
        # original voice.py/phone.py/webrtc.py copies this was extracted
        # from — could silently drop an already-synthesized sentence's
        # audio on barge-in. Checking task.done() first fixes that: only
        # a task that genuinely never finished counts as cancelled.
        if task.done() and not task.cancelled():
            try:
                audio = task.result()
            except Exception:
                audio = None
            if audio:
                await send(audio)

        if cancel.is_set():
            for t in tasks:
                if not t.done():
                    t.cancel()
            cancelled = True
            break

    return not cancelled
