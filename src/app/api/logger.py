import os

from fastapi import APIRouter

router = APIRouter(tags=["logger"])

@router.get("/internal/diagnostics/logger")
async def health():
    return {
        "log_level": os.environ.get("LOG_LEVEL", "info").upper(),
    }
