# Special review — the three Phase 2 failure cases

Required by the Phase 3 brief: for `empty_list_average_crash` and
`roster_lookup_wrong_exception`, does the Evidence Gate identify the
exact-value assertion as unsupported? For `csv_quoted_field_parsing`,
does execution/symptom verification identify the semantic mismatch?
Answered from the real, recorded gate output — quoted, not paraphrased.

## `empty_list_average_crash`

**C (fresh generation):** the agent wrote `pytest.raises(ZeroDivisionError)`
and claimed `VERIFIED_REPRODUCTION`. The orchestrator's own execution gate
caught this independently of any evidence question — the agent's own test
**passed** on `buggy/` (the exception it expects is exactly what buggy code
raises, so `pytest.raises` catches it as success):

> `status=EXECUTION_FAILURE reason=NO_FAILURE_OBSERVED detail=candidate
> collected and passed on buggy/ -- no failure to reproduce`

The agent's own trajectory.md said `PASSED [100%]` in the same breath as
claiming `VERIFIED_REPRODUCTION` — the mechanical execution gate is what
caught the contradiction, not the evidence gate. Its exception contract
*was* well-grounded (`exception contract asserting 'ZeroDivisionError':
GROUNDED`); the defect was symptom-direction, not invented evidence.

**D (repair):** correctly diagnosed the execution-failure feedback and
rewrote the test as a bare `average_score([])` call with no
`pytest.raises` guard — deliberately **not** pinning a replacement return
value ("report.md never states what the fixed function should return
instead... I narrowed the assertion to only what report.md actually
supports"). This is exactly the brief's intended "prefer the narrowest
supported assertion" behavior, and it worked: the revised test genuinely
fails on `buggy/` for the right reason. But the repair's EVIDENCE block
was written under a `## EVIDENCE` markdown header in `trajectory.md`
instead of the required `EVIDENCE:` marker in the final response — an
unparsable block, `INSUFFICIENT_EVIDENCE` by construction, oracle-VALID
underneath. **Net effect:** the evidence gate never got the chance to
approve or reject this one on its merits — a real, disclosed
format-compliance cost, not a judgment about the grounding itself.

## `roster_lookup_wrong_exception`

**C:** same pattern as above — `pytest.raises(IndexError)` around code
that currently, buggily, raises exactly `IndexError`. The exception
contract was grounded (`'IndexError': GROUNDED -- grounded by literal item
'missing-id-indexerror'`), but execution failed identically:
`EXECUTION_FAILURE reason=NO_FAILURE_OBSERVED`.

**D:** the repair correctly recognized report.md never states the intended
replacement behavior, and narrowed to `try: find_member(...); except
IndexError: pytest.fail(...)` — asserting only "not a raw `IndexError`"
rather than guessing a specific one. This time the EVIDENCE block was
written in the required place and parsed successfully; the sole exact
contract (`exception: IndexError`) — wait, note the *narrowed* form no
longer asserts `pytest.raises(IndexError)` at all, so no exception
contract is extracted in the first place — grounding is vacuously
`SUPPORTED`, execution genuinely fails on `buggy/`
(`IndexError: list index out of range` from `roster.py:4`, caught inside
the `except` and reported via `pytest.fail`), and the oracle independently
confirms **`VALID`**. This is the one clean, complete success story in the
whole D batch: Phase 2's original failure is fully resolved.

## `csv_quoted_field_parsing`

Predicted before running anything (design review, pre-Step-0): this
case's oracle (`message_pattern: "hi to the customer"`, a literal lifted
from `reference_test.py`'s own example data) is structurally invisible to
every B/C/D arm — none of them ever see `reference_test.py`. **Confirmed**:
C claims `INSUFFICIENT_EVIDENCE` (a fresh evidence-format failure, no
`ITEM:`/`---` separators — see below), oracle says
`REJECTED/WRONG_SYMPTOM`; D's repair genuinely fixes the evidence problem
(derives the field count from its own setup list, `expected_field_count =
len(setup_fields)`, correctly executes and fails on `buggy/` for the real
reported reason) and claims `VERIFIED_REPRODUCTION` — but the oracle still
says `REJECTED/WRONG_SYMPTOM`, exactly as predicted: `message_pattern`
never matches, because it was never about this case's actual defect
evidence at all. Execution/symptom verification (the mechanical gate) is
working exactly as designed here — it correctly certifies the *reproduction*
is genuine; what it cannot and was never meant to fix is an oracle whose
own symptom check is keyed to one reference test's literal wording. This is
the same class of issue the cart_coupon_ordering oracle needed fixing for
earlier in Phase 2 — out of scope to touch in Phase 3, flagged here as a
benchmark-quality observation, not an agent or gate failure.

## Two findings beyond the required scope

**A recurring parser-fragility pattern, not a fluke.** Across 8 repair
attempts and 12 generations, agents deviated from the exact `ITEM:`/`KIND:`
/`---`-delimited EVIDENCE format in two distinct ways, each observed
multiple times independently:
- *Evidence landed outside the final message* (a `## EVIDENCE` markdown
  header in `trajectory.md`, or omitted from the final response entirely):
  `empty_list_average_crash`'s C attempt implicitly and its D repair
  explicitly; `off_by_one_pagination`'s D repair.
- *Numbered-list items with no `---` separators and inconsistent field
  casing* (`item:`/`quote:`/`source:` lowercase, or `SUPPORTS:`/`USE:`/
  `RULE:` in place of `QUOTE:`/`SOURCE:`): `contact_dedup_case_sensitivity`,
  `stale_cache_between_users`, `roster_lookup_wrong_exception`'s D repairs.
  The parser's line-based chunking (splitting only on literal `---`) then
  merges every item in the block into one, and per-field last-write-wins
  overwriting silently drops all but the last occurrence of each field —
  verified directly against the real parsed output, not inferred.

  This is a real, disclosed cost of the "smallest deterministic mechanism"
  design: it is correct and ungameable against a deliberately dishonest
  agent, but fragile against ordinary, good-faith stylistic variation from
  an honestly-reasoning one. Three of the eight `INSUFFICIENT_EVIDENCE`/
  format-driven repair outcomes trace to this, not to genuinely
  ungroundable evidence.

**Computed (non-literal) expected values evade the AST extractor
entirely.** `extract_expected_contracts` only resolves a comparison side
that is a literal `Constant`, a one-hop local-constant `Name`, or a
`List`/`Tuple` of such — never an arbitrary computed expression like
`len(setup_fields)` or `1 + page_size`. Observed independently in three
cases: `off_by_one_pagination`'s D repair (`[first, first+1, first+2]`
computed page-2 value), `csv_quoted_field_parsing`'s D repair
(`expected_field_count = len(setup_fields)`), and
`contact_dedup_case_sensitivity`'s D repair (`expected_unique_count =
len({...})`). In every case the agent's *intent* was exactly right —
computing an expected value from real setup data instead of hardcoding a
magic number — but because the comparison operand is a `Name` bound to a
`Call`, not a `Constant`, no contract is extracted for it at all, so it is
never checked (grounded or not) rather than checked and passed. This is a
deliberate, disclosed scope boundary — resolving arbitrary in-code
arithmetic would edge toward the general symbolic-analysis framework the
brief explicitly ruled out — but it is a real attack surface worth naming
plainly: a less honest agent could compute an unjustified expected value
in code specifically to dodge grounding, and nothing here would catch it.
