"""GET /api/stats: the dashboard's numbers for the signed-in user (M16)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserId, ReadDbSession
from app.schemas.stats import UserStats
from app.services.stats import user_stats

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=UserStats)
def stats(user_id: CurrentUserId, db: ReadDbSession) -> UserStats:
    """Your knowledge bases, documents by status, indexed chunks, uploaded bytes,
    conversations, and questions (all time and in the last 7 days). One query."""
    return UserStats(**user_stats(db, user_id))
