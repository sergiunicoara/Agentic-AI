from pathlib import Path

import pytest
from sqlalchemy import delete

from app.browse.repo_map import build_repo_map
from app.db import session_factory
from app.ingest import chunker, store, walker
from app.ingest.embedder import FakeEmbedder, context_header
from app.tables import repos as repos_table

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
SOURCE_URL = "test://browse-repo-map"


@pytest.fixture(autouse=True)
async def _clean_db():
    # repos.id -> files.repo_id -> chunks.file_id all cascade on delete, so scoping
    # this to our own source_url is enough — never blanket-delete files/chunks,
    # that would wipe every other repo's ingested data too.
    async with session_factory()() as session:
        await session.execute(delete(repos_table).where(repos_table.c.source_url == SOURCE_URL))
        await session.commit()
    yield


async def _ingest_fixture(embedder):
    source_files = walker.walk(FIXTURE)
    async with session_factory()() as session:
        repo_id = await store.get_or_create_repo(session, SOURCE_URL)
        for source_file in source_files:
            text = source_file.abs_path.read_bytes().decode("utf-8")
            content_hash = store.compute_content_hash(text)
            records = chunker.chunk_file(source_file)
            embeddings = []
            if records:
                inputs = [
                    context_header(
                        SOURCE_URL,
                        source_file.path,
                        c.symbol_path,
                        c.docstring_first_line,
                        c.content,
                    )
                    for c in records
                ]
                embeddings = await embedder.embed_batch(inputs)
            await store.replace_file(
                session,
                repo_id,
                source_file.path,
                source_file.language,
                text.count("\n") + 1,
                content_hash,
                text,
                records,
                embeddings,
            )
        await store.finalize_repo_counts(session, repo_id)
        await session.commit()
    return repo_id


def _find(nodes, name):
    return next((n for n in nodes if n.name == name), None)


async def test_repo_map_builds_directory_tree_with_files_and_symbols():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)

    async with session_factory()() as session:
        tree = await build_repo_map(session, repo_id)

    top_names = {n.name for n in tree}
    assert "pkg" in top_names
    assert "README.md" in top_names

    pkg_dir = _find(tree, "pkg")
    assert pkg_dir.type == "dir"

    models_file = _find(pkg_dir.children, "models.py")
    assert models_file is not None
    assert models_file.type == "file"
    assert models_file.path == "pkg/models.py"


async def test_repo_map_nests_methods_under_class():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)

    async with session_factory()() as session:
        tree = await build_repo_map(session, repo_id)

    pkg_dir = _find(tree, "pkg")
    models_file = _find(pkg_dir.children, "models.py")

    user_symbol = next(s for s in models_file.symbols if s.symbol_path == "pkg.models.User")
    assert user_symbol.kind == "class"
    method_paths = {c.symbol_path for c in user_symbol.children}
    assert method_paths == {"pkg.models.User.__init__", "pkg.models.User.display_name"}

    create_user = next(
        s for s in models_file.symbols if s.symbol_path == "pkg.models.create_user"
    )
    assert create_user.kind == "function"
    assert create_user.children == []


async def test_repo_map_excludes_module_preamble_chunks():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)

    async with session_factory()() as session:
        tree = await build_repo_map(session, repo_id)

    pkg_dir = _find(tree, "pkg")
    models_file = _find(pkg_dir.children, "models.py")

    kinds = {s.kind for s in models_file.symbols}
    assert "module" not in kinds
