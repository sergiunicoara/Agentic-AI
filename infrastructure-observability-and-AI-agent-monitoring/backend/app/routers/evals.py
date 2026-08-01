import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.eval_ import EvalResult, EvalRun
from app.services.abac import check_span_access
from app.services.auth_service import get_current_user, require_role
from app.services.trace_service import get_trace_with_spans

router = APIRouter(prefix="/evals", tags=["evals"])


class EvalRunCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trace_id: Optional[str] = None


class EvalResultCreate(BaseModel):
    metric: str
    score: float = Field(ge=-1_000_000, le=1_000_000)
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
    query = select(EvalRun).order_by(EvalRun.created_at.desc()).limit(100)
    if _user.get("role") != "admin":
        query = query.where(EvalRun.created_by == str(_user.get("sub")))
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=EvalRunOut, status_code=201)
async def create_run(
    body: EvalRunCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("developer")),
):
    if body.trace_id:
        trace = await get_trace_with_spans(body.trace_id, db)
        if not trace:
            raise HTTPException(status_code=404, detail="Trace not found")
        if not any(
            check_span_access(
                user,
                {
                    "data_sensitivity": (span.attributes or {}).get("data_sensitivity", "internal"),
                    "owner_email": (span.attributes or {}).get("owner_email", ""),
                },
                "read",
            )
            for span in trace.spans
        ):
            raise HTTPException(status_code=403, detail="Insufficient clearance for trace")

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
    user: dict = Depends(require_role("developer")),
):
    run_result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    if user.get("role") != "admin" and run.created_by != str(user.get("sub")):
        raise HTTPException(status_code=403, detail="Not the eval owner")
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
    user: dict = Depends(require_role("developer")),
):
    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    if user.get("role") != "admin" and run.created_by != str(user.get("sub")):
        raise HTTPException(status_code=403, detail="Not the eval owner")
    await db.delete(run)
    await db.commit()
