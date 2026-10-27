from fastapi import APIRouter

from ..config import get_settings
from ..db import database_status, schema_status

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    """Railway health check. Always 200 while the process is up.

    `database` reports reachability; `schema` reports whether migrations are fully applied.
    """
    settings = get_settings()
    database = database_status()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "database": database,
        "schema": schema_status() if database == "ok" else "unknown",
    }
