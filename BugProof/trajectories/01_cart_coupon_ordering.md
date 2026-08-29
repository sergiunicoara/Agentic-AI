# Episode 1 — `cart_coupon_ordering`: straightforward successful reproduction

**Demonstrates:** a clean case, `VERIFIED_REPRODUCTION` / oracle-`VALID`
consistently across B, C, and D — the baseline "everything worked as
intended" episode against which the harder cases below should be read.

## Source artifacts (original, unmodified)

| Path | SHA-256 |
|---|---|
| `cases/cart_coupon_ordering/report.md` | `cebb2936cd27abecb803c01132438b731f8299a13388d2a666183d327a6dfa86` |
| `evidence/advanced/trajectories/cart_coupon_ordering/bundle.json` | `81620dab722049fef61c9bb0e6c369401f736bbdc0844e8a8d349a1127622254` |
| `evidence/advanced/candidates/C/cart_coupon_ordering/candidate_test.py` | `d3e6ecc34a0d0c112e0af28812b362bea05ba8d7dd098be28ead2e82b079f81b` |

(D's candidate is byte-identical to C's — `repair_fired: false`, since C's
claim was already `VERIFIED_REPRODUCTION`; same hash, verified above.)

## Input — bug report (directly captured, verbatim)

> Getting occasional complaints that a coupon code doesn't fully apply to
> an order. One customer described adding an item, applying the coupon,
> then adding a second item — the second item came out at full price,
> like the coupon only covered part of the cart. It seems inconsistent
> though: another customer said it worked fine for them, and they
> mentioned adding everything to the cart before entering the coupon
> code.

## Agent instruction

Directly captured: the standard Phase 3 `GENERATION_PROMPT_TEMPLATE`
(`src/bugproof/advanced.py`), workspace scoped to exactly `report.md` +
`buggy/` for this case — full text recorded in the bundle's
`C.prompt_sent` field.

## Final candidate (C, reused unchanged by D)

Two tests: one reproduces the coupon-applied-then-item-added ordering
(expects the whole cart discounted, gets a partial discount on buggy
code), one confirms the "add everything first" ordering already works —
directly mirroring both customers' reports.

## Execution outcome (orchestrator-measured, not agent-self-reported)

`C.execution_result.status = "OK"`, 1 of 2 testcases failing on `buggy/`
— the order-dependent one, matching the report exactly.

## Gate/claim outcome

Evidence Gate: `SUPPORTED`. The candidate's one exact numeric contract
(`80`, the correctly-discounted total) is grounded as a `derived` item —
`BASIS: (50 + 50) - (50 + 50) * 20 / 100`, quote-grounded against the
coupon-discount formula literally present in `buggy/cart.py`. Final claim:
`VERIFIED_REPRODUCTION`.

## Repair

Not applicable — C already reached `VERIFIED_REPRODUCTION`.

## Oracle measurement (deterministic, separate, later)

`status: VALID` (all five conditions satisfied) for B, C, and D alike.

## Agent self-reported (trajectory.md, not independently re-verified beyond the execution result above)

Reports reading `report.md` and `buggy/cart.py`, running the test once via
temp-copy into `buggy/`, observing the expected failure, and confirming
`buggy/` was left unmodified.

## Human checkpoint / orchestration decision

None required for this case — it followed the standard B/C/D pipeline with
no anomaly.
