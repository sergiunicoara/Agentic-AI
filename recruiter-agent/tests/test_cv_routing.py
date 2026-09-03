"""
Regression tests for CV question routing.

Two audits found real production bugs here that no test covered:

1. app/agent.py — CV_QUERY_KEYWORDS matched raw substrings with no word
   boundaries, so "city" fired inside "capacity planning", "based" inside
   "cloud-based", "address" inside "address technical debt". Because the
   gate runs before criteria parsing, a recruiter answering the agent's own
   "what are your criteria?" question got their answer swallowed into CV
   Q&A and the criteria silently dropped — a deterministic infinite loop.

2. app/cv_rag.py — _direct_facts_answer had the same substring class, so
   "capacity planning" cascaded through both layers and was answered with
   the candidate's home city.

The tables below are the exact cases used to verify those fixes.
"""
from __future__ import annotations

import pytest

from app.agent import (
    _looks_like_cv_question,
    _explicit_candidate_question,
    agent_turn,
)
from app.cv_rag import CVRAG
from app.models.state import State


# ---------------------------------------------------------------------------
# Routing gate — must NOT route to CV RAG
# ---------------------------------------------------------------------------

NOT_CV_QUESTIONS = [
    # 'based' inside a compound / as a preposition
    "We need someone with cloud-based infrastructure experience",
    "The role is based on our new platform team",
    "Java-based microservices",
    "location-based services experience",
    # 'city' inside capacity / velocity / simplicity
    "Experience with capacity planning is required",
    "They should improve team velocity",
    "Looking at simplicity of design",
    # 'address' as a verb
    "We need to address scalability challenges",
    # 'contact' in a domain term
    "Experience in a contact center environment",
    # 'degree' as a figure of speech
    "To a degree, yes",
    # 'location' in ordinary prose
    "The role requires multi-location coordination",
]


@pytest.mark.parametrize("msg", NOT_CV_QUESTIONS)
def test_ordinary_recruiter_prose_does_not_route_to_cv(msg):
    """Substring matches inside unrelated words must not trigger CV RAG."""
    assert _looks_like_cv_question(msg) is False, (
        f"{msg!r} was misrouted to CV RAG"
    )


# ---------------------------------------------------------------------------
# Routing gate — MUST route to CV RAG
# ---------------------------------------------------------------------------

CV_QUESTIONS = [
    # natural phrasings the old keyword list missed entirely
    "Does he have experience with Kubernetes?",
    "Has he worked with production RAG systems?",
    "Does he know Python?",
    "What did he do at Alcatel Lucent?",
    "Where did he study?",
    "Tell me about his previous roles",
    "Is he certified in AWS?",
    "What languages does he speak?",
    "Can he work remotely?",
    "How long was he at his last job?",
    # location / degree: no longer keywords, must match via question shape
    "What is his location?",
    "Where is he based?",
    "What city is he in?",
    "What degree does he have?",
    "Tell me about his degree",
    # plain keyword hits
    "What is his phone number?",
    "What are his certifications?",
    "Can you share his CV?",
]


@pytest.mark.parametrize("msg", CV_QUESTIONS)
def test_real_cv_questions_route_to_cv(msg):
    assert _looks_like_cv_question(msg) is True, (
        f"{msg!r} did not reach CV RAG"
    )


# ---------------------------------------------------------------------------
# Hiring-marker interaction
# ---------------------------------------------------------------------------

HIRING_REQUESTS = [
    "I'm hiring a Senior ML Engineer with RAG experience",
    "We are looking for a Data Scientist",
    "I need an AI Engineer with 5 years of experience",
]


@pytest.mark.parametrize("msg", HIRING_REQUESTS)
def test_hiring_requests_are_not_cv_questions(msg):
    assert _looks_like_cv_question(msg) is False


HIRING_PLUS_QUESTION = [
    "I'm hiring an ML engineer - what is his phone number?",
    "We are hiring - can you send me his email?",
]


@pytest.mark.parametrize("msg", HIRING_PLUS_QUESTION)
def test_explicit_question_overrides_hiring_marker(msg):
    """A hiring marker must not suppress an explicit question about the candidate."""
    assert _looks_like_cv_question(msg) is True


def test_explicit_candidate_question_requires_both_signals():
    # interrogative + candidate reference
    assert _explicit_candidate_question("what is his phone number?") is True
    # interrogative, no candidate reference
    assert _explicit_candidate_question("what are your criteria?") is False
    # candidate reference, not interrogative (JD prose)
    assert _explicit_candidate_question("he must have 5 years of experience") is False


