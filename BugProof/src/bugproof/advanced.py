"""Phase 3 mechanisms: execute-before-claim (ablation B), the Evidence /
Contract Sufficiency Gate (C), and the bounded repair loop (D). No LLM call
anywhere in this module -- every function here is pure and deterministic.
The gate works by requiring the *generating* agent to self-disclose its
evidence; this module only ever checks that disclosure against the actual
candidate/report/buggy source, never asks a second model anything.

This module never imports bugproof.verdict. That is deliberate, not an
oversight: the runtime claim computed here (compute_claim) must never be
able to see an oracle verdict, even by accident, so the benchmark oracle is
scored later by a separate caller (eval/run_advanced_replay.py) that this
module has no path to influence.

DESIGN HISTORY -- kept here because both corrections were real, reviewed
defects, not stylistic choices, and the reasoning matters for anyone
reading this file cold:

Round 1 (first design): an EvidenceItem could be labeled KIND: qualitative
to exempt it from grounding entirely, decided purely by the agent's own
label. This let an agent dodge the mechanism outright -- e.g. write
`assert average_score([]) == 0` and back it with
`KIND: qualitative / NOTE: "empty input should not crash"`, producing
SUPPORTED even though `== 0` is exactly the invented-contract failure mode
this gate exists to catch. Independent review caught this before any live
subagent call was made.

Round 1 fix -- extract_expected_contracts(): a deterministic AST walk over
the candidate finds every *exact* contract the code actually asserts
(`== <literal>`, `!= <literal>`, `is`/`is not None|True|False`,
`pytest.raises(<Exception>)`), independent of how the agent's EVIDENCE
block labels anything. Every such contract must be matched by a real,
verified EvidenceItem or the gate is UNSUPPORTED -- labeling it
qualitative, or omitting it, no longer exempts it. Setup values (e.g. the
`100` in `cart.add_item(100)`) are structurally invisible to the
extractor: only literals appearing directly inside an `assert` comparison
or a `pytest.raises(...)` argument are contracts at all.

Round 2 (this fix's own first cut): with only `literal` (quote-grounded)
and `qualitative` (exempt) kinds, a legitimate regression test that
correctly *derives* an exact value from its own setup numbers plus a
documented rule -- e.g. "$100 + $100 at a documented 10% discount = $180"
-- had no way to ground `180`, since that number need never appear
verbatim in report.md. Round 1's fix would have wrongly forced this case
into either an invented-looking quote or a weaker assertion it didn't need.

Round 2 fix -- KIND: derived, checked by _check_derived_item() via a
hand-rolled, whitelist-only arithmetic evaluator (never Python's real
eval/exec/compile): a derived item is grounded only if its BASIS
expression (plain numbers, `+ - * /`, parentheses -- no names, no calls)
safely evaluates to exactly the claimed value, the claimed value matches
the contract, its rule QUOTE is a real verified substring of its SOURCE,
and every numeric operand used in BASIS is independently provenanced
(either a real setup literal found elsewhere in the candidate, or textually
supported by the quoted rule). Applies only to numeric equality/inequality
contracts -- None/bool/string/exception contracts are always literal-only.
Any step that can't be proven this simply resolves to UNSUPPORTED, never
to a benefit of the doubt.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from bugproof.baseline import BASELINE_CONFIG
from bugproof.sandbox import SandboxRun

# -- Claim / gate status vocabulary -----------------------------------------

EXECUTION_FAILURE = "EXECUTION_FAILURE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
VERIFIED_REPRODUCTION = "VERIFIED_REPRODUCTION"

OK = "OK"
SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"


ADVANCED_CONFIG = {
    **BASELINE_CONFIG,
    "ladder_rungs": {
        "A": "frozen Phase 2 baseline, reused verbatim, not regenerated",
        "B": "+ execute before claiming: orchestrator re-runs A's frozen candidate "
             "against buggy/ itself and computes the claim mechanically; zero new "
             "subagent calls (B's generation prompt would be byte-identical to A's)",
        "C": "+ Evidence/Contract Sufficiency Gate: fresh one-shot generation with a "
             "mandatory execution report + structured EVIDENCE block; every exact "
             "contract the candidate's own code asserts is independently AST-detected "
             "and must be really grounded, regardless of how the agent labels anything",
        "D": "+ bounded repair loop: reuses C's candidate; exactly one repair "
             "subagent call iff C's claim was not already VERIFIED_REPRODUCTION",
    },
    "attempts_per_case": {"B": 0, "C": 1, "D": "0, or 1 repair iff C != VERIFIED_REPRODUCTION -- never more"},
    "candidates_generated_per_case": {"B": 0, "C": 1, "D": "0 unless repair fires, then 1 replacement"},
    "new_subagent_calls_for_12_cases": {"B": 0, "C": 12, "D": "<=12 (only C's non-VERIFIED_REPRODUCTION cases)"},
    "evidence_gate_is_llm_call": False,
    "evidence_gate_note": (
        "Deterministic checker in this module (check_evidence_grounding). The "
        "generating agent self-discloses evidence in its own response; nothing is "
        "re-asked of a second model. 'The goal is not to add more agents.'"
    ),
    "repair_bound_per_case": 1,
    "claim_states_by_variant": {
        "B": [EXECUTION_FAILURE, VERIFIED_REPRODUCTION],
        "C": [EXECUTION_FAILURE, INSUFFICIENT_EVIDENCE, VERIFIED_REPRODUCTION],
        "D": [EXECUTION_FAILURE, INSUFFICIENT_EVIDENCE, VERIFIED_REPRODUCTION],
    },
    "claim_states_note": (
        "B has no gate step, so INSUFFICIENT_EVIDENCE is unreachable for B by "
        "construction -- two states only. This asymmetry is intentional, not a gap."
    ),
    "oracle_scoring_note": (
        "evaluate() is run against every variant's final frozen candidate for every "
        "case, regardless of claim (including EXECUTION_FAILURE / "
        "INSUFFICIENT_EVIDENCE outcomes), for VRR measurement only -- as a separate, "
        "later, independent call, never the same call that fed the runtime decision."
    ),
    "contract_extraction_note": (
        "Corrected design (see module docstring): KIND labels alone never exempt an "
        "asserted value from grounding. extract_expected_contracts() independently "
        "AST-detects every exact ==, !=, is/is not, and pytest.raises(...) contract "
        "in the candidate's own code; each one must be matched by a verified literal "
        "quote or a verified derived (safe-arithmetic) computation, or the claim is "
        "INSUFFICIENT_EVIDENCE regardless of how the agent labeled its evidence."
    ),
}


# -- Prompts ------------------------------------------------------------------

GENERATION_PROMPT_TEMPLATE = """\
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
   report.md.
