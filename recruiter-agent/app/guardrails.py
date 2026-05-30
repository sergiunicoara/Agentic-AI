"""
app/guardrails.py — PII redaction + topic enforcement.

PII redaction:   strips phone numbers, emails, credit card numbers, and SSNs
                 from text before writing to logs/traces.
                 Applied AFTER the agent processes the message (so the LLM sees
                 the full context), only on the logging path.

Topic enforcement: checks whether an incoming message is recruiting-related.
                   Off-topic messages receive a polite deflection before
                   ever reaching agent_turn().
"""
from __future__ import annotations

import re
from typing import Tuple

# ── PII patterns ──────────────────────────────────────────────────────────────
# Ordered most-specific → least-specific to avoid partial replacement

_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Email — must come before the generic phone pattern so "user@host" isn't mangled
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    # US SSN: 123-45-6789
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    # Credit card: 16 digits optionally separated by spaces/dashes in groups of 4
    (re.compile(r"\b(?:\d[ \-]?){15,16}\b"), "[CARD]"),
    # International / local phone: +1 555 123 4567, (555) 123-4567, 555.123.4567
    (re.compile(r"(\+?\(?\d[\d\s\-\.\(\)]{7,}\d)"), "[PHONE]"),
]


def redact_pii(text: str) -> str:
    """Replace PII tokens with safe placeholder labels.

    Designed for log/trace sanitisation — do NOT redact the message that
    goes to the LLM, only the copy that gets written to Langfuse/OTel.
    """
    for pattern, placeholder in _PII_PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


# ── Topic enforcement ──────────────────────────────────────────────────────────

_RECRUITING_KEYWORDS = [
    "hire", "hiring", "role", "engineer", "developer", "scientist",
    "candidate", "job", "position", "experience", "skill", "skills", "project",
    "resume", "cv", "portfolio", "ats", "criteria", "leadership",
    "certification", "certifications", "education", "salary", "interview",
    "recruiter", "recruitment", "work", "career", "team", "startup", "company",
    "llm", "ml", "ai", "voice", "speech", "stt", "tts", "rag",
    "another", "next", "summary", "reset", "help", "menu",
    "deepgram", "gemini", "openai", "python", "fastapi", "cloud",
    "sergiu", "background", "tech stack",
]

_OFF_TOPIC_PATTERNS = [
    # Code generation / homework
    r"\b(write|generate|create|code)\b.{0,20}\b(code|program|script|function|class|algorithm|sql|query)\b",
    r"\b(solve|fix|debug|implement)\b.{0,20}\b(code|bug|error|problem|issue)\b",
    # Politics / current events
    r"\b(election|president|politics|politician|government|war|conflict|nato|military)\b",
    r"\b(stock|stocks|crypto|bitcoin|ethereum|invest|trading)\b",
    r"\b(news|headline|breaking|journal)\b",
    # Personal chit-chat
    r"\b(what is your name|who are you|are you (an? )?(human|robot|ai|bot))\b",
    r"\b(tell me a joke|joke|funny|laugh|meme)\b",
    r"\b(weather|forecast|temperature|celsius|fahrenheit)\b",
    r"\b(recipe|cooking|cook|food|restaurant|dinner|lunch)\b",
    r"\b(movie|film|tv show|series|netflix|spotify)\b",
    r"\b(game|gaming|xbox|playstation|steam)\b",
]

_OFF_TOPIC_RE = re.compile("|".join(_OFF_TOPIC_PATTERNS), re.IGNORECASE)

_DEFLECTION = (
    "I'm Sergiu's AI recruiter assistant, focused on helping you evaluate his profile. "
    "Could we get back to the hiring conversation? "
    "Feel free to ask about his skills, projects, certifications, or request an ATS summary."
)


def check_topic(message: str) -> Tuple[bool, str]:
    """
    Returns (is_on_topic, deflection_reply).

    is_on_topic=True  → proceed normally, deflection_reply is empty.
    is_on_topic=False → return deflection_reply directly to the user.

    Short messages (≤20 chars) are always allowed — they're almost certainly
    voice commands like "1", "next", "ats", "reset".
    """
    msg = message.strip()

    # Always allow short commands
    if len(msg) <= 20:
        return True, ""

    # Hard off-topic pattern match
    if _OFF_TOPIC_RE.search(msg):
        return False, _DEFLECTION

    # For longer messages (>8 words): require at least one recruiting keyword
    if len(msg.split()) > 8:
        low = msg.lower()
        if not any(kw in low for kw in _RECRUITING_KEYWORDS):
            return False, _DEFLECTION

    return True, ""
