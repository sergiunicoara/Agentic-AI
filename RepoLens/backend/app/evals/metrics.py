from app.retrieval.models import Citation, RetrievedChunk


def retrieval_hit(expected_files: list[str], retrieved: list[RetrievedChunk]) -> bool | None:
    """True if any expected file appears among the retrieved chunks' file paths.
    A question with no expected_files is excluded from the hit-rate denominator."""
    if not expected_files:
        return None
    retrieved_paths = {r.file_path for r in retrieved}
    return any(f in retrieved_paths for f in expected_files)


def citation_precision(
    citations: list[Citation],
    expected_symbols: list[str],
    included_chunks: list[RetrievedChunk],
) -> float | None:
    """Fraction of citations whose [file:start-end] range falls inside a chunk that
    was actually included in the assembled context AND mentions an expected symbol.
    Returns None when there's nothing to score (no citations, or no expected symbols
    to check against) rather than a misleading 0.0 or 1.0."""
    if not citations or not expected_symbols:
        return None

    correct = 0
    for citation in citations:
        match = any(
            chunk.file_path == citation.file
            and chunk.start_line <= citation.start_line
            and citation.end_line <= chunk.end_line
            and any(sym in chunk.symbol_path or sym in chunk.content for sym in expected_symbols)
            for chunk in included_chunks
        )
        if match:
            correct += 1
    return correct / len(citations)


def citation_validity(
    citations: list[Citation], included_chunks: list[RetrievedChunk]
) -> float:
    """Fraction of generated citations that match an included chunk exactly."""
    if not citations:
        return 0.0
    allowed = {
        (chunk.file_path, chunk.start_line, chunk.end_line) for chunk in included_chunks
    }
    return sum(
        (citation.file, citation.start_line, citation.end_line) in allowed
        for citation in citations
    ) / len(citations)


def answer_mentions(answer: str, required: list[str]) -> bool:
    """Case-insensitive answer correctness check for the golden-set requirements."""
    normalized = answer.casefold()
    return all(term.casefold() in normalized for term in required)