4. Do not modify any file under buggy/. Its final state must be byte-for-
   byte what you started with.
5. Your candidate_test.py will be copied into the same directory as the
   files currently under buggy/, and pytest will be run from there. Write
   imports accordingly -- e.g. `from module_name import thing`, not
   `from buggy.module_name import thing`.
6. You MUST run your test file exactly ONCE before finalizing (this is
   required, not optional): temporarily copy candidate_test.py into
   buggy/, run it from there with pytest, record the actual observed
   output, then remove the temporary copy from buggy/ (buggy/ must be
   unmodified in its final state, per point 4) and keep your real
   candidate_test.py only in the working directory shown above. Do not
   iterate further after this one check. Report what you actually
   observed (pass/fail, exception, message) in your final message and in
   trajectory.md -- do not claim reproduction without having actually run
   the test and seen it fail.
7. Write a short trajectory.md in the working directory: what you read,
   what you concluded, what happened when you ran your test, plus a
   bulleted list titled "Files read / commands run:" (this is
   self-reported by you, not independently re-verified by anything else).
8. Immediately before your final claim, write a structured EVIDENCE block
   disclosing, for every expected value or exception your test asserts,
   where that expectation came from. There are three kinds of item:

   KIND: literal -- the exact value appears verbatim somewhere in
   report.md or a buggy/ file.

   EVIDENCE:
   ITEM: <short slug>
   KIND: literal
   VALUE: <the exact value or exception type your test asserts, exactly
           as it appears in your code -- e.g. 0, None, "missing", KeyError>
   QUOTE: "<verbatim substring copied from the source file establishing
            exactly that value>"
   SOURCE: report.md | buggy/<filename>
   ---

   KIND: derived -- the exact value is a straightforward arithmetic
   consequence of numbers your own test already set up (e.g. quantities
   you chose) plus a rule (e.g. a rate or formula) that IS stated in the
   source. The final number itself need not appear anywhere -- what must
   be grounded is the RULE, and the arithmetic that applies it is checked
   by actually re-computing it.

   EVIDENCE:
   ITEM: <short slug>
   KIND: derived
   VALUE: <the exact numeric value your test asserts>
   BASIS: <an arithmetic expression using ONLY plain numbers already in
           your test's own setup, and +, -, *, /, parentheses -- no
           variable names, no function calls -- that evaluates to VALUE,
           e.g. "(100 + 100) - (100 + 100) * 0.10">
   QUOTE: "<verbatim substring from the source grounding the RULE this
            arithmetic applies -- e.g. the discount rate -- not the final
            number itself>"
   SOURCE: report.md | buggy/<filename>
   ---

   KIND: qualitative -- for expectations that are genuinely not encoded
   as an exact comparison anywhere in your code at all (e.g. a bare "does
   not raise" check with no == or is).

   EVIDENCE:
   ITEM: <short slug>
   KIND: qualitative
   NOTE: <one line: why this can't be pinned to a real quoted literal or
          a simple grounded arithmetic derivation>
   ---

   End the block with END_EVIDENCE. If your test genuinely asserts no
   specific expected value anywhere (rare), write one line
   `NO_EVIDENCE_ITEMS_NEEDED: <reason>` between EVIDENCE: and END_EVIDENCE
   instead of any ITEM entries -- but this claim is checked against your
   actual code, so it only holds if that's actually true.

   IMPORTANT: every exact value your test compares with ==, !=, is,
   is not, or every exception type in pytest.raises(...), is
   independently detected by reading your actual code -- not by trusting
   this block. Labeling an exact value 'qualitative' instead of
   'literal'/'derived', or omitting it, does not exempt it: any exact
   comparison found in your code must have a matching item that
   genuinely grounds it, or your claim becomes INSUFFICIENT_EVIDENCE
   regardless of labeling. Use 'derived' only when the arithmetic is
   genuinely simple and re-derivable, not to disguise a guess as a
   computation. Use 'qualitative' only for expectations that are not
   encoded as an exact comparison anywhere in your code at all.

9. Finish with your final claim in exactly this format, as the last thing
   you write:

   CLAIM: VERIFIED_REPRODUCTION
   or
   CLAIM: INSUFFICIENT_EVIDENCE

   followed by one paragraph explaining your reasoning. Use
   INSUFFICIENT_EVIDENCE if you cannot honestly back every asserted
   expectation per point 8 -- an honest INSUFFICIENT_EVIDENCE is far more
   useful than an unsupported VERIFIED_REPRODUCTION.

This is a one-shot task: no feedback, no revision after this response.
"""

REPAIR_PROMPT_TEMPLATE = """\
You are revising a previously-written pytest regression test that failed
an automated evidence check. You are a fresh agent with no memory of
writing it; everything you need is below and in your working directory.
This call is self-contained -- do not reference any earlier conversation;
there is none.

Your working directory is:

    {workspace_path}

It contains exactly: report.md, buggy/, and candidate_test.py (the test
you are revising, shown again below). Nothing else on disk is relevant.

THE CANDIDATE TEST AS WRITTEN:

```python
{candidate_source}
```

WHAT THE ORCHESTRATOR OBSERVED WHEN IT ACTUALLY RAN THIS TEST AGAINST
buggy/ (real, not hypothetical -- trust it over your own read of the code):

{execution_detail}

WHY THIS CANDIDATE FAILED ITS EVIDENCE CHECK:

{grounding_explanation}

Your task:

1. Read report.md and re-inspect buggy/ as needed.
2. Revise candidate_test.py to fix the specific evidence gap(s) named
   above. For each flagged exact value: either ground it with a real
   verbatim quote from report.md or a named buggy/*.py file (KIND:
   literal), ground it with a simple, real, re-computable arithmetic
   derivation from your own setup numbers plus a quoted rule (KIND:
   derived), or -- if you honestly cannot ground the exact value at all
   -- narrow your assertion to only what IS supported (e.g. that a
   failure/exception occurs, without pinning the exact value) rather than
   inventing one. Fix the test's logic too if the execution result above
   shows it wasn't actually failing on buggy/ for the reported reason.
3. Do not modify any file under buggy/. Final state must be byte-for-byte
   unchanged.
4. Overwrite candidate_test.py with your revision. Imports stay flat.
5. You MUST run your revised test exactly ONCE before finalizing, same
   procedure as before (temp-copy into buggy/, run, record, remove).
6. Overwrite trajectory.md: what changed and why, what you observed, plus
   "Files read / commands run:" (self-reported).
7. Write a fresh EVIDENCE block in the same format as before (literal /
   derived / qualitative items, or NO_EVIDENCE_ITEMS_NEEDED, ending with
   END_EVIDENCE). Same rules: literal quotes and derived BASIS
   expressions are independently checked against the real source, not
   trusted because you wrote them.
8. Finish with:

   CLAIM: VERIFIED_REPRODUCTION
   or
   CLAIM: INSUFFICIENT_EVIDENCE

   followed by one paragraph of reasoning.

THIS IS YOUR ONLY REVISION. No second repair attempt regardless of
outcome -- an honest CLAIM: INSUFFICIENT_EVIDENCE is correct if you
cannot honestly ground the candidate this time, not a guess.
"""


def render_generation_prompt(workspace_path: str) -> str:
    return GENERATION_PROMPT_TEMPLATE.format(workspace_path=workspace_path)


def render_repair_prompt(
    workspace_path: str,
    candidate_source: str,
    execution_detail: str,
    grounding_explanation: str,
) -> str:
    return REPAIR_PROMPT_TEMPLATE.format(
        workspace_path=workspace_path,
        candidate_source=candidate_source,
        execution_detail=execution_detail,
        grounding_explanation=grounding_explanation,
    )


# -- Contract extraction (deterministic, AST-based, no LLM) ------------------


@dataclass
class Contract:
    kind: str  # "equality" | "inequality" | "identity" | "identity-not" | "exception"
    value: str  # repr() of the literal, or the bare exception class name
    lineno: int
    source_snippet: str


def _local_constant_bindings(func: ast.AST) -> dict[str, ast.Constant]:
    """`name = <constant>` bindings anywhere in func's body -- a deliberate
    single-hop lookup, not general symbolic execution. Lets
    `expected = 85; assert actual == expected` still be caught: this exact
    pattern is why cart_coupon_ordering's own oracle needed fixing earlier
    in this project (see tests/test_oracle_generality.py)."""
    bindings: dict[str, ast.Constant] = {}
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = node.value
    return bindings


def _resolve_value(expr: ast.expr, local_constants: dict[str, ast.Constant]) -> tuple[bool, object]:
    """Returns (resolved, python_value). Handles scalars (Constant, one-hop
    local Name, unary-minus-Constant) AND literal List/Tuple whose elements
    are all themselves resolvable, e.g. `[1, 2, 3]` or `(1, "a", None)`.
    Composite literals are just as much an 'expected outcome' as scalars in
    ordinary pytest assertions (`assert get_page(...) == [1, 2, 3]` is at
    least as common as scalar equality in this corpus) -- still not general
    symbolic execution, only literal collections of literals, recursively."""
    if isinstance(expr, ast.Constant):
        return True, expr.value
    if isinstance(expr, ast.Name) and expr.id in local_constants:
        return True, local_constants[expr.id].value
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.USub) and isinstance(expr.operand, ast.Constant):
        val = expr.operand.value
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return True, -val
        return False, None
    if isinstance(expr, (ast.List, ast.Tuple)):
        values: list[object] = []
        for el in expr.elts:
            ok, val = _resolve_value(el, local_constants)
            if not ok:
                return False, None
            values.append(val)
        return True, (values if isinstance(expr, ast.List) else tuple(values))
    return False, None


def _raises_exception_name(call: ast.expr) -> str | None:
    if not isinstance(call, ast.Call) or not call.args:
        return None
    fn = call.func
    fn_name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
    if fn_name != "raises":
        return None
    exc_arg = call.args[0]
    if isinstance(exc_arg, ast.Name):
        return exc_arg.id
    if isinstance(exc_arg, ast.Attribute):
        return exc_arg.attr
    return None


def _extract_from_function(func: ast.AST) -> list[Contract]:
    local_constants = _local_constant_bindings(func)
    contracts: list[Contract] = []

    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            test = node.test
            if isinstance(test, ast.Compare) and len(test.ops) == 1:
                op = test.ops[0]
                left_ok, left_val = _resolve_value(test.left, local_constants)
                right_ok, right_val = _resolve_value(test.comparators[0], local_constants)
                # Exactly one side must resolve -- both (tautology) or
                # neither (comparing two dynamic values) contribute no
                # exact contract worth grounding.
                if left_ok != right_ok:
                    value = left_val if left_ok else right_val
                    snippet = ast.unparse(node)
                    kind_by_op = {
                        ast.Eq: "equality",
                        ast.NotEq: "inequality",
                        ast.Is: "identity",
                        ast.IsNot: "identity-not",
                    }
                    kind = kind_by_op.get(type(op))
                    if kind:
                        contracts.append(Contract(kind, repr(value), node.lineno, snippet))
        elif isinstance(node, ast.With):
            for item in node.items:
                exc_name = _raises_exception_name(item.context_expr)
                if exc_name:
                    contracts.append(Contract("exception", exc_name, node.lineno, ast.unparse(node)))
    return contracts


def extract_expected_contracts(candidate_source: str) -> list[Contract]:
    """Deterministic, AST-based, no LLM. Finds only the *expected outcome*
    side of assert comparisons and pytest.raises(...) exception types --
    never scans setup code (assignments, bare calls, call arguments) for
    literals, so `cart.add_item(100); assert cart.checkout() == 180`
    extracts only `equality: 180`, never `100`. Only walks functions whose
    name starts with "test". Only single-operator Compare nodes (no
    chained comparisons like `0 <= x < 10`). Unparsable source -> []
    (handled conservatively upstream, this function never raises).
    """
    try:
        tree = ast.parse(candidate_source)
    except SyntaxError:
        return []

    contracts: list[Contract] = []
    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)) and func.name.startswith("test"):
            contracts.extend(_extract_from_function(func))
    return contracts


def setup_numeric_literals(candidate_source: str) -> set[float]:
    """Every numeric constant in a test* function that is NOT inside an
    Assert's test expression or a pytest.raises(...) With's context
    expression -- the complement of extract_expected_contracts' own scope.
    These are the test-controlled numeric constants a `derived` BASIS
    operand is allowed to reuse."""
    try:
        tree = ast.parse(candidate_source)
    except SyntaxError:
        return set()

    literals: set[float] = set()
    for func in ast.walk(tree):
        if not (isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)) and func.name.startswith("test")):
            continue

        excluded_ids: set[int] = set()
        for node in ast.walk(func):
            if isinstance(node, ast.Assert):
                excluded_ids.update(id(sub) for sub in ast.walk(node.test))
            elif isinstance(node, ast.With):
                for item in node.items:
                    excluded_ids.update(id(sub) for sub in ast.walk(item.context_expr))

        for node in ast.walk(func):
            if isinstance(node, ast.Constant) and id(node) not in excluded_ids:
                val = node.value
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    literals.add(float(val))
    return literals


# -- EVIDENCE block parsing ---------------------------------------------------


@dataclass
class EvidenceItem:
    item_id: str
    kind: str  # "literal" | "derived" | "qualitative"
    value: str | None = None  # literal + derived
    quote: str | None = None  # literal + derived (derived: grounds the RULE, not the final number)
    source: str | None = None  # literal + derived
    basis: str | None = None  # derived only
    note: str | None = None  # qualitative only


@dataclass
class EvidenceBlock:
    items: list[EvidenceItem] = field(default_factory=list)
    no_items_needed_reason: str | None = None
    parse_ok: bool = True
    parse_error: str = ""
    raw_block_text: str = ""


_START = "EVIDENCE:"
_END = "END_EVIDENCE"
_SEP = "---"
_FIELD_KEYS = ("ITEM", "KIND", "VALUE", "QUOTE", "SOURCE", "BASIS", "NOTE")
_NO_ITEMS_PREFIX = "NO_EVIDENCE_ITEMS_NEEDED:"


def _unparsable(agent_message: str, error: str) -> EvidenceBlock:
    return EvidenceBlock(items=[], parse_ok=False, parse_error=error, raw_block_text=agent_message)


def parse_evidence_block(agent_message: str) -> EvidenceBlock:
    """Tolerant, line-based, never raises. Unparsable input becomes
    parse_ok=False, which check_evidence_grounding/compute_claim treat as
    UNSUPPORTED -- a parsing failure is never silently treated as success."""
    lines = agent_message.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == _START)
        end = next(i for i, ln in enumerate(lines) if i > start and ln.strip() == _END)
    except StopIteration:
        return _unparsable(agent_message, "no EVIDENCE:/END_EVIDENCE block found")

    body = lines[start + 1 : end]
    raw = "\n".join(lines[start : end + 1])

    for ln in body:
        if ln.strip().startswith(_NO_ITEMS_PREFIX):
            reason = ln.strip()[len(_NO_ITEMS_PREFIX) :].strip()
            return EvidenceBlock(items=[], no_items_needed_reason=reason or "(no reason given)", raw_block_text=raw)

    chunks: list[list[str]] = [[]]
    for ln in body:
        if ln.strip() == _SEP:
            chunks.append([])
        else:
            chunks[-1].append(ln)

    items: list[EvidenceItem] = []
    for chunk in chunks:
        fields: dict[str, str] = {}
        for ln in chunk:
            stripped = ln.strip()
            for key in _FIELD_KEYS:
                prefix = key + ":"
                if stripped.startswith(prefix):
                    fields[key] = stripped[len(prefix) :].strip().strip('"')
                    break
        if fields:
            items.append(
                EvidenceItem(
                    item_id=fields.get("ITEM", "(unnamed)"),
                    kind=fields.get("KIND", ""),
                    value=fields.get("VALUE"),
                    quote=fields.get("QUOTE"),
                    source=fields.get("SOURCE"),
                    basis=fields.get("BASIS"),
                    note=fields.get("NOTE"),
                )
            )

    if not items:
        return _unparsable(agent_message, "EVIDENCE block present but no ITEM entries and no NO_EVIDENCE_ITEMS_NEEDED")
    return EvidenceBlock(items=items, raw_block_text=raw)


# -- Grounding checks ----------------------------------------------------------


def _normalize(text: str) -> str:
    return " ".join((text or "").casefold().split())


def _normalized_contains(haystack: str, needle: str) -> bool:
    needle = (needle or "").strip()
    return bool(needle) and _normalize(needle) in _normalize(haystack)


def _try_parse_number(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text.strip())
    except (TypeError, ValueError):
        return None


def _contract_matches_claimed_value(contract: Contract, claimed_value: str) -> bool:
    """Tolerant matching between an AST-extracted Contract.value (a repr()
    string -- possibly of a list/tuple, see _resolve_value) and free text
    an agent wrote after VALUE:. Equality/inequality contracts try
    structural equality via ast.literal_eval first -- this uniformly
    handles numbers, strings, lists, and tuples (e.g. contract "[1, 2, 3]"
    vs claimed "[1,2,3]") without separate per-type logic. Falls back to a
    numeric-tolerant comparison, then a normalized string comparison, for
    text that doesn't literal_eval cleanly. None/True/False identity
    contracts match case-insensitively; exception names compare stripped
    of surrounding quotes, exact then casefold fallback."""
    claimed = (claimed_value or "").strip()
    if not claimed:
        return False

    if contract.kind in ("identity", "identity-not"):
        return _normalize(claimed).strip("\"' ") == _normalize(contract.value)

    if contract.kind == "exception":
        c = contract.value.strip("\"' ")
        cl = claimed.strip("\"' ")
        return cl == c or cl.casefold() == c.casefold()

    # equality / inequality
    try:
        if ast.literal_eval(contract.value) == ast.literal_eval(claimed):
            return True
    except Exception:
        pass

    contract_numeric = _try_parse_number(contract.value)
    claimed_numeric = _try_parse_number(claimed)
    if contract_numeric is not None and claimed_numeric is not None:
        return abs(contract_numeric - claimed_numeric) < 1e-9

    try:
        c_str = str(ast.literal_eval(contract.value))
    except Exception:
        c_str = contract.value.strip("\"' ")
    cl_str = claimed.strip("\"' ")
    return cl_str == c_str or cl_str.casefold() == c_str.casefold()


@dataclass
class ItemCheck:
    item_id: str
    kind: str
    supported: bool
    reason: str


@dataclass
class ContractCheck:
    contract: Contract
    matched_item_id: str | None
    grounded: bool
    reason: str


@dataclass
class GroundingResult:
    status: str  # SUPPORTED | UNSUPPORTED
    contract_checks: list[ContractCheck]
    item_checks: list[ItemCheck]
    mislabel_suspected: bool
    mislabel_detail: str
    detail: str


# -- Derived grounding: safe arithmetic, never eval()/exec() -----------------

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub)


class _UnsafeBasisError(Exception):
    pass


def _safe_eval_arithmetic(node: ast.AST) -> float:
    """Hand-rolled recursive evaluator over a strict node-type whitelist --
    never Python's eval()/exec()/compile()-for-execution, no escape
    surface. Anything outside Expression/numeric-Constant/BinOp(+-*/)/
    UnaryOp(+-) -- including any Name or Call -- raises _UnsafeBasisError."""
    if isinstance(node, ast.Expression):
        return _safe_eval_arithmetic(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise _UnsafeBasisError(f"non-numeric constant {node.value!r}")
        return float(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left = _safe_eval_arithmetic(node.left)
        right = _safe_eval_arithmetic(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise _UnsafeBasisError("division by zero")
        return left / right
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARYOPS):
        value = _safe_eval_arithmetic(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    raise _UnsafeBasisError(f"disallowed construct: {type(node).__name__}")


def _collect_basis_operands(node: ast.AST) -> list[float]:
    if isinstance(node, ast.Expression):
        return _collect_basis_operands(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return [float(node.value)]
    if isinstance(node, ast.BinOp):
        return _collect_basis_operands(node.left) + _collect_basis_operands(node.right)
    if isinstance(node, ast.UnaryOp):
        return _collect_basis_operands(node.operand)
    return []


def _evaluate_basis(basis_text: str) -> tuple[float | None, list[float], str]:
    """Never raises out. (None, [], reason) on any parse or safety failure."""
    try:
        tree = ast.parse(basis_text, mode="eval")
    except SyntaxError as exc:
        return None, [], f"BASIS is not valid arithmetic syntax: {exc}"
    try:
        result = _safe_eval_arithmetic(tree)
    except _UnsafeBasisError as exc:
        return None, [], f"BASIS uses a disallowed construct: {exc}"
    return result, _collect_basis_operands(tree), ""


def _operand_supported_by_quote(operand: float, quote: str) -> bool:
    """Narrow, explicit heuristic for a 'documentation' operand not from
    setup (e.g. a discount rate): checks the operand's plain integer/
    decimal form, or its x100 percent form (0.10 -> "10"), as a normalized
    substring of the quote. Deliberately biased toward False (->
    UNSUPPORTED) when uncertain -- no general text-to-number NLP."""
    candidates: set[str] = set()
    if operand == int(operand):
        candidates.add(str(int(operand)))
    candidates.add(str(operand))
    pct = operand * 100
    if pct == int(pct):
        candidates.add(str(int(pct)))
    normalized_quote = _normalize(quote)
    return any(_normalize(c) in normalized_quote for c in candidates)


def _check_derived_item(
    item: EvidenceItem,
    contract: Contract,
    report_text: str,
    buggy_files: dict[str, str],
    setup_literals: set[float],
) -> tuple[bool, str]:
    """Grounded iff, in order: BASIS parses and safely evaluates; the
    result equals the contract's own numeric value (this is what stops a
    WRONG arithmetic derivation, not just an unsafe one); QUOTE is a real
    verified substring of SOURCE; every BASIS operand is either a real
    setup literal or textually supported by the quote. Any failure ->
    (False, reason) -- 'if this cannot be proven simply, mark
    UNSUPPORTED' is the default on every branch, never the exception."""
    if not item.basis or not item.quote or not item.source or item.value is None:
        return False, "derived item missing BASIS, VALUE, QUOTE, or SOURCE"

    result, operands, err = _evaluate_basis(item.basis)
    if result is None:
        return False, f"invalid BASIS: {err}"

    target = _try_parse_number(contract.value)
    if target is None:
        return False, "derived grounding only applies to numeric equality/inequality contracts"
    if abs(result - target) > 1e-9:
        return False, f"BASIS {item.basis!r} evaluates to {result}, not the asserted {target}"

    src = report_text if item.source == "report.md" else buggy_files.get(item.source.removeprefix("buggy/"))
    if src is None:
        return False, f"unknown SOURCE {item.source!r}"
    if not _normalized_contains(src, item.quote):
        return False, f"QUOTE not verified as a real substring of {item.source} (fabricated)"

    for operand in operands:
        if operand in setup_literals or _operand_supported_by_quote(operand, item.quote):
            continue
        return False, f"BASIS operand {operand} is neither a test setup constant nor supported by the quoted text"

    return True, f"BASIS {item.basis!r} = {result} verified against setup constants + quoted rule in {item.source}"


