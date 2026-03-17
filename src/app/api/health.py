# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter

from src.app.utils.utils import service_name, get_app_version

router = APIRouter(tags=["health"])


@router.get("/internal/diagnostics/health")
async def health():
    return {
        "status": "healthy",
        "service": service_name,
        "version": get_app_version(),
    }
