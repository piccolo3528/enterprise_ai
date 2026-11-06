from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import EngineDep, QdrantDep, SettingsDep
from app.schemas.health import HealthReport
from app.services.health import collect_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthReport)
async def health(engine: EngineDep, qdrant: QdrantDep, settings: SettingsDep) -> HealthReport:
    """Service status for the system-status page.

    Always HTTP 200: `status` is "degraded" when a service is down, and each service reports
    its own status, latency and a short error. The status page can then show *which* part
    failed instead of a generic error.
    """
    return await collect_health(engine, qdrant, settings)
