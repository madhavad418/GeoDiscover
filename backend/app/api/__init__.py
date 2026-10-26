from fastapi import APIRouter

from .health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
# Add new routers here, e.g. api_router.include_router(layers_router, prefix="/layers", tags=["layers"])
