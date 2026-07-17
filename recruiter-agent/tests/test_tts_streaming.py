"""
Characterization tests for app/tts_streaming.py — the sentence-parallel TTS
core shared by voice.py, phone.py, and webrtc.py.

These exercise the extracted algorithm (parallel synthesis, cancel-race,
ordered delivery) with fake synth/send callables — no Deepgram, Google TTS,
WebSocket, Twilio, or aiortc involved. This is the first coverage this
codebase has had on the barge-in path.
"""

from __future__ import annotations

import asyncio

import pytest

from app.tts_streaming import stream_tts_sentences


def _fake_synth(delays: dict[str, float] | None = None):
    """Returns a synth() that yields b"<sentence>" bytes, optionally delayed."""
    delays = delays or {}

    async def synth(sentence: str) -> bytes | None:
        delay = delays.get(sentence, 0)
        if delay:
            await asyncio.sleep(delay)
        return sentence.encode()

    return synth


def _collecting_send():
    """Returns (send, sent_list) — send() appends bytes to sent_list in call order."""
    sent: list[bytes] = []

    async def send(audio: bytes) -> None:
        sent.append(audio)

    return send, sent


@pytest.mark.asyncio
async def test_no_cancel_streams_all_sentences_in_order():
    synth = _fake_synth()
    send, sent = _collecting_send()

    completed = await stream_tts_sentences(
        "First sentence. Second sentence. Third sentence.", synth, send
    )

    assert completed is True
    assert sent == [b"First sentence.", b"Second sentence.", b"Third sentence."]


@pytest.mark.asyncio
async def test_empty_text_completes_with_no_sends():
    synth = _fake_synth()
    send, sent = _collecting_send()

    completed = await stream_tts_sentences("", synth, send)

    assert completed is True
    assert sent == []


@pytest.mark.asyncio
async def test_synth_returning_none_is_skipped_not_sent():
    async def synth(sentence: str) -> bytes | None:
        return None

    send, sent = _collecting_send()

    completed = await stream_tts_sentences("One. Two.", synth, send)

    assert completed is True
    assert sent == []


@pytest.mark.asyncio
async def test_cancel_set_before_start_cancels_immediately():
    synth = _fake_synth(delays={"First.": 1.0, "Second.": 1.0})
    send, sent = _collecting_send()
    cancel = asyncio.Event()
    cancel.set()

    completed = await stream_tts_sentences("First. Second.", synth, send, cancel=cancel)

    assert completed is False
    assert sent == []


@pytest.mark.asyncio
async def test_cancel_mid_synthesis_stops_before_later_sentences():
    """Cancel fires while sentence 1 is still synthesizing — sentence 2
    (which finishes fast) must never be sent, proving barge-in aborts
    even a task already in flight, not just tasks that haven't started."""
    cancel = asyncio.Event()

    async def synth(sentence: str) -> bytes | None:
        if sentence == "Slow first.":
            await asyncio.sleep(0.05)
            cancel.set()
            await asyncio.sleep(0.05)
            return sentence.encode()
        return sentence.encode()

    send, sent = _collecting_send()

    completed = await stream_tts_sentences(
        "Slow first. Fast second.", synth, send, cancel=cancel
    )

    assert completed is False
    assert sent == []


@pytest.mark.asyncio
async def test_cancel_set_during_wait_does_not_discard_already_completed_result():
    """
    Regression test for a race that existed in the original voice.py /
    phone.py / webrtc.py copies this module was extracted from: checking
    `cancel.is_set()` right after `asyncio.wait()` returns — without first
    checking whether `task` itself was the one that completed — could
    silently drop an already-synthesized sentence's audio if `cancel` fired
    concurrently. Fixed here by checking `task.done()` first: a result
    that's already in hand is always sent before the cancellation is
    honored for the *next* sentence.
    """
    cancel = asyncio.Event()

    async def synth(sentence: str) -> bytes | None:
        if sentence == "Second.":
            cancel.set()
        return sentence.encode()

    send, sent = _collecting_send()

    completed = await stream_tts_sentences(
        "First. Second. Third.", synth, send, cancel=cancel
    )

    assert completed is False
    assert sent == [b"First."]  # already-completed result is sent, not dropped


@pytest.mark.asyncio
async def test_all_synthesis_tasks_fire_in_parallel_not_sequentially():
    """Fires N sentences with equal delay — total time should be ~1x delay,
    not Nx, proving tasks are created upfront rather than awaited one at a time."""
    synth = _fake_synth(delays={"A.": 0.05, "B.": 0.05, "C.": 0.05})
    send, sent = _collecting_send()

    start = asyncio.get_event_loop().time()
    await stream_tts_sentences("A. B. C.", synth, send)
    elapsed = asyncio.get_event_loop().time() - start

    assert elapsed < 0.12  # well under 3x0.05=0.15 sequential time
    assert sent == [b"A.", b"B.", b"C."]
