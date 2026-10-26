from fastapi import APIRouter

from ..config import get_settings
from ..db import database_status

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    """Railway health check. Always 200 while the process is up; `database` reports DB reachability."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "database": database_status(),
    }