def check_evidence_grounding(
    candidate_source: str,
    evidence: EvidenceBlock,
    report_text: str,
    buggy_files: dict[str, str],
) -> GroundingResult:
    """status = SUPPORTED iff EVERY AST-extracted Contract is grounded by a
    verified `literal` item (same value, real quote) or -- numeric
    equality/inequality contracts only -- a verified `derived` item
    (safe-evaluated BASIS, provenanced operands). A `qualitative` item can
    never satisfy a contract, no matter how it's worded -- this is the
    fix for the mislabel-to-bypass loophole. Zero extracted contracts
    (nothing exact asserted -- e.g. a bare 'does not raise' check) is
    trivially SUPPORTED as long as the block itself parses; this is the
    legitimate 'narrowed assertion' path the brief asks for."""
    if not evidence.parse_ok:
        return GroundingResult(
            UNSUPPORTED, [], [], False, "",
            f"EVIDENCE block missing/unparsable: {evidence.parse_error}",
        )

    contracts = extract_expected_contracts(candidate_source)

    if evidence.no_items_needed_reason is not None:
        if contracts:
            checks = [
                ContractCheck(c, None, False, "agent claimed NO_EVIDENCE_ITEMS_NEEDED, but this exact contract exists")
                for c in contracts
            ]
            return GroundingResult(
                UNSUPPORTED, checks, [], True,
                "NO_EVIDENCE_ITEMS_NEEDED claimed despite real exact contracts in the candidate",
                "agent's NO_EVIDENCE_ITEMS_NEEDED claim is contradicted by AST-extracted contracts",
            )
        return GroundingResult(SUPPORTED, [], [], False, "", f"NO_EVIDENCE_ITEMS_NEEDED: {evidence.no_items_needed_reason}")

    item_checks: list[ItemCheck] = []
    verified_literal_items: list[EvidenceItem] = []
    for item in evidence.items:
        if item.kind == "literal":
            if not item.quote or not item.source or item.value is None:
                item_checks.append(ItemCheck(item.item_id, item.kind, False, "literal item missing VALUE, QUOTE, or SOURCE"))
                continue
            src = report_text if item.source == "report.md" else buggy_files.get(item.source.removeprefix("buggy/"))
            if src is None:
                item_checks.append(ItemCheck(item.item_id, item.kind, False, f"unknown SOURCE {item.source!r}"))
            elif _normalized_contains(src, item.quote):
                item_checks.append(ItemCheck(item.item_id, item.kind, True, f"quote verified in {item.source}"))
                verified_literal_items.append(item)
            else:
                item_checks.append(ItemCheck(item.item_id, item.kind, False, f"quote not found in {item.source} (fabricated)"))
        elif item.kind == "derived":
            has_fields = bool(item.basis and item.quote and item.source and item.value is not None)
            item_checks.append(
                ItemCheck(item.item_id, item.kind, has_fields,
                          "has required fields" if has_fields else "derived item missing BASIS, VALUE, QUOTE, or SOURCE")
            )
        elif item.kind == "qualitative":
            item_checks.append(ItemCheck(item.item_id, item.kind, True, "qualitative -- no exact value claimed"))
        else:
            item_checks.append(ItemCheck(item.item_id, item.kind, False, f"unrecognized KIND {item.kind!r}"))

    setup_literals = setup_numeric_literals(candidate_source)

    contract_checks: list[ContractCheck] = []
    for contract in contracts:
        match = next((it for it in verified_literal_items if _contract_matches_claimed_value(contract, it.value or "")), None)
        if match is not None:
            contract_checks.append(ContractCheck(contract, match.item_id, True, f"grounded by literal item {match.item_id!r}"))
            continue

        if contract.kind in ("equality", "inequality") and _try_parse_number(contract.value) is not None:
            derived_candidates = [
                it for it in evidence.items if it.kind == "derived" and _contract_matches_claimed_value(contract, it.value or "")
            ]
            grounded, item_id, reason = False, None, "no derived item claims this value"
            for derived_item in derived_candidates:
                ok, why = _check_derived_item(derived_item, contract, report_text, buggy_files, setup_literals)
                item_id, reason = derived_item.item_id, why
                if ok:
                    grounded = True
                    break
            if grounded:
                contract_checks.append(ContractCheck(contract, item_id, True, reason))
                continue
            if derived_candidates:
                contract_checks.append(ContractCheck(contract, item_id, False, reason))
                continue

        contract_checks.append(
            ContractCheck(
                contract, None, False,
                "no verified literal or valid derived EVIDENCE item matches this exact contract -- "
                "labeling it qualitative or omitting it does not exempt it",
            )
        )

    status = SUPPORTED if all(c.grounded for c in contract_checks) else UNSUPPORTED
    mislabel_suspected = bool(contracts) and not any(i.kind in ("literal", "derived") for i in evidence.items)
    mislabel_detail = (
        "exact contracts exist in the candidate but zero literal/derived items were disclosed at all"
        if mislabel_suspected else ""
    )
    detail = (
        f"{sum(1 for c in contract_checks if c.grounded)}/{len(contract_checks)} exact contract(s) grounded"
        if contract_checks else "no exact contracts to ground"
    )
    return GroundingResult(status, contract_checks, item_checks, mislabel_suspected, mislabel_detail, detail)


