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
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I | re.S), "instruction_override"),
    (re.compile(r"forget\s+(your\s+)?(previous\s+)?instructions", re.I | re.S), "instruction_override"),
    (re.compile(r"disregard\s+(all\s+)?previous", re.I | re.S), "instruction_override"),
    (re.compile(r"override\s+(your\s+)?instructions", re.I | re.S), "instruction_override"),
    # Role hijack
    (re.compile(r"you\s+are\s+now\s+\w+", re.I), "role_hijack"),
    (re.compile(r"act\s+as\s+(if\s+you\s+are|a|an)\s+\w+", re.I), "role_hijack"),
    (re.compile(r"pretend\s+(you\s+are|to\s+be)", re.I), "role_hijack"),
    (re.compile(r"roleplay\s+as", re.I), "role_hijack"),
    (re.compile(r"from\s+now\s+on\s+(you\s+are|act)", re.I), "role_hijack"),
    # Jailbreak
    (re.compile(r"jailbreak", re.I), "jailbreak"),
    (re.compile(r"\bDAN\b"), "jailbreak"),                          # Do Anything Now
    (re.compile(r"do\s+anything\s+now", re.I), "jailbreak"),
    (re.compile(r"developer\s+mode", re.I), "jailbreak"),
    # System prompt extraction
    (re.compile(r"system\s*prompt", re.I), "system_prompt_extraction"),
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
