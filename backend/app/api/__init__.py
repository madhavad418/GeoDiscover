from fastapi import APIRouter

from .health import router as health_router
from .customer import router as customer_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(customer_router)
# Add new routers here, e.g. api_router.include_router(layers_router, prefix="/layers", tags=["layers"])
