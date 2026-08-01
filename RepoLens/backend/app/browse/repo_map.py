import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.browse.models import FileContent, RepoSummary, SymbolNode, TreeNode
from app.tables import chunks, files, repos


async def list_repos(session: AsyncSession) -> list[RepoSummary]:
    result = await session.execute(
        select(
            repos.c.id,
            repos.c.source_url,
            repos.c.file_count,
            repos.c.chunk_count,
            repos.c.indexed_at,
        ).order_by(repos.c.indexed_at.desc().nullslast())
    )
    return [
        RepoSummary(
            id=row.id,
            source_url=row.source_url,
            file_count=row.file_count,
            chunk_count=row.chunk_count,
            indexed_at=row.indexed_at.isoformat() if row.indexed_at else None,
        )
        for row in result
    ]


async def get_file_content(
    session: AsyncSession, repo_id: uuid.UUID, path: str
) -> FileContent | None:
    result = await session.execute(
        select(files.c.content, files.c.language).where(
            files.c.repo_id == repo_id, files.c.path == path
        )
    )
    row = result.first()
    if row is None:
        return None
    return FileContent(path=path, content=row.content, language=row.language)


class _Dir:
    def __init__(self) -> None:
        self.subdirs: dict[str, _Dir] = {}
        self.files: list[TreeNode] = []


def _dir_to_nodes(d: _Dir) -> list[TreeNode]:
    nodes = [
        TreeNode(type="dir", name=name, children=_dir_to_nodes(sub))
        for name, sub in sorted(d.subdirs.items())
    ]
    nodes.extend(sorted(d.files, key=lambda f: f.name))
    return nodes


async def build_repo_map(session: AsyncSession, repo_id: uuid.UUID) -> list[TreeNode]:
    """Directory tree of files, each carrying its top-level symbols (methods nested
    under their parent class by symbol_path prefix). Module-preamble chunks are
    excluded — they aren't a distinct browsable symbol."""
    file_rows = (
        await session.execute(select(files.c.id, files.c.path).where(files.c.repo_id == repo_id))
    ).all()
    file_id_to_path = {row.id: row.path for row in file_rows}

    chunk_rows = []
    if file_id_to_path:
        chunk_rows = (
            await session.execute(
                select(
                    chunks.c.file_id,
                    chunks.c.symbol_path,
                    chunks.c.kind,
                    chunks.c.start_line,
                    chunks.c.end_line,
                )
                .where(chunks.c.file_id.in_(file_id_to_path.keys()), chunks.c.kind != "module")
                .order_by(chunks.c.start_line)
            )
        ).all()

    symbols_by_file: dict[uuid.UUID, list] = {fid: [] for fid in file_id_to_path}
    for row in chunk_rows:
        symbols_by_file[row.file_id].append(row)

    root = _Dir()
    for file_id, path in file_id_to_path.items():
        top_level: dict[str, SymbolNode] = {}
        methods: list[SymbolNode] = []

        for row in symbols_by_file[file_id]:
            node = SymbolNode(
                symbol_path=row.symbol_path,
                kind=row.kind,
                start_line=row.start_line,
                end_line=row.end_line,
            )
            if row.kind == "method":
                methods.append(node)
            else:
                top_level[row.symbol_path] = node

        for method_node in methods:
            parent_path = method_node.symbol_path.rsplit(".", 1)[0]
            parent = top_level.get(parent_path)
            if parent:
                parent.children.append(method_node)
            else:
                # orphan method (parent class chunk missing) — surface it rather than drop it
                top_level[method_node.symbol_path] = method_node

        parts = path.split("/")
        current = root
        for segment in parts[:-1]:
            current = current.subdirs.setdefault(segment, _Dir())
        current.files.append(
            TreeNode(type="file", name=parts[-1], path=path, symbols=list(top_level.values()))
        )

    return _dir_to_nodes(root)
