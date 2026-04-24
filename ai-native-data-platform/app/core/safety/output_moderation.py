from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ModerationResult:
    safe: bool                          # False → block the response
    flags: list[str] = field(default_factory=list)  # taxonomy codes
    redacted: str | None = None         # sanitized text when PII was found; None if clean or blocked


# ---------------------------------------------------------------------------
# PII patterns — regex-based
# Production replacement: OpenAI moderation API, AWS Comprehend, or a
# dedicated PII detection service.  Regex covers the common cases cheaply.
# ---------------------------------------------------------------------------
_PII: list[tuple[str, re.Pattern[str], str]] = [
    (
        "email",
        re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", re.I),
        "[EMAIL REDACTED]",
    ),
    (
        "phone_us",
        re.compile(r"\b(\+1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b"),
        "[PHONE REDACTED]",
    ),
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[SSN REDACTED]",
    ),
    (
        "credit_card",
        # 13-19 digit sequences with optional separators — Luhn check omitted intentionally
        re.compile(r"\b(?:\d[ \-]?){13,18}\d\b"),
        "[CC REDACTED]",
    ),
    (
        "api_key",
        re.compile(r"\b(sk-|pk-|api[-_]?key\s*[:=]\s*)[A-Za-z0-9_\-]{16,}", re.I),
        "[API_KEY REDACTED]",
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{20,}={0,2}\b", re.I),
        "[TOKEN REDACTED]",
    ),
]


# ---------------------------------------------------------------------------
# Toxicity signals — keyword-based; first match blocks the response.
# Production replacement: OpenAI moderation endpoint, Perspective API.
# ---------------------------------------------------------------------------
_TOXICITY = re.compile(
    r"\b(kill\s+yourself|kys|go\s+die|you\s+should\s+die|i\s+will\s+kill\s+you)\b",
    re.I,
)


def moderate_output(text: str) -> ModerationResult:
    """Scan LLM-generated text for PII and toxicity before returning to the caller.

    Behaviour:
    - Toxicity detected  → safe=False, caller should degrade to unknown=true.
    - PII detected       → safe=True, redacted text returned; caller should
                           substitute redacted for original answer.
    - Clean              → safe=True, no flags, redacted=None.

    Design notes:
    - Two-pass: toxicity checked on original text; PII redacted iteratively.
    - Redaction preserves surrounding text so citations remain useful.
    - Does not raise; always returns a ModerationResult for uniform handling.
    """
    flags: list[str] = []
    redacted = text

    # PII scan — apply all patterns, accumulate flags, redact in place
    for label, pattern, replacement in _PII:
        if pattern.search(redacted):
            flags.append(f"pii:{label}")
            redacted = pattern.sub(replacement, redacted)

    # Toxicity check on the *original* text (not redacted, to avoid masking signals)
    if _TOXICITY.search(text):
        flags.append("toxicity")
        return ModerationResult(safe=False, flags=flags, redacted=None)

    pii_found = any(f.startswith("pii:") for f in flags)
    return ModerationResult(
        safe=True,
        flags=flags,
        redacted=redacted if pii_found else None,
    )
