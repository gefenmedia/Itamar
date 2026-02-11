"""Personal Profile endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import PersonalProfile

router = APIRouter(tags=["Personal Profile"])


class ProfileUpdate(BaseModel):
    identity: Optional[str] = None
    values: Optional[str] = None
    goals: Optional[str] = None
    constraints: Optional[str] = None
    preferences: Optional[str] = None
    recurring_patterns: Optional[str] = None
    decision_history: Optional[str] = None
    vocabulary: Optional[str] = None
    raw_notes: Optional[str] = None


def profile_to_dict(p: PersonalProfile) -> dict:
    return {
        "identity": p.identity or "",
        "values": p.values or "",
        "goals": p.goals or "",
        "constraints": p.constraints or "",
        "preferences": p.preferences or "",
        "recurring_patterns": p.recurring_patterns or "",
        "decision_history": p.decision_history or "",
        "vocabulary": p.vocabulary or "",
        "raw_notes": p.raw_notes or "",
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/profile")
async def get_profile(db: AsyncSession = Depends(get_db)):
    """Get the user's personal profile."""
    result = await db.execute(select(PersonalProfile).limit(1))
    profile = result.scalar_one_or_none()

    if not profile:
        # Create default profile
        profile = PersonalProfile(id=1)
        db.add(profile)
        await db.flush()

    return profile_to_dict(profile)


@router.post("/profile/update")
async def update_profile(
    req: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update the user's personal profile.

    Only provided fields are updated; None fields are left unchanged.
    """
    result = await db.execute(select(PersonalProfile).limit(1))
    profile = result.scalar_one_or_none()

    if not profile:
        profile = PersonalProfile(id=1)
        db.add(profile)

    update_data = req.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(profile, key, value)

    await db.flush()
    return profile_to_dict(profile)
