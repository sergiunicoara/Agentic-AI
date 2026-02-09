from __future__ import annotations

def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    text = (text or "").strip()
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks
