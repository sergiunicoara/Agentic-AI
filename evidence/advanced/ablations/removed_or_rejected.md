# Mechanisms deliberately not built

The Phase 3 brief forbids building, ahead of evidence: a multi-agent
reviewer, retrieval augmentation, a vector DB, general framework
orchestration, multiple-candidate ranking, fixed-revision feedback, or
oracle-guided repair — "unless later ablation data proves the chosen
mechanism insufficient." None of that data emerged. This is a reasoned
non-build, decided before any live call and confirmed after, not an
oversight or something deferred for later.

**Second reviewer / multi-agent critique.** The Evidence Gate is
deliberately a single deterministic checker over the *same* generating
agent's self-disclosure (see `src/bugproof/advanced.py`'s module
docstring), specifically because the brief states "the goal is not to add
more agents." Every genuine defect this round's data surfaced — execution
self-contradiction (`empty_list_average_crash`, `roster_lookup_wrong_exception`
claiming success while their own tests passed on `buggy/`), invented exact
values (round-1's original loophole), and format non-compliance — was
caught by a *mechanical* check, not by asking a second model's opinion. A
second reviewer agent would add cost and latency to catch the same class
of thing the deterministic gate already catches for free, with no evidence
in this batch that any failure mode was invisible to instrumentation and
would have required a second model's judgment to see.

**Retrieval / vector DB.** Every case in this corpus is a single bug
report against a single small source file; there is nothing to retrieve
that `create_agent_workspace()` doesn't already hand the agent directly.
Phase 2's own `summary.md` reached the same conclusion before Phase 3
began ("targeted retrieval? No evidence"); nothing in this round's data
changes that — the failures observed were never "the agent couldn't find
the relevant code," they were "the agent found the code but asserted an
unsupported exact value" or "the agent's test didn't structurally
reproduce the defect." Retrieval doesn't touch either failure mode.

**Multiple-candidate ranking.** Would require generating several
candidates per case and picking one — directly conflicts with the "one
attempt" one-shot design this project has held since Phase 2, and there's
no evidence a single well-instrumented attempt plus one bounded repair
under-samples the solution space here; D already recovered 2 of 2
recoverable Phase 2 failures without needing multiple candidates.

**Fixed-revision feedback / oracle-guided repair.** Explicitly forbidden
regardless of evidence, and never exercised: the repair prompt (see
`REPAIR_PROMPT_TEMPLATE`) is built exclusively from report.md, buggy/, the
candidate, the orchestrator's own execution result, and the gate's
grounding explanation — never `fixed/`, `oracle.yaml`, or a verdict. This
is structurally enforced (no import of `bugproof.verdict` anywhere in
`advanced.py`), not just a prompt-level promise — see the module docstring.

If a future round wants to revisit any of these, the concrete evidence
that would justify it is: a failure mode where the *code the agent needed*
was not visible in `buggy/` (would motivate retrieval), or a failure mode
where the *deterministic gate's own reasoning* was wrong in a way a second
model's judgment would plausibly have caught (would motivate a reviewer)
— neither was observed this round.
