from pathlib import Path

from app.ingest import parser
from app.ingest.models import ChunkKind

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_parse_models_py_extracts_expected_symbols() -> None:
    symbols = parser.parse_python(FIXTURE / "pkg" / "models.py", "pkg.models")
    by_path = {s.symbol_path: s for s in symbols}

    assert by_path["pkg.models.User"].kind == ChunkKind.CLASS
    assert by_path["pkg.models.User.__init__"].kind == ChunkKind.METHOD
    assert by_path["pkg.models.User.display_name"].kind == ChunkKind.METHOD
    assert (
        by_path["pkg.models.User.display_name"].docstring_first_line
        == "Return a human-friendly display name."
    )
    create_user = by_path["pkg.models.create_user"]
    assert create_user.kind == ChunkKind.FUNCTION
    assert create_user.docstring_first_line == "Factory function for building a User."


def test_class_chunk_excludes_method_bodies() -> None:
    symbols = parser.parse_python(FIXTURE / "pkg" / "models.py", "pkg.models")
    by_path = {s.symbol_path: s for s in symbols}

    class_symbol = by_path["pkg.models.User"]
    init_symbol = by_path["pkg.models.User.__init__"]

    assert class_symbol.end_line < init_symbol.start_line


def test_decorated_async_function_and_class_keep_exact_ranges() -> None:
    symbols = parser.parse_python(FIXTURE / "pkg" / "routes.py", "pkg.routes")
    by_path = {symbol.symbol_path: symbol for symbol in symbols}

    route = by_path["pkg.routes.list_users"]
    assert route.kind == ChunkKind.FUNCTION
    assert route.start_line == 4
    assert route.end_line == 6
    assert '@router.get("/users")' in route.code

    user = by_path["pkg.routes.User"]
    assert user.kind == ChunkKind.CLASS
    assert user.start_line == 9
    assert user.end_line == 11
    assert "@dataclass" in user.code

    display = by_path["pkg.routes.User.display"]
    assert display.start_line == 12
    assert display.end_line == 13

    class_body = by_path["pkg.routes.User.__class_body_2"]
    assert class_body.start_line == 15
    assert class_body.end_line == 15
    assert "DEFAULT_ROLE" in class_body.code

    module_tail = by_path["pkg.routes::<module-body-2>"]
    assert module_tail.start_line == 18
    assert module_tail.end_line == 18
