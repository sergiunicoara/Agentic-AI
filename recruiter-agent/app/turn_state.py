"""
app/turn_state.py — Explicit turn-taking state machine for voice conversations.

States
------
  LISTENING   → mic open, Deepgram active, waiting for user speech
  THINKING    → is_final transcript received, agent_turn() processing
  SPEAKING    → TTS streaming to user (browser WebSocket or Twilio mulaw)
  INTERRUPTED → barge-in detected while SPEAKING; transitions immediately back to LISTENING

Transitions
-----------
  LISTENING   → THINKING    on Deepgram is_final transcript
  THINKING    → SPEAKING    on agent_turn() complete, TTS starting
  SPEAKING    → LISTENING   on TTS stream complete (audio_end / mark received)
  SPEAKING    → INTERRUPTED on barge-in signal; INTERRUPTED → LISTENING in same call

Each transition emits:
  - structured log line with elapsed_ms in the previous phase
  - OTel span attributes on the current span (if passed)

Usage
-----
    fsm = TurnStateMachine(session_id="abc123")

    # In transcript callback:
    fsm.on_transcript(transcript, span=otel_span)

    # Before TTS:
    fsm.on_tts_start(span=otel_span)

    # After TTS completes:
    if tts_was_cancelled:
        fsm.on_barge_in(span=otel_span)
    else:
        fsm.on_tts_end(span=otel_span)

    # Inspect current state:
    if fsm.can_barge_in:
        ...

    # Session summary for logging:
    logger.info("session_end | %s", fsm.summary())
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

from opentelemetry import trace

logger = logging.getLogger(__name__)


class TurnPhase(Enum):
    LISTENING   = "listening"    # waiting for user speech
    THINKING    = "thinking"     # agent processing
    SPEAKING    = "speaking"     # TTS streaming
    INTERRUPTED = "interrupted"  # barge-in mid-speech


class TurnStateMachine:
    """Thread-safe (asyncio) state machine for a single voice session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.phase: TurnPhase = TurnPhase.LISTENING
        self._phase_entered_at: float = time.monotonic()
        self._turn_count: int = 0
        self._interrupted_count: int = 0

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def is_speaking(self) -> bool:
        return self.phase == TurnPhase.SPEAKING

    @property
    def can_barge_in(self) -> bool:
        """True only while SPEAKING — the only state where interruption makes sense."""
        return self.phase == TurnPhase.SPEAKING

    @property
    def is_busy(self) -> bool:
        """True when agent is processing or speaking (not ready for new input)."""
        return self.phase in (TurnPhase.THINKING, TurnPhase.SPEAKING)

    # ------------------------------------------------------------------
    # Core transition
    # ------------------------------------------------------------------

    def transition(
        self,
        new_phase: TurnPhase,
        *,
        transcript: Optional[str] = None,
        span: Optional[trace.Span] = None,
    ) -> None:
        """Move to *new_phase*, emit log + OTel attributes. No-op if already there."""
        if self.phase == new_phase:
            return

        old = self.phase
        elapsed_ms = (time.monotonic() - self._phase_entered_at) * 1000

        if new_phase == TurnPhase.THINKING:
            self._turn_count += 1
        elif new_phase == TurnPhase.INTERRUPTED:
            self._interrupted_count += 1

        self.phase = new_phase
        self._phase_entered_at = time.monotonic()

        logger.info(
            "turn_fsm | session=%s %s→%s elapsed_ms=%.0f turns=%d interrupts=%d%s",
            self.session_id,
            old.value,
            new_phase.value,
            elapsed_ms,
            self._turn_count,
            self._interrupted_count,
            f" transcript={transcript!r}" if transcript else "",
        )

        if span is not None:
            span.set_attribute("turn.phase", new_phase.value)
            span.set_attribute("turn.prev_phase", old.value)
            span.set_attribute("turn.phase_elapsed_ms", round(elapsed_ms))
            span.set_attribute("turn.count", self._turn_count)
            span.set_attribute("turn.interrupts", self._interrupted_count)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def on_transcript(self, transcript: str, span: Optional[trace.Span] = None) -> None:
        """Call when Deepgram fires is_final=True."""
        self.transition(TurnPhase.THINKING, transcript=transcript, span=span)

    def on_tts_start(self, span: Optional[trace.Span] = None) -> None:
        """Call immediately before _tts_stream() / _tts_stream_phone() begins."""
        self.transition(TurnPhase.SPEAKING, span=span)

    def on_tts_end(self, span: Optional[trace.Span] = None) -> None:
        """Call when TTS completes normally (audio_end / mark received)."""
        self.transition(TurnPhase.LISTENING, span=span)

    def on_barge_in(self, span: Optional[trace.Span] = None) -> None:
        """Call when barge-in detected. Handles SPEAKING→INTERRUPTED→LISTENING atomically."""
        if self.can_barge_in:
            self.transition(TurnPhase.INTERRUPTED, span=span)
        self.transition(TurnPhase.LISTENING, span=span)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        return {
            "session_id": self.session_id,
            "phase": self.phase.value,
            "turn_count": self._turn_count,
            "interrupted_count": self._interrupted_count,
            "interrupt_rate": (
                round(self._interrupted_count / self._turn_count, 3)
                if self._turn_count else 0.0
            ),
        }