# -- Execution-before-claim ----------------------------------------------------


@dataclass
class ExecutionGateResult:
    status: str  # OK | EXECUTION_FAILURE
    reason: str | None  # None | COLLECTION_ERROR | NO_FAILURE_OBSERVED | TIMED_OUT
    detail: str
    buggy_tampering_detected: bool = False
    buggy_tampering_detail: str = "not checked"


def _diff_buggy_dirs(agent_buggy_dir: Path, case_buggy_dir: Path) -> tuple[bool, str]:
    """Informational only -- never changes OK/EXECUTION_FAILURE, since the
    real check always re-runs against a *fresh* copy of case_dir/buggy/,
    never the agent's own copy. Cheap insurance against a misbehaving
    agent editing its own buggy/ to make a test trivially pass."""
    agent_buggy_dir, case_buggy_dir = Path(agent_buggy_dir), Path(case_buggy_dir)
    a = {p.relative_to(agent_buggy_dir): p for p in agent_buggy_dir.rglob("*") if p.is_file()}
    c = {p.relative_to(case_buggy_dir): p for p in case_buggy_dir.rglob("*") if p.is_file()}
    if a.keys() != c.keys():
        added = sorted(str(k) for k in a.keys() - c.keys())
        removed = sorted(str(k) for k in c.keys() - a.keys())
        return True, f"file set differs: added={added} removed={removed}"
    changed = sorted(str(rel) for rel, p in a.items() if p.read_bytes() != c[rel].read_bytes())
    if changed:
        return True, f"content differs in: {changed}"
    return False, "buggy/ byte-for-byte unchanged"


