"""Restudy endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import RestudyReport
from app.services.restudy import run_restudy

router = APIRouter(tags=["Restudy"])


@router.post("/restudy/run")
async def trigger_restudy(db: AsyncSession = Depends(get_db)):
    """Trigger a manual restudy cycle."""
    result = await run_restudy(db)
    return result


@router.get("/restudy/reports")
async def list_restudy_reports(db: AsyncSession = Depends(get_db)):
    """List all restudy reports."""
    result = await db.execute(
        select(RestudyReport).order_by(RestudyReport.created_at.desc()).limit(20)
    )
    reports = result.scalars().all()

    return [
        {
            "id": str(r.id),
            "report_text": r.report_text,
            "top_principles": r.top_principles,
            "contradictions": r.contradictions,
            "weak_support": r.weak_support,
            "scenario_results": r.scenario_results,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]
