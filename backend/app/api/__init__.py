from fastapi import APIRouter, Depends

from ..auth import current_user
from .auth import router as auth_router
from .comparison import router as comparison_router
from .comparison_runs import router as comparison_runs_router
from .customer import router as customer_router
from .delivery import router as delivery_router
from .health import router as health_router
from .operations import router as operations_router
from .sources import router as sources_router
from .tasks import router as tasks_router
from .area_collection import router as area_collection_router
from .provider_comparison import router as provider_comparison_router

api_router = APIRouter()
api_router.include_router(area_collection_router)
api_router.include_router(provider_comparison_router)
# Public: health check (Railway) and sign-in.
api_router.include_router(health_router)
api_router.include_router(auth_router)
# Everything else needs a signed-in user; routes add role checks where an action needs one.
signed_in = [Depends(current_user)]
api_router.include_router(customer_router, dependencies=signed_in)
api_router.include_router(comparison_router, dependencies=signed_in)
api_router.include_router(operations_router, dependencies=signed_in)
api_router.include_router(sources_router)
api_router.include_router(comparison_runs_router)
api_router.include_router(tasks_router)
api_router.include_router(delivery_router)
