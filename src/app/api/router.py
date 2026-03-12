from fastapi import APIRouter

from src.app.api.health import router as health_router

router = APIRouter()

router.include_router(health_router)
