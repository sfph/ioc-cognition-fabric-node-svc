# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""Client utilities for interacting with the Management Plane API."""

import logging
from typing import Any, Dict, Optional
import httpx
from fastapi import Path, HTTPException

from src.app.config.config import MGMT_URL, DISABLE_VALIDATION

logger = logging.getLogger(__name__)


async def _fetch_resource(
    client: httpx.AsyncClient,
    url: str,
    not_found_detail: Optional[str] = None,
    server_error_detail: str = "Upstream service request failed.",
    not_found_log: Optional[str] = None,
    server_error_log: str = "Upstream service request failed",
    return_json: bool = False,
) -> Optional[Dict[str, Any]]:
    try:
        resp = await client.get(
            url,
            headers={"Accept": "application/json"},
        )
    except httpx.TimeoutException:
        logger.error("%s | reason=timeout", server_error_log)
        raise HTTPException(
            status_code=500,
            detail=server_error_detail,
        )
    except httpx.RequestError as exc:
        logger.error("%s | reason=request_error error=%s", server_error_log, str(exc))
        raise HTTPException(
            status_code=500,
            detail=server_error_detail,
        )

    if resp.status_code == 404 and not_found_detail is not None:
        logger.error(not_found_log or not_found_detail)
        raise HTTPException(
            status_code=404,
            detail=not_found_detail,
        )

    if not 200 <= resp.status_code < 300:
        logger.error(
            "%s | status_code=%s response=%s",
            server_error_log,
            resp.status_code,
            resp.text,
        )
        raise HTTPException(
            status_code=500,
            detail=server_error_detail,
        )

    if not return_json:
        return None

    try:
        return resp.json()
    except ValueError:
        logger.error(
            "%s | reason=invalid_json_response response=%s",
            server_error_log,
            resp.text,
        )
        raise HTTPException(
            status_code=500,
            detail=server_error_detail,
        )


async def fetch_all_cfn_nodes() -> Dict[str, Any]:
    """
    Fetch list of all CFN nodes from management plane API.

    Args: None

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
    list_url = f"{MGMT_URL}/api/cognition-fabric-nodes"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await _fetch_resource(
                client=client,
                url=list_url,
                server_error_detail="Failed to fetch CFN list.",
                server_error_log="Failed to fetch CFN list",
                return_json=True,
            )
    except HTTPException as exc:
        error_msg = f"Failed to fetch CFN list: status={exc.status_code}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from exc

    return response or {}


async def fetch_cfn_summary(cfn_id: str) -> Dict[str, Any]:
    """
    Fetch CFN summary from management plane API.

    Args:
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
    summary_url = f"{MGMT_URL}/api/cognition-fabric-nodes/{cfn_id}/summary"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await _fetch_resource(
                client=client,
                url=summary_url,
                server_error_detail=f"Failed to fetch CFN summary for cfn_id={cfn_id}.",
                server_error_log=f"Failed to fetch CFN summary for cfn_id={cfn_id}",
                return_json=True,
            )
    except HTTPException as exc:
        error_msg = f"Failed to fetch CFN summary: status={exc.status_code}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from exc

    logger.debug("Received CFN summary response: %s", response)

    return response or {}


async def check_workspace_and_mas(
    workspace_id: str = Path(..., description="Workspace ID"),
    mas_id: str = Path(..., description="Multi-Agentic System ID"),
) -> None:
    # Stamp dep-resolution latency into the per-request timing bucket.
    from src.app.api._request_timing import timing_stage

    with timing_stage("check_workspace_and_mas_ms"):
        if DISABLE_VALIDATION:
            logger.debug("Skipping Workspace and MAS validation as it is disabled.")
            return

        workspace_url = f"{MGMT_URL}/api/workspaces/{workspace_id}"
        mas_url = f"{MGMT_URL}/api/workspaces/{workspace_id}/multi-agentic-systems/{mas_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            with timing_stage("check_workspace_ms"):
                await _fetch_resource(
                    client=client,
                    url=workspace_url,
                    not_found_detail=f"Workspace '{workspace_id}' not found. "
                    f"Please visit {MGMT_URL}/api/docs for creating a workspace.",
                    server_error_detail=(
                        f"Internal Server Error while validating workspace: '{workspace_id}'."
                    ),
                    not_found_log=f"Workspace '{workspace_id}' not found",
                    server_error_log=f"Failed to fetch workspace '{workspace_id}'",
                )

            with timing_stage("check_mas_ms"):
                await _fetch_resource(
                    client=client,
                    url=mas_url,
                    not_found_detail=f"MAS '{mas_id}' not found under workspace '{workspace_id}'. "
                    f"Please visit {MGMT_URL}/api/docs for creating a MAS under the workspace.",
                    server_error_detail=(
                        f"Internal Server Error while validating MAS '{mas_id}' "
                        f"under workspace {workspace_id}."
                    ),
                    not_found_log=f"MAS '{mas_id}' not found under workspace '{workspace_id}'",
                    server_error_log=f"Failed to fetch MAS '{mas_id}' under workspace '{workspace_id}'",
                )
