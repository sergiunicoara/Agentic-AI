"""
Layer 5: LLM-as-Judge

Scores a ReviewDisposition against a golden case using three evaluation dimensions:

1. Traceability (0–5): Are all findings grounded in tool output or diff lines?
2. Accuracy (0–5): Did the agent catch the issues present in the golden case?
   Did it avoid hallucinated issues not present in the golden case?
3. Actionability (0–5): Are the findings clear, specific, and directly actionable?

Composite score = average of the three dimensions.
Regression threshold: 4.0/5.0 overall.
"""
import json
import os
import time

import anthropic

_JUDGE_MODEL = os.getenv("EVAL_MODEL", "claude-haiku-4-5-20251001")

_JUDGE_SCHEMA = {
    "name": "evaluation_score",
    "description": "Evaluation scores for a code review disposition against a golden case",
    "input_schema": {
        "type": "object",
        "properties": {
            "traceability": {
                "type": "number",
                "description": "0-5: Every finding has a direct evidence citation from tool output or diff",
            },
            "accuracy": {
                "type": "number",
                "description": "0-5: Correct issues detected, no hallucinated issues added",
            },
            "actionability": {
                "type": "number",
                "description": "0-5: Findings are specific, line-referenced, and directly fixable",
            },
            "composite": {
                "type": "number",
                "description": "Average of the three scores",
            },
            "rationale": {
                "type": "string",
                "description": "One paragraph explaining the scores",
            },
            "missed_findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Issues present in the golden case that the review missed",
            },
            "hallucinated_findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Issues flagged by the review that are NOT in the golden case",
            },
        },
        "required": [
            "traceability", "accuracy", "actionability", "composite",
            "rationale", "missed_findings", "hallucinated_findings"
        ],
    },
}

_JUDGE_SYSTEM = """You are an expert evaluator assessing the quality of an AI code review system.

You will receive:
1. A diff (the code change being reviewed)
2. The golden case (the expected correct review outcome)
3. The actual ReviewDisposition produced by the system

Score the disposition on three dimensions (0–5 each):

TRACEABILITY (0–5):
5 = Every finding has an evidence field quoting tool output or a diff line verbatim
3 = Most findings are traceable, some evidence is vague
1 = Evidence fields are empty or non-specific
0 = No evidence fields present

ACCURACY (0–5):
5 = All issues from the golden case were detected; no hallucinated issues added
4 = Most golden issues detected, 0-1 hallucination
3 = Some golden issues missed OR 2+ hallucinations
1 = Major golden issues missed AND hallucinations present
0 = Completely wrong verdict or no useful findings

ACTIONABILITY (0–5):
5 = All findings reference specific files and lines with clear fix instructions
3 = Most findings are actionable, some are vague
1 = Findings are generic with no specific location or fix
0 = Findings are useless

Respond using the evaluation_score tool.
"""


def judge(diff: str, golden_case: dict, actual_disposition: dict) -> dict:
    """
    Score actual_disposition against golden_case for the given diff.
    Returns the evaluation_score dict.
    """
    client = anthropic.Anthropic()

    user_message = f"""## Diff
```diff
{diff}
```

## Golden Case (Expected Outcome)
```json
{json.dumps(golden_case, indent=2)}
```

## Actual ReviewDisposition
```json
{json.dumps(actual_disposition, indent=2)}
```

Please evaluate the actual disposition against the golden case.
"""

    start = time.monotonic()
    response = client.messages.create(
        model=_JUDGE_MODEL,
        max_tokens=2048,
        system=_JUDGE_SYSTEM,
        tools=[_JUDGE_SCHEMA],
        tool_choice={"type": "tool", "name": "evaluation_score"},
        messages=[{"role": "user", "content": user_message}],
    )
    elapsed = time.monotonic() - start

    for block in response.content:
        if block.type == "tool_use" and block.name == "evaluation_score":
            result = dict(block.input)
            result["judge_model"] = _JUDGE_MODEL
            result["judge_elapsed_ms"] = int(elapsed * 1000)
            return result

    return {
        "traceability": 0.0,
        "accuracy": 0.0,
        "actionability": 0.0,
        "composite": 0.0,
        "rationale": "Judge produced no output.",
        "missed_findings": [],
        "hallucinated_findings": [],
        "judge_model": _JUDGE_MODEL,
        "judge_elapsed_ms": int(elapsed * 1000),
    }
