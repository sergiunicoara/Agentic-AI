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
        # 13-19 digit sequences with optional separators, filtered by a
        # Luhn checksum (see _luhn_valid / moderate_output below) — without
        # it this matched any digit run in that length range, including
        # ordinary order/invoice numbers ("Order #20240115 1234567
        # shipped" was flagged and redacted as a credit card).
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


def _luhn_valid(digits: str) -> bool:
    """Standard Luhn checksum. A real card number always passes; an
    arbitrary same-length digit run (order/invoice/tracking numbers) only
    passes by chance (~1 in 10) — this is the standard, cheap way to cut
    that false-positive rate without needing a real PAN/BIN validator.
    """
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


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
        if label == "credit_card":
            # Only redact (and flag) a candidate that actually passes Luhn —
            # a syntactic match alone (any 13-19 digit run) is not enough;
            # see _luhn_valid's docstring.
            luhn_matched = False

            def _redact_if_luhn_valid(m: re.Match) -> str:
                nonlocal luhn_matched
                digits = re.sub(r"[ \-]", "", m.group(0))
                if _luhn_valid(digits):
                    luhn_matched = True
                    return replacement
                return m.group(0)

            redacted = pattern.sub(_redact_if_luhn_valid, redacted)
            if luhn_matched:
                flags.append(f"pii:{label}")
            continue

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
