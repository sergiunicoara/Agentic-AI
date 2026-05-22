"""
CCA-F D5.1 Anti-Pattern: Progressive Summarization Destroying Transactional Facts
"Progressive summarization destroying transactional facts" — #5 production failure

The exam scenario: "After multiple summarization rounds, your agent's final report
references wrong metrics. What caused this?"
Answer: Progressive summarization silently overwrote precise values with vague prose.
"""

# ===========================================================================
# ❌ BAD: Naive summarization — loses transactional facts
# ===========================================================================

BAD_SUMMARY_PROMPT = """Summarize the conversation so far into a brief paragraph."""

# What happens with this prompt:
# Original: "DB CPU peaked at 98% at 14:30:15 UTC on 2026-05-21 [source: prometheus alert INC-2047]"
# After 1st summary: "The database CPU was very high in the early afternoon"
# After 2nd summary: "There were database performance issues"
# After 3rd summary: "The system experienced problems"
#
# The transactional fact (98%, 14:30:15, prometheus, INC-2047) is GONE.
# The agent now produces an RCA based on "the system experienced problems" — useless.


def bad_compact_messages(messages: list[dict], client) -> list[dict]:
    """
    BAD: Naive compaction — facts evaporate with each round.
    """
    conversation_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages
        if isinstance(m.get('content'), str)
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        # ❌ No instruction to preserve facts
        messages=[{"role": "user", "content": f"Summarize:\n{conversation_text}"}]
    )
    summary = response.content[0].text
    # ❌ Old messages completely replaced — no fact preservation
    return [{"role": "user", "content": summary}]


# ===========================================================================
# ✅ GOOD: Fact-preserving compaction
# ===========================================================================

GOOD_SUMMARY_PROMPT = """Summarize these messages into 3-5 sentences.

CRITICAL RULE: You MUST preserve these verbatim:
- Every specific number or metric (e.g., "98%", "14:30:15 UTC")
- Every service name, error code, or identifier
- Every source name (prometheus, app_logs, runbook-42)
- Every timestamp

You MAY paraphrase: tool calls, intermediate steps, reasoning process.
You MUST NOT paraphrase: concrete data values, measurements, identifiers.

After the summary, output a JSON block:
```facts
{"facts": [{"key": "...", "value": "...", "source": "...", "ts": "..."}]}
```
"""


def good_compact_messages(messages: list[dict], client) -> list[dict]:
    """
    GOOD: Two-phase compaction:
    Phase 1: Extract transactional facts explicitly
    Phase 2: Summarize with facts-preserved instruction
    Phase 3: Inject facts back as a separate reminder block
    """
    import json, re

    conversation_text = "\n".join(
        f"{m['role']}: {m['content'][:500]}" for m in messages
        if isinstance(m.get('content'), str)
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=GOOD_SUMMARY_PROMPT,
        messages=[{"role": "user", "content": conversation_text[:4000]}]
    )
    full_response = response.content[0].text

    # Extract the facts JSON block
    facts = []
    match = re.search(r'```facts\s*(\{.*?\})\s*```', full_response, re.DOTALL)
    if match:
        try:
            facts = json.loads(match.group(1)).get("facts", [])
        except json.JSONDecodeError:
            pass

    # Build fact reminder that will be injected into context
    fact_lines = [f"- {f['key']}: {f['value']} [source: {f.get('source', '?')}, ts: {f.get('ts', '?')}]"
                  for f in facts]
    fact_block = "\n".join(fact_lines) if fact_lines else "No explicit facts extracted"

    # Remove the facts block from the summary text
    summary = re.sub(r'```facts.*?```', '', full_response, flags=re.DOTALL).strip()

    # Return compacted history: original first message + summary + fact reminder + last 2 turns
    first_message = messages[:1]
    last_two = messages[-4:] if len(messages) > 4 else messages

    return first_message + [
        {
            "role": "user",
            "content": (
                f"[CONTEXT SUMMARY]\n{summary}\n\n"
                f"[PRESERVED TRANSACTIONAL FACTS — these must appear in the final report]\n"
                f"{fact_block}"
            )
        }
    ] + last_two


# ===========================================================================
# The "lost in the middle" effect (D5.1 — separate from summarization)
# ===========================================================================

# PROBLEM: In long contexts, Claude pays more attention to the beginning
# and end of the context window than the middle.
# Critical facts buried in turn 15 of a 30-turn conversation get ignored.

# SOLUTION PATTERNS:
# 1. Inject critical facts at the END of each compacted context (above ✅)
# 2. Use the "user" role for fact injections (higher attention than "assistant")
# 3. Keep transactional facts in a separate "facts" structure, not prose

# EXAM MENTAL MODEL:
# Summarization: facts disappear ACROSS compaction rounds (accumulating loss)
# Lost in middle: facts ignored WITHIN a single long context (positional bias)
# Both need different fixes. The exam may ask you to distinguish them.
