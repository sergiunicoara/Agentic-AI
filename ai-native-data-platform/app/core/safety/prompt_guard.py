from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardResult:
    safe: bool
    reason: str  # "ok" or a short taxonomy code


# ---------------------------------------------------------------------------
# Injection pattern registry
# Each entry: (compiled regex, taxonomy code)
# Ordered from most to least specific — first match wins.
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Instruction override
    # `(?:\w+\s+){0,3}` absorbs common filler ("the", "all", "any", "prior
    # to this,") between the verb and its object — the previous, exact
    # phrasing (only an optional bare "all ") missed the everyday
    # "ignore THE previous instructions" / "please forget THE previous
    # instructions" variants entirely (verified: they returned safe=True).
    # Bounded to 3 words, so this can't run away on long input.
    (re.compile(r"ignore\s+(?:\w+\s+){0,3}(?:previous|prior)\s+instructions", re.I | re.S), "instruction_override"),
    (re.compile(r"forget\s+(?:\w+\s+){0,3}instructions", re.I | re.S), "instruction_override"),
    (re.compile(r"disregard\s+(?:\w+\s+){0,3}(?:previous|prior)", re.I | re.S), "instruction_override"),
    (re.compile(r"override\s+(?:\w+\s+){0,3}instructions", re.I | re.S), "instruction_override"),
    # Role hijack
    (re.compile(r"you\s+are\s+now\s+\w+", re.I), "role_hijack"),
    # Deliberately narrower than "act as a/an X" (matched below via
    # "if you are"): the bare form flagged completely ordinary requests
    # like "act as a reviewer for this doc" or "act as a proofreader" —
    # asking the assistant to take a professional lens on THIS task, not
    # to discard its instructions. "act as IF you ARE X" is a much more
    # specific "pretend to be a different, unconstrained entity" cue.
    (re.compile(r"act\s+as\s+if\s+you\s+are\s+\w+", re.I), "role_hijack"),
    (re.compile(r"pretend\s+(you\s+are|to\s+be)", re.I), "role_hijack"),
    (re.compile(r"roleplay\s+as", re.I), "role_hijack"),
    (re.compile(r"from\s+now\s+on\s+(you\s+are|act)", re.I), "role_hijack"),
    # Jailbreak
    (re.compile(r"jailbreak", re.I), "jailbreak"),
    (re.compile(r"\bDAN\b"), "jailbreak"),                          # Do Anything Now
    (re.compile(r"do\s+anything\s+now", re.I), "jailbreak"),
    (re.compile(r"developer\s+mode", re.I), "jailbreak"),
    # System prompt extraction
    # Requires an actual extraction verb immediately before "your/the
    # system prompt" — the previous bare `system\s*prompt` flagged any
    # mention at all, including ordinary questions like "how do I
    # configure the system prompt for our bot" or "what system prompt
    # format does OpenAI use", neither of which is an extraction attempt.
    (re.compile(r"(?:what\s+is|what's|show\s+me|reveal|tell\s+me|print|display|output|give\s+me|repeat)\s+(?:your|the)\s+system\s*prompt", re.I), "system_prompt_extraction"),
    (re.compile(r"reveal\s+your\s+(system\s+)?instructions", re.I), "system_prompt_extraction"),
    (re.compile(r"what\s+(are|were)\s+your\s+instructions", re.I), "system_prompt_extraction"),
    (re.compile(r"repeat\s+(everything|all)\s+(above|before)", re.I), "system_prompt_extraction"),
    # Special token injection (model-specific control tokens)
    (re.compile(r"<\|.*?\|>", re.S), "special_token_injection"),
    (re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>"), "special_token_injection"),
    (re.compile(r"###\s*instruction", re.I), "special_token_injection"),
    (re.compile(r"<\s*system\s*>", re.I), "special_token_injection"),
]


def check_query(query: str) -> GuardResult:
    """Scan a user query for prompt injection patterns before it reaches the LLM.

    Returns GuardResult(safe=False, reason=<taxonomy_code>) on first match.
    The caller should reject the request (HTTP 400) without forwarding the query.

    Design notes:
    - Regex-based; production would add an LLM-based classifier as a second pass.
    - First match wins — no scoring; any match is sufficient for rejection.
    - Does not log the flagged query here; the caller should emit an audit event.
    """
    for pattern, reason in _INJECTION_PATTERNS:
        if pattern.search(query):
            return GuardResult(safe=False, reason=reason)
    return GuardResult(safe=True, reason="ok")


def is_safe_context(text: str) -> bool:
    """Return whether retrieved content is safe to include in an LLM prompt.

    Documents are untrusted data, not instructions. Filtering only the high
    confidence injection forms avoids treating ordinary prose as suspicious
    while preventing common direct-instruction payloads from reaching the
    generator.
    """
    high_confidence = {"instruction_override", "system_prompt_extraction", "special_token_injection"}
    result = check_query(text)
    return result.safe or result.reason not in high_confidence
