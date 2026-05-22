"""
CCA-F D5.2 Anti-Pattern: Vague Confidence Threshold
"Vague confidence instructions causing false positives" — #4 production failure

The exam question: "Your escalation system is triggering too often (or not enough). Why?"
Answer: You used string-based confidence or vague language instead of numeric thresholds.
"""

# ===========================================================================
# ❌ BAD: String-based confidence — causes false positives and inconsistency
# ===========================================================================

# BAD system prompt excerpt:
BAD_SYSTEM_PROMPT = """
When you are not sure about your answer, escalate to human review.
If confidence is low, mark escalate=true.
Use your judgment for when something seems uncertain.
"""

# PROBLEMS:
# 1. "Not sure" is subjective — different runs produce different escalation rates
# 2. "Low confidence" has no definition — is 60% low? 40%? 10%?
# 3. "Seems uncertain" uses sentiment — sentiment-based judgments are unreliable (D5.2 exam fact)
# 4. Result: wildly inconsistent escalation rates across runs

BAD_ESCALATION_LOGIC = """
# In the RCA output:
{
  "confidence": "medium",      # ❌ String — not comparable, not calibrated
  "escalate": "maybe",         # ❌ Not a boolean
  "escalation_reason": "seems unclear"  # ❌ Sentiment
}
"""


# ❌ BAD: Code-level vague check
def bad_should_escalate(confidence_str: str) -> bool:
    """Unpredictable — "medium" sometimes triggers, sometimes doesn't."""
    # This is the anti-pattern: string matching for confidence
    return confidence_str in ("low", "medium", "uncertain", "unclear")
    # Problem: "medium" might mean 0.50 or 0.70 depending on context
    # The model has no stable mapping from words to probabilities


# ===========================================================================
# ✅ GOOD: Numeric thresholds — explicit, consistent, auditable
# ===========================================================================

# GOOD system prompt excerpt:
GOOD_SYSTEM_PROMPT = """
Confidence calibration (USE THESE EXACT THRESHOLDS):
- confidence >= 0.85: Direct evidence available, high certainty
- confidence 0.65-0.84: Strong correlation but some gaps
- confidence < 0.65: Insufficient evidence — set escalate=true REQUIRED

Escalation rules (ALL are required, not optional):
1. confidence < 0.65 → escalate=true, state numeric value in escalation_reason
2. Conflicting evidence from 2+ independent sources → escalate=true
3. Severity=P1 AND confidence < 0.80 → escalate=true (policy requirement)
4. error_type="permission" → escalate=true (agent cannot resolve)
5. Customer explicitly requests escalation → escalate=true (always honor)

DO NOT use sentiment language like "seems uncertain" or "possibly unclear".
Use ONLY numeric comparisons.
"""


# ✅ GOOD: Code-level numeric check
CONFIDENCE_THRESHOLD = 0.65  # single source of truth

def good_should_escalate(rca: dict) -> tuple[bool, str]:
    """
    Deterministic, auditable escalation logic.
    Same input always produces same output.
    """
    confidence = rca.get("confidence", 0.0)
    severity = rca.get("severity", "P4")
    reasons = []

    # Rule 1: Numeric confidence threshold
    if confidence < CONFIDENCE_THRESHOLD:
        reasons.append(f"Confidence {confidence:.2f} < threshold {CONFIDENCE_THRESHOLD}")

    # Rule 2: P1 needs higher confidence
    if severity == "P1" and confidence < 0.80:
        reasons.append(f"P1 severity requires confidence >= 0.80, got {confidence:.2f}")

    # Rule 3: Conflicting evidence (count-based, not sentiment-based)
    evidence = rca.get("evidence", [])
    sources = [e["source"] for e in evidence]
    if len(set(sources)) != len(sources):  # duplicate sources with different facts
        reasons.append("Conflicting evidence from same source detected")

    should = bool(reasons)
    return should, "; ".join(reasons) if reasons else ""


# ===========================================================================
# Exam mental model: D5.2 escalation trigger checklist
# ===========================================================================

ESCALATION_TRIGGERS = {
    # ALWAYS escalate (no exceptions)
    "permission_error": "Agent cannot access required data — human must resolve",
    "customer_requested": "Customer explicitly asked for human review",
    "policy_gap": "Situation not covered by any policy — human judgment needed",

    # CONDITIONAL escalation (use numeric thresholds)
    "low_confidence": lambda conf: conf < 0.65,
    "p1_medium_confidence": lambda conf, sev: sev == "P1" and conf < 0.80,
    "conflicting_sources": lambda sources: len(set(sources)) > len(sources),
}

# EXAM TRAP:
# Q: "Which confidence trigger is correct?"
# A: The one with a numeric comparison (< 0.65), NOT "if confidence is low"
