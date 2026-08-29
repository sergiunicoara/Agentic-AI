# Episode 5 — `csv_quoted_field_parsing`: structural oracle/reference-text mismatch

**Demonstrates:** a case where no B/C/D mechanism can ever move the
oracle verdict, because this case's oracle checks for a literal string
lifted from `reference_test.py`'s own example data — something no B/C/D
arm ever sees. Predicted before any live call in this round's design
review, confirmed after. A genuine benchmark-oracle limitation, not an
agent or gate failure — already known from Phase 2 and explicitly left
unfixed as out of scope for Phase 3.

## Source artifacts (original, unmodified)

| Path | SHA-256 |
|---|---|
| `cases/csv_quoted_field_parsing/report.md` | `49fe3af22de7d1727bc1e03459a8bd59496902269f91febfc7ab4c326ac87941` |
| `evidence/advanced/trajectories/csv_quoted_field_parsing/bundle.json` | `984228c37ce757b15e23441b6bb3d7403f1ce4757a6d39c2c082cdcb1bec4e87` |
| `evidence/advanced/candidates/C/csv_quoted_field_parsing/candidate_test.py` | `4a28be79904b96e3736b7ba708544f95b5b8b5ee71ebe4c6d883517ee5f3d6f8` |
| `evidence/advanced/candidates/D/csv_quoted_field_parsing/candidate_test.py` | `3987f1f7414ee4faeb29ef7846e1be07616b3deb3954408cc1b2c545a9044bd5` |

## Input — bug report (directly captured, verbatim)

> Importing a product catalog file, one of the description fields came
> out mangled. The source text has a quoted phrase inside it, and after
> import the embedded quote marks are just gone from the value, and it
> looks like the field boundary shifted somehow right after that point
> too. Most rows in the file import fine — it seems specific to this kind
> of field.

## Round C — generation

**Final candidate:** constructs `101,"He said "ok, sure" today",29.99` —
a field with an embedded quoted phrase — and asserts `len(fields) == 3`
(expected 3 real fields) plus that the description text stays together.

**Execution outcome (orchestrator-measured):** `OK` — genuinely fails on
`buggy/` with `assert 4 == 3`, the buggy parser splitting on the comma
inside the embedded quoted phrase.

**Gate/claim outcome:** the count `3` was asserted via a hand-counted
derived item (`BASIS: 2 + 1`) whose operand provenance couldn't be
verified against the candidate's own setup — `UNSUPPORTED`. **Claim:
`INSUFFICIENT_EVIDENCE`.**

**Oracle measurement:** `REJECTED / WRONG_SYMPTOM` —
`expected exception_type='' message_pattern='hi to the customer';
observed failure text did not match`. This case's oracle checks for a
literal phrase from `reference_test.py`'s own example data — never
visible to the agent at any point.

## Round D — bounded repair (fired: C was `INSUFFICIENT_EVIDENCE`)

**Repaired candidate:** replaced the hand-count with a re-computable
derivation — `expected_field_count = len(setup_fields)` where
`setup_fields` is the test's own list of the three fields it's about to
join — grounded by `parse_line`'s own docstring ("Split a single
delimited line into fields, respecting double-quoted fields") as the rule
justifying why a correctly-quoted field must survive intact.

**Execution outcome:** re-run genuinely fails on `buggy/` — `assert 4 ==
3`, buggy output shown as `['101', 'He said ok', ' sure today', '29.99']`
— matching the report's "quote marks gone / field boundary shifted"
description exactly.

**Gate/claim outcome:** the `expected_field_count = len(setup_fields)`
expression is a `Name` bound to a `Call`, not a literal `Constant` —
invisible to the AST contract extractor entirely (a disclosed scope
boundary, not a bug: see `evidence/advanced/ablations/special_review.md`'s
"computed expected values evade the AST extractor" finding). With zero
extractable contracts, the gate is vacuously `SUPPORTED`. **Claim:
`VERIFIED_REPRODUCTION`.**

**Oracle measurement (separate, later, never fed back into the claim
above):** **still `REJECTED / WRONG_SYMPTOM`, unchanged** — exactly as
predicted before this round's batch ever ran. The repair fixed the
evidence-grounding problem; it could never fix an oracle checking for
text from a file the candidate never saw.

## Agent self-reported (not independently re-verified beyond the execution results above)

Both rounds' `trajectory.md` describe reading `report.md` and
`buggy/linefmt.py`, hand-tracing the `in_quotes` toggle logic to explain
the defect mechanism, running the test once, and confirming `buggy/` was
left unmodified.

## Human checkpoint / orchestration decision

None specific to this case. Its predicted-then-confirmed outcome is used
in `evidence/advanced/ablations/special_review.md` as a worked example of
distinguishing "the runtime system's execution/symptom verification
correctly certifies a genuine reproduction" from "the benchmark oracle
still rejects it" — two different, independently checkable facts that
this episode shows disagreeing for a structural reason, not a quality one.
