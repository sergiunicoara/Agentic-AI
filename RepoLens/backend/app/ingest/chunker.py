import re
from pathlib import Path

from app.ingest import parser as ts_parser
from app.ingest.models import ChunkKind, ChunkRecord, ParsedSymbol, SourceFile
from app.tokens import count_tokens

TOKEN_CEILING = 800
_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*\S|\S)\s*$")


def module_path_for(rel_path: str) -> str:
    parts = list(Path(rel_path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _split_on_line_boundaries(
    file_path: str,
    symbol_path: str,
    kind: ChunkKind,
    start_line: int,
    lines: list[str],
) -> list[ChunkRecord]:
    """Greedily pack consecutive lines into sub-chunks, each <= TOKEN_CEILING tokens.

    Never splits mid-line, so citation ranges always stay exact.
    """
    chunks: list[ChunkRecord] = []
    current_lines: list[str] = []
    current_tokens = 0
    current_start = start_line
    line_no = start_line

    def flush(end_line: int) -> None:
        if not current_lines:
            return
        chunks.append(
            ChunkRecord(
                file_path=file_path,
                symbol_path=symbol_path,
                kind=kind,
                start_line=current_start,
                end_line=end_line,
                content="".join(current_lines),
                token_count=current_tokens,
            )
        )

    for line in lines:
        line_tokens = count_tokens(line)
        if current_lines and current_tokens + line_tokens > TOKEN_CEILING:
            flush(line_no - 1)
            current_lines = []
            current_tokens = 0
            current_start = line_no
        current_lines.append(line)
        current_tokens += line_tokens
        line_no += 1

    flush(line_no - 1)
    return chunks


def _symbol_to_chunks(file_path: str, symbol: ParsedSymbol) -> list[ChunkRecord]:
    tokens = count_tokens(symbol.code)
    if tokens <= TOKEN_CEILING:
        return [
            ChunkRecord(
                file_path=file_path,
                symbol_path=symbol.symbol_path,
                kind=symbol.kind,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                content=symbol.code,
                token_count=tokens,
                docstring_first_line=symbol.docstring_first_line,
            )
        ]
    lines = symbol.code.splitlines(keepends=True)
    return _split_on_line_boundaries(
        file_path, symbol.symbol_path, symbol.kind, symbol.start_line, lines
    )


def chunk_python_file(file_path: str, abs_path: Path) -> list[ChunkRecord]:
    module_path = module_path_for(file_path)
    symbols = ts_parser.parse_python(abs_path, module_path)

    chunks: list[ChunkRecord] = []

    for symbol in symbols:
        chunks.extend(_symbol_to_chunks(file_path, symbol))

    return chunks


def chunk_markdown_file(file_path: str, abs_path: Path) -> list[ChunkRecord]:
    """Split on headings; symbol_path is the heading breadcrumb (parent > child).

    Sections are flat (non-nested) slices of the file — each line belongs to exactly
    one section, ending where the next heading (of any level) begins — while the
    breadcrumb in symbol_path still reflects the heading hierarchy.
    """
    text = abs_path.read_bytes().decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)

    headings: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines, start=1):
        m = _HEADING_RE.match(line.rstrip("\n"))
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip()))

    if not headings:
        if text.strip():
            return _split_on_line_boundaries(file_path, "", ChunkKind.MARKDOWN_SECTION, 1, lines)
        return []

    chunks: list[ChunkRecord] = []

    first_line = headings[0][0]
    if first_line > 1:
        intro_lines = lines[: first_line - 1]
        if "".join(intro_lines).strip():
            chunks.extend(
                _split_on_line_boundaries(
                    file_path, "(intro)", ChunkKind.MARKDOWN_SECTION, 1, intro_lines
                )
            )

    breadcrumb: list[tuple[int, str]] = []
    for idx, (line_no, level, title) in enumerate(headings):
        end_line = (headings[idx + 1][0] - 1) if idx + 1 < len(headings) else len(lines)

        while breadcrumb and breadcrumb[-1][0] >= level:
            breadcrumb.pop()
        breadcrumb.append((level, title))
        symbol_path = " > ".join(t for _, t in breadcrumb)

        section_lines = lines[line_no - 1 : end_line]
        chunks.extend(
            _split_on_line_boundaries(
                file_path, symbol_path, ChunkKind.MARKDOWN_SECTION, line_no, section_lines
            )
        )

    return chunks


def chunk_file(source_file: SourceFile) -> list[ChunkRecord]:
    if source_file.language == "python":
        return chunk_python_file(source_file.path, source_file.abs_path)
    if source_file.language == "markdown":
        return chunk_markdown_file(source_file.path, source_file.abs_path)
    return []
