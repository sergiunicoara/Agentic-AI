"""
CCA-F D5.1: Conversation Context Preservation
Covers: lost-in-the-middle effect, progressive summarization risks,
transactional fact extraction, token accumulation management.

The most common failure: progressive summarization silently destroys
transactional facts (e.g., "CPU=98% at 14:30 from prometheus").
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
import anthropic

logger = logging.getLogger(__name__)


@dataclass
class TransactionalFact:
    """
    D5.1: Facts that MUST survive summarization.
    These are concrete, verifiable data points — not interpretations.
    """
    key: str            # e.g. "cpu_peak"
    value: str          # e.g. "98%"
    source: str         # e.g. "prometheus"
    timestamp: str      # e.g. "2026-05-21T14:30:00Z"
    must_preserve: bool = True


@dataclass
class ContextState:
    """Running context state for a single investigation session."""
    facts: list[TransactionalFact] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    original_message_count: int = 0
    compaction_count: int = 0


class ContextManager:
    """
    D5.1: Manages context preservation across long agentic sessions.

    Key exam concepts:
    1. "Lost in the middle" — critical info buried in long contexts gets ignored
    2. Progressive summarization loss — each summary loses precision
    3. Transactional facts — specific numbers/timestamps/sources that must survive
    4. Token accumulation — detect and compact before hitting limits
    """

    FACT_EXTRACTION_PROMPT = """Extract all concrete, verifiable facts from these messages.
A fact must have: specific value + source + timestamp (or "unknown").
Examples of facts: "CPU=98% [prometheus, 14:30]", "Error rate 5% [app logs, 14:32]"
NOT facts: "system was slow", "there were errors"

Return JSON: {"facts": [{"key": "...", "value": "...", "source": "...", "timestamp": "..."}]}"""

    SUMMARY_PROMPT = """Summarize these conversation messages into 3-5 sentences.
CRITICAL: You MUST preserve every specific number, metric name, service name,
and timestamp — do NOT paraphrase them. These are transactional facts.
Omit tool call details but keep tool results that contain concrete data."""

    def __init__(self):
        self.client = anthropic.Anthropic()
        self.state = ContextState()

    def compact(self, messages: list[dict], preserve_facts: bool = True) -> list[dict]:
        """
        D5.1: Compact conversation history while preserving transactional facts.
        Returns a shorter messages list safe to continue from.
        """
        if len(messages) < 4:
            return messages  # nothing to compact

        # Step 1: Extract transactional facts BEFORE summarizing
        if preserve_facts:
            self._extract_and_store_facts(messages)

        # Step 2: Summarize the middle of the conversation
        # Keep: first user message (task context) + last 2 exchanges
        first_msg = messages[:1]
        recent_msgs = messages[-4:]  # last 2 exchanges
        middle_msgs = messages[1:-4]

        if not middle_msgs:
            return messages

        summary = self._summarize(middle_msgs)
        self.state.summaries.append(summary)
        self.state.compaction_count += 1

        # Step 3: Inject facts back as a system reminder (so they survive)
        fact_reminder = self._build_fact_reminder()

        compacted = first_msg + [
            {"role": "user", "content": f"[CONTEXT SUMMARY — compaction #{self.state.compaction_count}]\n{summary}\n\n{fact_reminder}"},
        ] + recent_msgs

        logger.info(
            f"Compacted {len(messages)} messages → {len(compacted)} "
            f"(preserved {len(self.state.facts)} transactional facts)"
        )
        return compacted

    def _extract_and_store_facts(self, messages: list[dict]):
        """Extract transactional facts from messages before they get summarized away."""
        text = "\n".join(
            m["content"] if isinstance(m["content"], str)
            else json.dumps(m["content"])
            for m in messages
            if m.get("role") == "assistant"
        )

        if not text.strip():
            return

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                system=self.FACT_EXTRACTION_PROMPT,
                messages=[{"role": "user", "content": text[:4000]}],  # limit input
            )
            raw = next((b.text for b in response.content if hasattr(b, "text")), "{}")
            data = json.loads(raw)
            for f in data.get("facts", []):
                self.state.facts.append(TransactionalFact(**f))
        except Exception as e:
            logger.warning(f"Fact extraction failed: {e} — continuing without")

    def _summarize(self, messages: list[dict]) -> str:
        """Summarize middle messages, preserving transactional facts."""
        text = "\n".join(
            f"[{m['role']}]: {m['content'] if isinstance(m['content'], str) else json.dumps(m['content'])[:500]}"
            for m in messages
        )
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=self.SUMMARY_PROMPT,
            messages=[{"role": "user", "content": text[:4000]}],
        )
        return next((b.text for b in response.content if hasattr(b, "text")), "Summary unavailable")

    def _build_fact_reminder(self) -> str:
        """Format extracted facts as a reminder injected into compacted context."""
        if not self.state.facts:
            return ""
        lines = ["[PRESERVED TRANSACTIONAL FACTS — do not lose these]"]
        for f in self.state.facts:
            lines.append(f"- {f.key}: {f.value} [source: {f.source}, ts: {f.timestamp}]")
        return "\n".join(lines)
