# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter

from src.app.api.health import router as health_router
from src.app.api.logger import router as logger_router
from src.app.api.info import router as info_router
from src.app.api.shared_memory import router as shared_memory_router

router = APIRouter()

router.include_router(health_router, include_in_schema=False)
router.include_router(logger_router, include_in_schema=False)
router.include_router(info_router, include_in_schema=False)

router.include_router(shared_memory_router)
