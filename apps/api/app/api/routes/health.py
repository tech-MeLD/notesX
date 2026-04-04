from fastapi import APIRouter

from app.core.config import settings
from app.schemas.rss import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.app_env)
