import os

from fastapi import APIRouter

from src.logger.logger import SUPPORTED_LOG_LEVELS

router = APIRouter(tags=["logger"])

@router.get("/internal/diagnostics/log-level")
async def health():
    return {
        "log_level": os.environ.get("LOG_LEVEL", "info").upper(),
    }


@router.get("/internal/diagnostics/log-levels")
async def health():
    return {
        "supported_log_levels": SUPPORTED_LOG_LEVELS
    }
