# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""Client utilities for interacting with the Management Plane API."""

import logging
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)


async def fetch_all_cfn_nodes(mgmt_url: str) -> Dict[str, Any]:
    """
    Fetch list of all CFN nodes from management plane API.

    Args:
        mgmt_url: Management plane base URL (e.g., "http://localhost:9000")

    Returns:
        Response dict containing:
        {
            "nodes": [
                {
                    "cfn_id": "uuid",
                    "cfn_name": "name",
                    "status": "online|offline",
                    "workspace_ids": [...],
                    ...
                }
            ],
            "total": int
        }

    Raises:
        RuntimeError: If API call fails
    """
    list_url = f"{mgmt_url}/api/cognition-fabric-nodes"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            list_url,
            headers={"Accept": "application/json"},
        )

    if resp.status_code < 200 or resp.status_code >= 300:
        error_msg = f"Failed to fetch CFN list: status={resp.status_code}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    return resp.json()


async def fetch_cfn_summary(mgmt_url: str, cfn_id: str) -> Dict[str, Any]:
    """
    Fetch CFN summary from management plane API.

    Args:
        mgmt_url: Management plane base URL (e.g., "http://localhost:9000")
        cfn_id: Cognition Fabric Node ID

    Returns:
        CFN summary response dict containing workspaces, MAS, and configuration

    Raises:
        RuntimeError: If API call fails

    Example response structure:
        {
            "id": "cfn-uuid",
            "name": "My CFN",
            "config": {
                "workspaces": [
                    {
                        "id": "workspace-uuid",
                        "multi_agentic_systems": [
                            {"id": "mas-uuid", "name": "MAS 1", ...}
                        ]
                    }
                ]
            },
            "status": "online",
            ...
        }
    """
    summary_url = f"{mgmt_url}/api/cognition-fabric-nodes/{cfn_id}/summary"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            summary_url,
            headers={"Accept": "application/json"},
        )

    if resp.status_code < 200 or resp.status_code >= 300:
        error_msg = f"Failed to fetch CFN summary: status={resp.status_code}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    logger.debug(f"Received CFN summary response: {resp.json()}")

    return resp.json()
