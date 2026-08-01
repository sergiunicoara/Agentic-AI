import re

from app.retrieval.models import Citation, RetrievedChunk

_CITATION_RE = re.compile(r"\[([^\[\]:]+):(\d+)-(\d+)\]")


def extract_citations(answer: str) -> list[Citation]:
    """Extract every [path/to/file:start-end] token from generated answer text."""
    citations = []
    for match in _CITATION_RE.finditer(answer):
        file_path, start, end = match.groups()
        citations.append(Citation(file=file_path, start_line=int(start), end_line=int(end)))
    return citations


def validate_citations(
    citations: list[Citation], used_chunks: list[RetrievedChunk]
) -> list[Citation]:
    """Keep only citations whose exact file and line range were in model context."""
    allowed = {
        (chunk.file_path, chunk.start_line, chunk.end_line) for chunk in used_chunks
    }
    return [
        citation
        for citation in citations
        if (citation.file, citation.start_line, citation.end_line) in allowed
    ]
