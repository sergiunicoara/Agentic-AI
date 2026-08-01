from app.retrieval.models import RetrievedChunk
from app.tokens import count_tokens

TOKEN_BUDGET = 6000


def render_chunk(chunk: RetrievedChunk) -> str:
    header = f"[{chunk.file_path}:{chunk.start_line}-{chunk.end_line}]"
    return f"{header}\n{chunk.content}"


def assemble_context(chunks: list[RetrievedChunk]) -> tuple[str, list[RetrievedChunk]]:
    """Greedily include whole chunks, in rank order, until the next one would exceed
    TOKEN_BUDGET. Never truncates a chunk mid-content — a partial chunk would break the
    citation-fidelity guarantee. Returns (rendered_context, chunks_actually_included)."""
    included: list[RetrievedChunk] = []
    blocks: list[str] = []
    total_tokens = 0

    for chunk in chunks:
        block = render_chunk(chunk)
        block_tokens = count_tokens(block)
        if included and total_tokens + block_tokens > TOKEN_BUDGET:
            break
        included.append(chunk)
        blocks.append(block)
        total_tokens += block_tokens

    return "\n\n".join(blocks), included
