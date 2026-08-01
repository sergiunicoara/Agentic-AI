import uuid

from app.evals.metrics import answer_mentions, citation_precision, citation_validity, retrieval_hit
from app.retrieval.models import Citation, RetrievedChunk


def _chunk(file_path: str, start: int, end: int, symbol_path: str = "a.foo") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        file_path=file_path,
        symbol_path=symbol_path,
        kind="function",
        start_line=start,
        end_line=end,
        content="pass",
        token_count=1,
        distance=0.0,
    )


def test_retrieval_hit_true_when_expected_file_present() -> None:
    retrieved = [_chunk("a.py", 1, 5), _chunk("b.py", 1, 5)]
    assert retrieval_hit(["b.py"], retrieved) is True


def test_retrieval_hit_false_when_expected_file_absent() -> None:
    retrieved = [_chunk("a.py", 1, 5)]
    assert retrieval_hit(["b.py"], retrieved) is False


def test_retrieval_hit_excludes_questions_without_expected_files() -> None:
    assert retrieval_hit([], []) is None


def test_citation_precision_none_when_no_citations() -> None:
    assert citation_precision([], ["foo"], []) is None


def test_citation_precision_none_when_no_expected_symbols() -> None:
    citations = [Citation(file="a.py", start_line=1, end_line=5)]
    assert citation_precision(citations, [], []) is None


def test_citation_precision_correct_match() -> None:
    included = [_chunk("a.py", 1, 10, symbol_path="a.foo")]
    citations = [Citation(file="a.py", start_line=1, end_line=10)]
    assert citation_precision(citations, ["foo"], included) == 1.0


def test_citation_precision_partial_match() -> None:
    included = [_chunk("a.py", 1, 10, symbol_path="a.foo")]
    citations = [
        Citation(file="a.py", start_line=1, end_line=10),
        Citation(file="b.py", start_line=1, end_line=10),
    ]
    assert citation_precision(citations, ["foo"], included) == 0.5


def test_citation_precision_range_outside_chunk_is_wrong() -> None:
    included = [_chunk("a.py", 1, 10, symbol_path="a.foo")]
    citations = [Citation(file="a.py", start_line=20, end_line=25)]
    assert citation_precision(citations, ["foo"], included) == 0.0


def test_answer_mentions_requires_every_expected_term() -> None:
    assert answer_mentions("The User has a name and email.", ["user", "email"])
    assert not answer_mentions("The User has a name.", ["user", "email"])


def test_citation_validity_requires_exact_included_range() -> None:
    included = [_chunk("a.py", 1, 10)]
    assert citation_validity([Citation(file="a.py", start_line=1, end_line=10)], included) == 1.0
    assert citation_validity([Citation(file="a.py", start_line=1, end_line=9)], included) == 0.0