# ---------------------------------------------------------------------------
# The bug that mattered: criteria collection must not be hijacked
# ---------------------------------------------------------------------------

CRITERIA_WITH_POISONED_SUBSTRINGS = [
    "cloud-based architecture, ownership",   # 'based'
    "capacity planning, leadership",         # 'city'
    "modern technologies, communication",    # 'technologies'
    "location-based services, ownership",    # 'location' + 'based'
]


@pytest.mark.parametrize("criteria_msg", CRITERIA_WITH_POISONED_SUBSTRINGS)
def test_criteria_answer_is_not_swallowed_by_cv_gate(criteria_msg):
    """
    Regression: the agent asks for criteria, the recruiter answers, and the
    answer must be recorded — not diverted into CV Q&A leaving criteria empty
    (which looped forever, since retrying produced the same diversion).
    """
    state = State()
    agent_turn(state, "I need a Senior ML Engineer")
    assert state.role, "role should be set before the criteria stage"
    assert state.criteria == [], "agent should be awaiting criteria"

    agent_turn(state, criteria_msg)

    assert state.criteria, (
        f"criteria {criteria_msg!r} were silently discarded"
    )


def test_criteria_stage_does_not_loop():
    """Retrying the same criteria must not reproduce the same non-answer."""
    state = State()
    agent_turn(state, "I need a Senior ML Engineer")
    agent_turn(state, "cloud-based architecture, ownership")
    assert state.criteria, "first attempt should already be accepted"


def test_cv_question_still_interrupts_criteria_collection():
    """
    CV Q&A is documented as available anytime — an explicit question must
    still work mid-criteria, and must not consume the criteria step.
    """
    state = State()
    agent_turn(state, "I need a Senior ML Engineer")

    out = agent_turn(state, "what is his phone number?")
    assert "phone" in out["reply"].lower()
    assert state.criteria == [], "CV answer must not advance the criteria stage"

    agent_turn(state, "production RAG, ownership")
    assert state.criteria == ["production_rag", "ownership"]


# ---------------------------------------------------------------------------
# cv_rag direct-fact routing (no network — regex/extractor layer only)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rag():
    return CVRAG()


def test_capacity_does_not_trigger_location_branch(rag):
    """'capacity' contains 'city' — must not be answered with the home city."""
    assert rag._direct_facts_answer("capacity planning, leadership") is None


def test_cloud_based_does_not_trigger_location_branch(rag):
    assert rag._direct_facts_answer("cloud-based architecture") is None


def test_real_location_question_still_answered(rag):
    answer = rag._direct_facts_answer("Where is he based?")
    assert answer is not None
    assert "Timisoara" in answer


def test_open_experience_question_falls_through_to_retrieval(rag):
    """
    A bare 'experience' substring used to swallow these into a canned
    'multiple years of experience' answer that never reached retrieval.
    """
    assert rag._direct_facts_answer("Does he have experience with Kubernetes?") is None
    assert rag._direct_facts_answer("Does he have production RAG experience?") is None


def test_explicit_years_question_handled_directly(rag):
    """
    The CV states no explicit 'Years of experience:' figure, so this must
    return None (fall through to retrieval) rather than inventing a number.
    """
    assert rag._direct_facts_answer("How many years of experience does he have?") is None


def test_direct_fact_extractors_still_work(rag):
    phone = rag._direct_facts_answer("What is his phone number?")
    assert phone and "+40" in phone

    email = rag._direct_facts_answer("What is his email?")
    assert email and "@" in email

    edu = rag._direct_facts_answer("What is his education?")
    assert edu and "Master" in edu

    certs = rag._direct_facts_answer("What are his certifications?")
    assert certs and "AWS Certified AI Practitioner" in certs


def test_dummy_fallback_exposes_query_stream():
    """
    get_cv_rag()'s Dummy fallback previously defined only query(), so the
    voice path (query_stream only) crashed with AttributeError instead of
    degrading gracefully.
    """
    import app.cv_rag as m

    saved = m._rag
    try:
        m._rag = None
        original_init = m.CVRAG.__init__

        def _boom(self):
            raise RuntimeError("simulated cv.txt failure")

        m.CVRAG.__init__ = _boom
        try:
            dummy = m.get_cv_rag()
            assert hasattr(dummy, "query")
            assert hasattr(dummy, "query_stream")
        finally:
            m.CVRAG.__init__ = original_init
    finally:
        m._rag = saved
