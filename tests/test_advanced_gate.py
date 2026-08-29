"""Unit coverage for src/bugproof/advanced.py's deterministic mechanisms --
run before any live subagent call, per the Phase 3 plan's Step -1 gate.

Covers the 11 scenarios independent review required (numbered 1-11 below,
verbatim in spirit from the review), plus pre-existing coverage for parsing
tolerance, the mislabel heuristic, compute_claim's state asymmetry, and the
execution gate's SandboxRun mapping (12-17).
"""

from __future__ import annotations

from bugproof.advanced import (
    EXECUTION_FAILURE,
    OK,
    SUPPORTED,
    UNSUPPORTED,
    VERIFIED_REPRODUCTION,
    INSUFFICIENT_EVIDENCE,
    check_evidence_grounding,
    check_execution_before_claim,
    compute_claim,
    extract_expected_contracts,
    parse_evidence_block,
)
from bugproof.sandbox import SandboxRun, TestCaseResult

# ---------------------------------------------------------------------------
# Shared fixtures (plain module-level constants, not pytest fixtures --
# these are just candidate/report text, not I/O).
# ---------------------------------------------------------------------------

_EMPTY_LIST_CANDIDATE = """\
from stats import average_score


def test_empty_list_returns_zero():
    result = average_score([])
    assert result == 0
"""

_MISSING_MEMBER_NONE_CANDIDATE = """\
from roster import find_member


def test_missing_member_returns_none():
    result = find_member({}, "nobody")
    assert result is None
"""

_MISSING_MEMBER_RAISES_CANDIDATE = """\
import pytest

from roster import find_member


def test_missing_member_raises_keyerror():
    with pytest.raises(KeyError):
        find_member({}, "nobody")
"""

_CART_SETUP_CANDIDATE = """\
from cart import ShoppingCart


def test_cart_add_then_checkout():
    cart = ShoppingCart()
    cart.add_item(100)
    assert cart.checkout() == 180
"""

_CART_DISCOUNT_CANDIDATE = """\
from cart import ShoppingCart


def test_two_items_discounted_total():
    cart = ShoppingCart()
    cart.add_item(100)
    cart.add_item(100)
    assert cart.checkout() == 180
"""

_NO_CRASH_CANDIDATE = """\
from stats import average_score


def test_empty_list_does_not_crash():
    try:
        average_score([])
    except Exception as exc:
        raise AssertionError(f"average_score([]) raised {exc!r}, but empty input should not crash") from exc
"""


def _message(evidence_body: str, claim: str = "VERIFIED_REPRODUCTION") -> str:
    return f"Some narrative reasoning here.\n\n{evidence_body}\n\nCLAIM: {claim}\nReasoning paragraph.\n"


# ---------------------------------------------------------------------------
# 1-2: "must not crash" vs. explicitly grounded 0
# ---------------------------------------------------------------------------


