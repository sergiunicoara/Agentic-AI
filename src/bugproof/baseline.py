"""The fair one-shot baseline agent, and its pinned configuration.

BUGPROOF_AGENT_BRIEF.md section 7 describes baseline.py as an API-driven
script: same model, same tools (read files, run pytest), single prompt,
one attempt, accepts any red test as done. This environment has no
Anthropic API key -- Claude Code itself authenticates via OAuth, not a
key this process can hand to a separate SDK client -- so the literal
"raw HTTP request/response cassette" design in llm.py could not be built
without either spending a different provider's credits (breaking model-
family consistency with the intended Claude-based advanced system) or
asking for a key that wasn't available. See PRIOR_WORK.md / the Phase 2
report for the full discussion; the human explicitly approved the
alternative used for this submission:

Each case's baseline attempt is a real Claude general-purpose agent,
spawned by Claude Code (this project's own coding agent) as an isolated
subagent, model pinned to the same Sonnet family this project runs on,
given the exact prompt below and nothing else. Its workspace contains
only report.md and buggy/ for that case -- physically separate from
fixed/, oracle.yaml, reference_test.py, and any decoy, not merely
withheld by prompt instruction. This is still "the same model family
expected for the advanced system," still one prompt, still one attempt,
still no oracle feedback before the candidate is frozen -- the only
deviation from the brief's literal architecture is that offline replay
means replaying the recorded subagent trajectory (transcript + final
candidate), not re-issuing a raw API call from a cassette file. A judge
verifies the headline numbers by re-running the frozen candidates
through the unmodified Phase 1 evaluator (see eval/run_baseline_replay.py)
-- no LLM call, no API key needed for that part, matching R5.

This module is the durable record of exactly what was run: the prompt is
a module-level constant reused verbatim for all 12 cases (only the
workspace path differs, which is not content about any bug), and
BASELINE_CONFIG records everything about the run that is available to
record. It also happens to be the place a genuine SDK-based
implementation would slot in later, unchanged in shape, if an Anthropic
key becomes available.
"""

from __future__ import annotations

BASELINE_CONFIG = {
    "executor": "claude-code-agent-subagent",
    "subagent_type": "general-purpose",
    "model": "sonnet",  # pinned explicitly on every spawn; Claude Sonnet 5 for this run
    "model_family_note": (
        "Same family as the model authoring this project (Claude Sonnet 5), "
        "chosen for consistency with the intended advanced-system model per "
        "BUGPROOF_AGENT_BRIEF.md's model-consistency requirement, and because "
        "no other provider's key was authorized for this purpose."
    ),
    "temperature": "not configurable at this layer (Claude Code subagent default)",
    "max_output_tokens": "not configurable at this layer (Claude Code subagent default)",
    "reasoning_effort": "not configurable at this layer (Claude Code subagent default)",
    "tools_available_to_subagent": "all (general-purpose subagent default: Read, Write, Edit, Bash, Grep, Glob, ...)",
    "tools_actually_needed": "read files under buggy/, write one test file, run pytest at most once",
    "attempts_per_case": 1,
    "candidates_generated_per_case": 1,
    "oracle_feedback_before_freeze": False,
    "fixed_revision_visible": False,
    "retry_after_evaluation": False,
    "token_usage_available": True,
    "token_usage_note": (
        "Claude Code's Agent tool reports a single subagent_tokens total per "
        "completed subagent (not split into input/output) plus tool_uses and "
        "duration_ms; recorded verbatim in evidence/baseline/usage.json."
    ),
    "cost_available": False,
    "cost_unavailable_reason": (
        "Claude Code's Agent tool does not expose per-subagent dollar cost to "
        "the orchestrating session; not fabricated or estimated from public "
        "per-token pricing, marked unavailable in results.json instead."
    ),
}

# Reused verbatim for every one of the 12 cases. Only the workspace path is
# substituted per case (a filesystem location, not content about any bug) --
# the task description, constraints, and required output format are
# identical every time.
BASELINE_TASK_PROMPT_TEMPLATE = """\
You are a software engineer investigating a bug report against a small
Python repository.

Your working directory is:

    {workspace_path}

It contains exactly two things:
  - report.md   -- a bug report describing observed behavior
  - buggy/      -- the current state of the relevant source code

Do not look for, assume, or reference any files outside this working
directory. There is nothing else relevant to this task anywhere else on
disk.

Your task:

1. Read report.md.
2. Inspect whatever files under buggy/ you need to understand the code
   well enough to reason about the reported behavior.
3. Write ONE new pytest test file named candidate_test.py, saved directly
   in the working directory shown above (as a sibling of report.md and
   buggy/, not inside buggy/). It should reproduce the bug described in
   report.md: it should express the behavior a user would expect based on
   the report, and it should fail against the current code specifically
   because of the reported defect.
4. Do not modify any file under buggy/. Its final state must be byte-for-
   byte what you started with.
5. How this test will actually be executed later: your candidate_test.py
   will be copied into the same directory as the files currently under
   buggy/ (i.e., as a sibling of those modules), and pytest will be run
   from there. Write your imports accordingly -- e.g. `from module_name
   import thing`, not `from buggy.module_name import thing`.
6. You may check your own work by running your test file exactly ONCE
   before finalizing: temporarily copy candidate_test.py into buggy/,
   run it from there with pytest, note whether it failed as expected,
   then remove the temporary copy from buggy/ (buggy/ must be unmodified
   in its final state, per point 4) and keep your real candidate_test.py
   only in the working directory shown above. Do not iterate further
   after this one check -- you will not get another chance, and no
   further feedback will be provided.
7. Also write a short trajectory.md in the working directory (a few
   sentences to a short paragraph) noting: what you read, what you
   concluded about the bug, and, if you ran your test, what happened.
8. Finish your response with your final claim in exactly this format, as
   the last thing you write:

   CLAIM: REPRODUCED
   or
   CLAIM: NOT_REPRODUCED

   followed by one paragraph explaining your reasoning.

This is a one-shot task: you will not receive any feedback on your
candidate, correct or otherwise, and you will not get to revise it after
this response. Produce your best candidate test even if you are not fully
certain it is right.
"""


def render_prompt(workspace_path: str) -> str:
    return BASELINE_TASK_PROMPT_TEMPLATE.format(workspace_path=workspace_path)
