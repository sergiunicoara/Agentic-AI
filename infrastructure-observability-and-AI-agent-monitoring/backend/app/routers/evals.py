import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.eval_ import EvalResult, EvalRun
from app.services.auth_service import get_current_user, require_role

router = APIRouter(prefix="/evals", tags=["evals"])


class EvalRunCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trace_id: Optional[str] = None


class EvalResultCreate(BaseModel):
    metric: str
    score: float
    details: dict = {}


class EvalRunOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    trace_id: Optional[str]
    created_by: str
    status: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[EvalRunOut])
async def list_runs(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    result = await db.execute(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(100))
    return list(result.scalars().all())


@router.post("", response_model=EvalRunOut, status_code=201)
async def create_run(
    body: EvalRunCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("developer")),
):
    run = EvalRun(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        trace_id=body.trace_id,
        created_by=user["sub"],
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/{run_id}/results", status_code=201)
async def add_result(
    run_id: str,
    body: EvalResultCreate,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_role("developer")),
):
    result_row = EvalResult(
        id=str(uuid.uuid4()),
        run_id=run_id,
        metric=body.metric,
        score=body.score,
        details=body.details,
    )
    db.add(result_row)
    await db.commit()
    return {"id": result_row.id}


@router.delete("/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_role("developer")),
):
    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(run)
    await db.commit()