def test_1_ungrounded_zero_via_mislabeled_qualitative_is_unsupported():
    """The exact loophole independent review caught: an invented == 0 is
    NOT exempted just because the agent labels it qualitative."""
    report_text = "Calling average_score on an empty list crashes. Empty input must not crash."
    message = _message(
        "EVIDENCE:\n"
        "ITEM: empty-list-returns-zero\n"
        "KIND: qualitative\n"
        "NOTE: report says empty input must not crash\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    assert evidence.parse_ok
    result = check_evidence_grounding(_EMPTY_LIST_CANDIDATE, evidence, report_text, {})
    assert result.status == UNSUPPORTED
    assert any(not c.grounded for c in result.contract_checks)


def test_2_explicitly_grounded_zero_is_supported():
    report_text = "average_score of an empty list should return 0."
    message = _message(
        "EVIDENCE:\n"
        "ITEM: empty-list-returns-zero\n"
        "KIND: literal\n"
        "VALUE: 0\n"
        'QUOTE: "average_score of an empty list should return 0"\n'
        "SOURCE: report.md\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    result = check_evidence_grounding(_EMPTY_LIST_CANDIDATE, evidence, report_text, {})
    assert result.status == SUPPORTED
    assert all(c.grounded for c in result.contract_checks)


# ---------------------------------------------------------------------------
# 3-4: vague "normal missing behavior" vs. explicitly grounded None
# ---------------------------------------------------------------------------


def test_3_vague_report_does_not_ground_is_none():
    report_text = "Looking up a missing member should behave like normal missing-member handling elsewhere."
    message = _message(
        "EVIDENCE:\n"
        "ITEM: missing-member\n"
        "KIND: qualitative\n"
        "NOTE: report describes normal missing behavior without naming a value\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    result = check_evidence_grounding(_MISSING_MEMBER_NONE_CANDIDATE, evidence, report_text, {})
    assert result.status == UNSUPPORTED


def test_4_explicitly_grounded_none_is_supported():
    report_text = "find_member should return None when the member is missing, matching the rest of the API."
    message = _message(
        "EVIDENCE:\n"
        "ITEM: missing-member\n"
        "KIND: literal\n"
        "VALUE: None\n"
        'QUOTE: "find_member should return None when the member is missing"\n'
        "SOURCE: report.md\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    result = check_evidence_grounding(_MISSING_MEMBER_NONE_CANDIDATE, evidence, report_text, {})
    assert result.status == SUPPORTED


# ---------------------------------------------------------------------------
# 5-6: exception type not established vs. explicitly established
# ---------------------------------------------------------------------------


def test_5_ungrounded_exception_type_is_unsupported():
    report_text = "Looking up a missing member currently raises IndexError, which is wrong."
    message = _message(
        "EVIDENCE:\n"
        "ITEM: missing-member-exception\n"
        "KIND: qualitative\n"
        "NOTE: report only says the current IndexError is wrong, doesn't name the correct exception\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    result = check_evidence_grounding(_MISSING_MEMBER_RAISES_CANDIDATE, evidence, report_text, {})
    assert result.status == UNSUPPORTED


def test_6_grounded_exception_type_is_supported():
    report_text = "find_member should raise KeyError for a missing member, consistent with dict-style lookups elsewhere."
    message = _message(
        "EVIDENCE:\n"
        "ITEM: missing-member-exception\n"
        "KIND: literal\n"
        "VALUE: KeyError\n"
        'QUOTE: "find_member should raise KeyError for a missing member"\n'
        "SOURCE: report.md\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    result = check_evidence_grounding(_MISSING_MEMBER_RAISES_CANDIDATE, evidence, report_text, {})
    assert result.status == SUPPORTED


# ---------------------------------------------------------------------------
# 7: setup literals never mistaken for expected-contract literals
# ---------------------------------------------------------------------------


def test_7_setup_literal_not_extracted_as_contract():
    contracts = extract_expected_contracts(_CART_SETUP_CANDIDATE)
    assert len(contracts) == 1
    assert contracts[0].kind == "equality"
    assert contracts[0].value == "180"
    assert all(c.value != "100" for c in contracts)


# ---------------------------------------------------------------------------
# 8-9: derived grounding -- legitimate arithmetic vs. wrong arithmetic
# ---------------------------------------------------------------------------


def test_8_legitimate_derived_value_is_supported():
    report_text = "Prices include a documented 10% discount applied at checkout."
    message = _message(
        "EVIDENCE:\n"
        "ITEM: discounted-total\n"
        "KIND: derived\n"
        "VALUE: 180\n"
        "BASIS: (100 + 100) - (100 + 100) * 0.10\n"
        'QUOTE: "a documented 10% discount"\n'
        "SOURCE: report.md\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    result = check_evidence_grounding(_CART_DISCOUNT_CANDIDATE, evidence, report_text, {})
    assert result.status == SUPPORTED, result.contract_checks


def test_9_wrong_arithmetic_derivation_is_rejected():
    report_text = "Prices include a documented 10% discount applied at checkout."
    # Candidate asserts 170; claimed BASIS actually computes to 180 -- a
    # mismatched, wrong derivation, not merely an unsafe one.
    candidate = _CART_DISCOUNT_CANDIDATE.replace("== 180", "== 170")
    message = _message(
        "EVIDENCE:\n"
        "ITEM: discounted-total\n"
        "KIND: derived\n"
        "VALUE: 170\n"
        "BASIS: (100 + 100) - (100 + 100) * 0.10\n"
        'QUOTE: "a documented 10% discount"\n'
        "SOURCE: report.md\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    result = check_evidence_grounding(candidate, evidence, report_text, {})
    assert result.status == UNSUPPORTED
    assert any("evaluates to" in c.reason for c in result.contract_checks)


def test_10_arbitrary_function_call_basis_is_rejected():
    report_text = "Prices include a documented 10% discount applied at checkout."
    message = _message(
        "EVIDENCE:\n"
        "ITEM: discounted-total\n"
        "KIND: derived\n"
        "VALUE: 180\n"
        "BASIS: compute_discount(100, 100) - 10\n"
        'QUOTE: "a documented 10% discount"\n'
        "SOURCE: report.md\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    result = check_evidence_grounding(_CART_DISCOUNT_CANDIDATE, evidence, report_text, {})
    assert result.status == UNSUPPORTED
    assert any("invalid BASIS" in c.reason for c in result.contract_checks)

    # Also confirm a bare Name reference (not just a Call) is rejected --
    # _safe_eval_arithmetic must never fall through to Python's real eval.
    message_name = _message(
        "EVIDENCE:\n"
        "ITEM: discounted-total\n"
        "KIND: derived\n"
        "VALUE: 180\n"
        "BASIS: some_var + 100\n"
        'QUOTE: "a documented 10% discount"\n'
        "SOURCE: report.md\n"
        "END_EVIDENCE"
    )
    evidence_name = parse_evidence_block(message_name)
    result_name = check_evidence_grounding(_CART_DISCOUNT_CANDIDATE, evidence_name, report_text, {})
    assert result_name.status == UNSUPPORTED


def test_11_invented_contract_with_no_evidence_at_all_stays_unsupported():
    report_text = "Calling average_score on an empty list crashes. Empty input must not crash."
    message = _message("EVIDENCE:\nNO_EVIDENCE_ITEMS_NEEDED: nothing exact is asserted\nEND_EVIDENCE")
    evidence = parse_evidence_block(message)
    assert evidence.no_items_needed_reason is not None
    # The candidate DOES assert an exact 0 -- the agent's claim is simply
    # false, and derived grounding doesn't widen what counts as evidence.
    result = check_evidence_grounding(_EMPTY_LIST_CANDIDATE, evidence, report_text, {})
    assert result.status == UNSUPPORTED
    assert result.mislabel_suspected


# ---------------------------------------------------------------------------
# 12-17: pre-existing coverage (parsing tolerance, mislabel heuristic,
# compute_claim state asymmetry, execution-gate mapping)
# ---------------------------------------------------------------------------


def test_12_unparsable_evidence_block_is_unsupported_not_a_crash():
    message = "No evidence block at all here.\n\nCLAIM: VERIFIED_REPRODUCTION\n"
    evidence = parse_evidence_block(message)
    assert not evidence.parse_ok
    result = check_evidence_grounding(_EMPTY_LIST_CANDIDATE, evidence, "some report text", {})
    assert result.status == UNSUPPORTED


def test_13_zero_contracts_genuinely_qualitative_only_is_supported():
    message = _message(
        "EVIDENCE:\n"
        "ITEM: no-crash\n"
        "KIND: qualitative\n"
        "NOTE: bare call with no exact assertion -- narrowed on purpose\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    contracts = extract_expected_contracts(_NO_CRASH_CANDIDATE)
    assert contracts == []
    result = check_evidence_grounding(_NO_CRASH_CANDIDATE, evidence, "empty input must not crash", {})
    assert result.status == SUPPORTED


def test_14_fabricated_quote_is_unsupported():
    report_text = "empty input should not crash"  # no "returns 0" anywhere
    message = _message(
        "EVIDENCE:\n"
        "ITEM: empty-list-returns-zero\n"
        "KIND: literal\n"
        "VALUE: 0\n"
        'QUOTE: "the function returns 0 for empty input"\n'
        "SOURCE: report.md\n"
        "END_EVIDENCE"
    )
    evidence = parse_evidence_block(message)
    result = check_evidence_grounding(_EMPTY_LIST_CANDIDATE, evidence, report_text, {})
    assert result.status == UNSUPPORTED
    # The fabrication is caught at item-verification time (item_checks);
    # contract_checks then correctly reports "no verified ... item matches"
    # since the fabricated item never became a verified_literal_item.
    assert any("fabricated" in c.reason for c in result.item_checks)
    assert any("no verified literal or valid derived" in c.reason for c in result.contract_checks)


def test_15_mislabel_suspected_fires_only_when_no_literal_or_derived_disclosed():
    report_text = "empty input must not crash"
    only_qualitative = _message(
        "EVIDENCE:\nITEM: x\nKIND: qualitative\nNOTE: no exact value known\nEND_EVIDENCE"
    )
    result_all_qualitative = check_evidence_grounding(
        _EMPTY_LIST_CANDIDATE, parse_evidence_block(only_qualitative), report_text, {}
    )
    assert result_all_qualitative.mislabel_suspected

    with_a_literal_attempt = _message(
        "EVIDENCE:\nITEM: x\nKIND: literal\nVALUE: 0\nQUOTE: \"nonexistent\"\nSOURCE: report.md\nEND_EVIDENCE"
    )
    result_attempted_literal = check_evidence_grounding(
        _EMPTY_LIST_CANDIDATE, parse_evidence_block(with_a_literal_attempt), report_text, {}
    )
    # Still UNSUPPORTED (the quote is fabricated) but NOT flagged as a
    # mislabel -- the agent genuinely attempted disclosure, it just failed
    # verification, which is a different failure mode.
    assert result_attempted_literal.status == UNSUPPORTED
    assert not result_attempted_literal.mislabel_suspected


def test_16_compute_claim_state_asymmetry():
    ok_execution = check_execution_before_claim(
        SandboxRun(0, "", "", timed_out=False, collection_error=False, collection_error_text="",
                   testcases=[TestCaseResult("candidate_test", "test_x", "failed")])
    )
    failing_execution = check_execution_before_claim(
        SandboxRun(0, "", "", timed_out=False, collection_error=False, collection_error_text="",
                   testcases=[TestCaseResult("candidate_test", "test_x", "passed")])
    )

    # B: grounding=None -> only ever two states, never INSUFFICIENT_EVIDENCE.
    assert compute_claim(ok_execution, None) == VERIFIED_REPRODUCTION
    assert compute_claim(failing_execution, None) == EXECUTION_FAILURE

    # C/D: a real GroundingResult can produce all three states.
    from bugproof.advanced import GroundingResult

    supported = GroundingResult(SUPPORTED, [], [], False, "", "ok")
    unsupported = GroundingResult(UNSUPPORTED, [], [], False, "", "not ok")
    assert compute_claim(ok_execution, supported) == VERIFIED_REPRODUCTION
    assert compute_claim(ok_execution, unsupported) == INSUFFICIENT_EVIDENCE
    # execution failure takes priority over grounding either way
    assert compute_claim(failing_execution, supported) == EXECUTION_FAILURE


_PAGINATION_CANDIDATE = """\
from paginator import get_page


def test_page_one_returns_first_three_items():
    items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    result = get_page(items, 1, 3)
    assert result == [1, 2, 3]
"""


def test_18_list_literal_contract_is_extracted_and_gated():
    """The real gap this correction was written for: [1, 2, 3] is an
    ast.List, not an ast.Constant -- earlier the extractor silently
    skipped it entirely (zero contracts, trivially SUPPORTED) instead of
    demanding real grounding. Found live in off_by_one_pagination's
    generated candidate during Phase 3 orchestration, fixed before any
    case was scored."""
    contracts = extract_expected_contracts(_PAGINATION_CANDIDATE)
    assert len(contracts) == 1
    assert contracts[0].kind == "equality"
    assert contracts[0].value == "[1, 2, 3]"

    # Ungrounded -> UNSUPPORTED, same as any invented scalar.
    unsupported_evidence = parse_evidence_block(
        _message("EVIDENCE:\nITEM: x\nKIND: qualitative\nNOTE: just seemed right\nEND_EVIDENCE")
    )
    result = check_evidence_grounding(_PAGINATION_CANDIDATE, unsupported_evidence, "some report text", {})
    assert result.status == UNSUPPORTED

    # Grounded with a real quote -> SUPPORTED, list-vs-list compared structurally.
    report_text = "page 1 gives me items 4, 5, 6 instead of 1, 2, 3"
    grounded_evidence = parse_evidence_block(
        _message(
            "EVIDENCE:\n"
            "ITEM: page1\n"
            "KIND: literal\n"
            "VALUE: [1, 2, 3]\n"
            'QUOTE: "instead of 1, 2, 3"\n'
            "SOURCE: report.md\n"
            "END_EVIDENCE"
        )
    )
    result2 = check_evidence_grounding(_PAGINATION_CANDIDATE, grounded_evidence, report_text, {})
    assert result2.status == SUPPORTED


def test_17_execution_gate_maps_sandbox_run_states():
    timed_out = SandboxRun(-1, "", "", timed_out=True, collection_error=False, collection_error_text="")
    assert check_execution_before_claim(timed_out).status == EXECUTION_FAILURE
    assert check_execution_before_claim(timed_out).reason == "TIMED_OUT"

    collection_error = SandboxRun(2, "", "", timed_out=False, collection_error=True, collection_error_text="boom")
    assert check_execution_before_claim(collection_error).reason == "COLLECTION_ERROR"

    passed_only = SandboxRun(
        0, "", "", timed_out=False, collection_error=False, collection_error_text="",
        testcases=[TestCaseResult("candidate_test", "test_x", "passed")],
    )
    result = check_execution_before_claim(passed_only)
    assert result.status == EXECUTION_FAILURE
    assert result.reason == "NO_FAILURE_OBSERVED"

    failed_present = SandboxRun(
        1, "", "", timed_out=False, collection_error=False, collection_error_text="",
        testcases=[TestCaseResult("candidate_test", "test_x", "failed")],
    )
    ok_result = check_execution_before_claim(failed_present)
    assert ok_result.status == OK
    assert ok_result.reason is None

    # pytest "error" status (unhandled exception, no assert involved) must
    # also count as failing -- this is what makes the narrowed "does not
    # crash" candidate style (test 13 above) actually reproduce on buggy/.
    error_present = SandboxRun(
        1, "", "", timed_out=False, collection_error=False, collection_error_text="",
        testcases=[TestCaseResult("candidate_test", "test_x", "error")],
    )
    assert check_execution_before_claim(error_present).status == OK
