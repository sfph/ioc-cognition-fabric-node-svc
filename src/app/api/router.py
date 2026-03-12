from fastapi import APIRouter

from src.app.api.health import router as health_router
from src.app.api.logger import router as logger_router

router = APIRouter()

router.include_router(health_router)
router.include_router(logger_router)
