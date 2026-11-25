from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import EngineDep, OptionalUserId, QdrantDep, SettingsDep
from app.schemas.health import HealthReport, PublicHealth
from app.services.health import collect_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthReport | PublicHealth)
async def health(
    engine: EngineDep, qdrant: QdrantDep, settings: SettingsDep, user_id: OptionalUserId
) -> HealthReport | PublicHealth:
    """Service status for the system-status page (signed in). Without a session: only
    `{"status": "ok"}`, meaning the API process is up (M16).

    Always HTTP 200: `status` is "degraded" when a service is down, and each service reports
    its own status, latency and a short error. The status page can then show *which* part
    failed instead of a generic error.
    """
    if user_id is None:
        return PublicHealth()
    return await collect_health(engine, qdrant, settings)
