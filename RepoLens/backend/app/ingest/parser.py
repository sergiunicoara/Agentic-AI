from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from app.ingest.models import ChunkKind, ParsedSymbol

_LANGUAGE = Language(tspython.language())
_parser = Parser(_LANGUAGE)


def _line_range(node: Node) -> tuple[int, int]:
    """1-indexed, inclusive [start_line, end_line] for a tree-sitter node."""
    return node.start_point[0] + 1, node.end_point[0] + 1


def _slice_lines(source_lines: list[str], start_line: int, end_line: int) -> str:
    return "".join(source_lines[start_line - 1 : end_line])


def _content_range(source_lines: list[str], start_line: int, end_line: int) -> tuple[int, int]:
    while start_line <= end_line and not source_lines[start_line - 1].strip():
        start_line += 1
    while end_line >= start_line and not source_lines[end_line - 1].strip():
        end_line -= 1
    return start_line, end_line


def _docstring_first_line(node: Node, source: bytes) -> str:
    body = node.child_by_field_name("body")
    if body is None or body.named_child_count == 0:
        return ""
    first_stmt = body.named_children[0]
    if first_stmt.type != "expression_statement" or first_stmt.named_child_count == 0:
        return ""
    expr = first_stmt.named_children[0]
    if expr.type != "string":
        return ""
    content_node = next((c for c in expr.children if c.type == "string_content"), None)
    if content_node is None:
        return ""
    text = source[content_node.start_byte : content_node.end_byte].decode("utf-8", errors="replace")
    text = text.strip()
    return text.splitlines()[0].strip() if text else ""


def _symbol_path(*parts: str | None) -> str:
    return ".".join(p for p in parts if p)


def _definition_node(node: Node) -> Node | None:
    if node.type == "decorated_definition":
        return node.child_by_field_name("definition")
    if node.type in {"function_definition", "class_definition"}:
        return node
    return None


def _name(node: Node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    return (
        source[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="replace")
        if name_node
        else "<anonymous>"
    )


def _is_method(node: Node) -> bool:
    definition = _definition_node(node)
    return definition is not None and definition.type == "function_definition"


def parse_python(abs_path: Path, module_path: str) -> list[ParsedSymbol]:
    """Parse a Python file into top-level function/class/method symbols.

    Every returned symbol's `code` is reconstructed by slicing the source file's
    lines at [start_line, end_line] (1-indexed, inclusive) — never by tree-sitter
    byte ranges directly — so citations are guaranteed to reproduce the source
    verbatim.
    """
    source = abs_path.read_bytes()
    source_text = source.decode("utf-8", errors="replace")
    source_lines = source_text.splitlines(keepends=True)
    tree = _parser.parse(source)
    root = tree.root_node

    symbols: list[ParsedSymbol] = []

    def make_symbol(
        node: Node, symbol_path: str, kind: ChunkKind, doc_node: Node | None = None
    ) -> ParsedSymbol:
        start, end = _line_range(node)
        return ParsedSymbol(
            symbol_path=symbol_path,
            kind=kind,
            start_line=start,
            end_line=end,
            code=_slice_lines(source_lines, start, end),
            docstring_first_line=_docstring_first_line(doc_node or node, source),
        )

    # Module-level definitions may be decorated. Emit the gaps between them as
    # module chunks so imports, assignments, and statements after definitions remain indexed.
    module_definitions = [node for node in root.named_children if _definition_node(node)]
    cursor = 1
    module_segment = 1
    for node in module_definitions:
        start, _ = _line_range(node)
        if cursor < start:
            end = start - 1
            content_start, content_end = _content_range(source_lines, cursor, end)
            if content_start <= content_end:
                suffix = "" if module_segment == 1 else f"::<module-body-{module_segment}>"
                symbols.append(
                    ParsedSymbol(
                        symbol_path=f"{module_path}{suffix}",
                        kind=ChunkKind.MODULE,
                        start_line=content_start,
                        end_line=content_end,
                        code=_slice_lines(source_lines, content_start, content_end),
                    )
                )
                module_segment += 1
        cursor = _line_range(node)[1] + 1
    if cursor <= len(source_lines):
        content_start, content_end = _content_range(source_lines, cursor, len(source_lines))
    else:
        content_start, content_end = cursor, cursor - 1
    if content_start <= content_end:
        suffix = "" if module_segment == 1 else f"::<module-body-{module_segment}>"
        symbols.append(
            ParsedSymbol(
                symbol_path=f"{module_path}{suffix}",
                kind=ChunkKind.MODULE,
                start_line=content_start,
                end_line=content_end,
                code=_slice_lines(source_lines, content_start, content_end),
            )
        )

    for node in module_definitions:
        definition = _definition_node(node)
        if definition is None:
            continue
        if definition.type == "function_definition":
            name = _name(definition, source)
            symbols.append(
                make_symbol(
                    node, _symbol_path(module_path, name), ChunkKind.FUNCTION, definition
                )
            )
        elif definition.type == "class_definition":
            class_name = _name(definition, source)
            class_start, class_end = _line_range(node)
            body = definition.child_by_field_name("body")
            members = list(body.named_children) if body else []
            methods = [m for m in members if _is_method(m)]

            cursor = class_start
            body_segment = 1
            for member in methods:
                member_start, member_end = _line_range(member)
                if cursor < member_start:
                    content_start, content_end = _content_range(
                        source_lines, cursor, member_start - 1
                    )
                    if content_start <= content_end:
                        suffix = "" if body_segment == 1 else f".__class_body_{body_segment}"
                        symbols.append(
                            ParsedSymbol(
                                symbol_path=_symbol_path(module_path, class_name) + suffix,
                                kind=ChunkKind.CLASS,
                                start_line=content_start,
                                end_line=content_end,
                                code=_slice_lines(source_lines, content_start, content_end),
                                docstring_first_line=_docstring_first_line(definition, source),
                            )
                        )
                        body_segment += 1
                cursor = member_end + 1
            if cursor <= class_end:
                content_start, content_end = _content_range(source_lines, cursor, class_end)
            else:
                content_start, content_end = cursor, cursor - 1
            if content_start <= content_end:
                suffix = "" if body_segment == 1 else f".__class_body_{body_segment}"
                symbols.append(
                    ParsedSymbol(
                        symbol_path=_symbol_path(module_path, class_name) + suffix,
                        kind=ChunkKind.CLASS,
                        start_line=content_start,
                        end_line=content_end,
                        code=_slice_lines(source_lines, content_start, content_end),
                        docstring_first_line=_docstring_first_line(definition, source),
                    )
                )

            for member in methods:
                member_definition = _definition_node(member)
                assert member_definition is not None
                symbols.append(
                    make_symbol(
                        member,
                        _symbol_path(module_path, class_name, _name(member_definition, source)),
                        ChunkKind.METHOD,
                        member_definition,
                    )
                )

    return symbols
