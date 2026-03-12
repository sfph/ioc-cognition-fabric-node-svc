import logging
import os
from typing import Set

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.logger.logger import SUPPORTED_LOG_LEVELS, update_log_level

router = APIRouter(tags=["logger"])


def get_current_root_log_level() -> str:
    """
    Return the current root log level as a string.
    """
    return logging.getLevelName(logging.getLogger().getEffectiveLevel()).upper()

def get_supported_log_levels() -> Set[str]:
    """
    Return supported external log levels.
    """
    return SUPPORTED_LOG_LEVELS


@router.get("/internal/diagnostics/log-level")
async def log_level():
    return {
        "log_level": get_current_root_log_level(),
    }


@router.get("/internal/diagnostics/log-levels")
async def log_levels():
    return {
        "supported_log_levels": get_supported_log_levels
    }

class LogLevelUpdateRequest(BaseModel):
    module: str = Field(
        default="ROOT",
        description="Logger name or 'ROOT' for the root logger",
        examples=["ROOT", "src.app.registration"],
    )
    level: str = Field(
        ...,
        description="Desired log level",
        examples=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
    )

class LogLevelUpdateResponse(BaseModel):
    module: str
    level: str
    root_level: str
    supported_levels: list[str]


@router.post(
    "/internal/diagnostics/log-level",
    response_model=LogLevelUpdateResponse,
    summary="Update log level at runtime",
    description="Updates the log level for the root logger or a specific module",
)
async def update_log_levels(request: LogLevelUpdateRequest):
    success, error = update_log_level(
        module_name=request.module,
        log_level=request.level,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail=error,
        )

    return LogLevelUpdateResponse(
        module=request.module,
        level=request.level.upper(),
        root_level=get_current_root_log_level(),
        supported_levels=sorted(get_supported_log_levels()),
    )
