# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Dict, Any

from fastapi import APIRouter

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
                "time": os.environ.get("GIT_COMMIT_TIME", "unknown"),
                "id": os.environ.get("GIT_COMMIT_SHA", "unknown"),
            },
            "branch": os.environ.get("GIT_BRANCH", "unknown"),
        }
    }
