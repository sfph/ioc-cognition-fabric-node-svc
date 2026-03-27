# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Dict, Any

from fastapi import APIRouter

from src.app.config.config import GIT_COMMIT_SHA, GIT_COMMIT_TIME, GIT_BRANCH

router = APIRouter(tags=[""])


@router.get(
    "/internal/diagnostics/info",
    summary="Get diagnostics information",
    description="Returns git build information for this service",
)
async def diagnostics_info():
    return {
        "git": {
            "commit": {
                "time": GIT_COMMIT_TIME,
                "id": GIT_COMMIT_SHA,
            },
            "branch": GIT_BRANCH,
        }
    }
