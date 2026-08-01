import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.browse.models import FileContent, RepoSummary, TreeNode
from app.browse.repo_map import build_repo_map, get_file_content, list_repos
from app.db import get_session

router = APIRouter()


@router.get("/repos")
async def repos(session: AsyncSession = Depends(get_session)) -> list[RepoSummary]:
    return await list_repos(session)


@router.get("/repo-map")
async def repo_map(
    repo_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[TreeNode]:
    return await build_repo_map(session, repo_id)


@router.get("/file")
async def file(
    repo_id: uuid.UUID, path: str, session: AsyncSession = Depends(get_session)
) -> FileContent:
    result = await get_file_content(session, repo_id, path)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No file at path {path!r} for this repo")
    return result
