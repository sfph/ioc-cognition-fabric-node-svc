"""
Logger configuration and management utilities.

Provides functions for initializing logging, querying logger states,
and updating log levels dynamically at runtime.
"""

import json
import logging
import os
import tomllib
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Set

# Valid log levels for IoC CFN Service
SUPPORTED_LOG_LEVELS: Set[str] = {
    "DEBUG",
    "INFO",
    "WARN",
    "ERROR",
    "CRITICAL",
}


# Mapping of IoC CFN log levels to Python logging levels
LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def get_version_from_pyproject() -> str:
    """
    Read version from pyproject.toml file.

    Returns:
        Version string from pyproject.toml or "unknown" if not found
    """
    try:
        # Try to find pyproject.toml in common locations
        possible_paths = [
            os.path.join(os.getcwd(), "pyproject.toml"),
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "pyproject.toml",
            ),
        ]

        for pyproject_path in possible_paths:
            if os.path.exists(pyproject_path):
                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)
                    return data.get("project", {}).get("version", "unknown")

        return "unknown"
    except Exception as e:
        logging.warning(f"Could not read version from pyproject.toml: {e}")
        return "unknown"


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str, version: str):
        super().__init__()
        self.service_name = service_name
        self.version = version

    def format(self, record: logging.LogRecord) -> str:
        dt = datetime.fromtimestamp(record.created)
        timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + time.strftime("%z")

        # this is to normalize uvicorn's logger names, e.g. its default name of "uvicorn.error"
        if record.name.startswith("uvicorn"):
            logger_name = "server"
        else:
            logger_name = record.name

        log_record = {
            "level": record.levelname,
            "timestamp": timestamp,
            "logger": logger_name,
            "caller": f"{record.filename}:{record.lineno}",
            "message": record.getMessage(),
            "service": self.service_name,
            "version": self.version,
        }
        return json.dumps(log_record)


def setup_logging(service_name: str, default_level: str = "INFO") -> None:
    """
    Initialize logging configuration for the service.

    Args:
        service_name: Name of the service for log identification
        default_level: Default log level (default: INFO)
    """
    # Get log level from environment or use default
    env_level = os.environ.get("LOG_LEVEL", default_level).upper()
    if env_level not in LOG_LEVEL_MAP:
        env_level = default_level.upper()
    python_level = LOG_LEVEL_MAP[env_level]

    app_version = os.environ.get("APPLICATION_VERSION") or get_version_from_pyproject()

    # Configure basic logging
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service_name, app_version))

    root = logging.getLogger()
    root.setLevel(python_level)
    root.handlers = [handler]


def get_loggers_info() -> Dict[str, Any]:
    """
    Get information about all configured loggers.

    Returns:
        Dictionary containing root log level and all module-specific loggers
    """
    root_logger = logging.getLogger()
    log_level_name = logging.getLevelName(root_logger.level)

    # Get all loggers with their levels
    loggers_info = {"log-level": log_level_name, "loggers": {}}

    # Iterate through all known loggers
    for name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(name)
        if logger.level != logging.NOTSET:
            loggers_info["loggers"][name] = logging.getLevelName(logger.level)

    return loggers_info


def validate_log_level(log_level: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and normalize a log level string.

    Args:
        log_level: The log level string to validate

    Returns:
        Tuple of (is_valid, normalized_level, error_message)
    """
    log_level_upper = log_level.upper()

    # Check if it's a valid IoC CFN Management Backend Service log level
    if log_level_upper not in SUPPORTED_LOG_LEVELS:
        return False, None, f"Invalid log level: {log_level}"

    # Verify it's a valid Python logging level
    if log_level_upper not in LOG_LEVEL_MAP:
        return False, None, f"Invalid log level: {log_level}"

    return True, None


def update_log_level(module_name: str, log_level: str) -> Tuple[bool, Optional[str]]:
    log_level_upper = log_level.upper()

    if log_level_upper not in LOG_LEVEL_MAP:
        return False, f"Invalid log level: {log_level}"

    python_level = LOG_LEVEL_MAP[log_level_upper]

    if module_name in ("ROOT", ""):
        logging.getLogger().setLevel(python_level)
        logging.info("Root logger level set to %s", log_level_upper)
    else:
        logger = logging.getLogger(module_name)
        logger.setLevel(python_level)
        logging.info("Logger '%s' level set to %s", module_name, log_level_upper)

    return True, None