def check_execution_before_claim(
    run: SandboxRun,
    *,
    agent_buggy_dir: Path | None = None,
    case_buggy_dir: Path | None = None,
) -> ExecutionGateResult:
    """Uses only the orchestrator's own SandboxRun against buggy/ -- never
    the agent's self-report. No oracle.yaml, no fixed/, ever."""
    if agent_buggy_dir is not None and case_buggy_dir is not None:
        tampering, tamper_detail = _diff_buggy_dirs(agent_buggy_dir, case_buggy_dir)
    else:
        tampering, tamper_detail = False, "not checked (no agent workspace to diff)"

    if run.timed_out:
        return ExecutionGateResult(
            EXECUTION_FAILURE, "TIMED_OUT",
            "orchestrator's run_pytest against buggy/ did not finish within the time budget",
            tampering, tamper_detail,
        )
    if run.collection_error:
        return ExecutionGateResult(EXECUTION_FAILURE, "COLLECTION_ERROR", run.collection_error_text[:2000], tampering, tamper_detail)
    if not run.any_failed():
        return ExecutionGateResult(
            EXECUTION_FAILURE, "NO_FAILURE_OBSERVED",
            "candidate collected and passed on buggy/ -- no failure to reproduce",
            tampering, tamper_detail,
        )
    return ExecutionGateResult(OK, None, f"{len(run.failing())} failing testcase(s) observed on buggy/", tampering, tamper_detail)


# -- Final claim ---------------------------------------------------------------


def compute_claim(execution: ExecutionGateResult, grounding: GroundingResult | None) -> str:
    """B calls this with grounding=None (no gate step) -> two states only
    (EXECUTION_FAILURE / VERIFIED_REPRODUCTION). C/D always pass a real
    GroundingResult -> three states. Priority: an execution failure is
    reported as such regardless of what grounding would have said."""
    if execution.status == EXECUTION_FAILURE:
        return EXECUTION_FAILURE
    if grounding is None:
        return VERIFIED_REPRODUCTION
    if grounding.status == UNSUPPORTED:
        return INSUFFICIENT_EVIDENCE
    return VERIFIED_REPRODUCTION
