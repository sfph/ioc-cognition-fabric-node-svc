# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import logging
import os
import socket
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from src.app.config.config import (
    DISABLE_REGISTRATION,
    MGMT_URL,
    CFN_NAME,
    APP_PORT,
    SERVICE_NAME,
    HEARTBEAT_INTERVAL_SECONDS,
)

logger = logging.getLogger(__name__)


# ----------------------------
# Global CFN State
# ----------------------------
CfnID: Optional[str] = None
CfnConfig: Dict[str, Any] = {}
CfnTimestamp: Optional[str] = None

cfn_config_lock = asyncio.Lock()


def get_outbound_ip() -> str:
    """
    Determine outbound IP.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        logger.warning(
            "Failed to determine outbound IP, using the service name address for it"
        )
        return SERVICE_NAME


async def refresh_config(mgmt_url: str) -> None:
    global CfnConfig, CfnTimestamp

    if not CfnID:
        raise RuntimeError("CFN not registered")

    cfn_url = f"{mgmt_url}/api/cognition-fabric-nodes/{CfnID}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            cfn_url,
            headers={"Accept": "application/json"},
        )

    result = resp.json()

    if resp.status_code < 200 or resp.status_code >= 300:
        logger.error(
            "RefreshConfig failed: status=%d response=%s",
            resp.status_code,
            result,
        )
        raise RuntimeError(f"RefreshConfig failed: status={resp.status_code}")

    async with cfn_config_lock:
        cfg_blob = result.get("config")
        if isinstance(cfg_blob, dict):
            CfnConfig = cfg_blob
            CfnTimestamp = cfg_blob.get("config_timestamp")
            logger.info("CFN Config refreshed, timestamp=%s", CfnTimestamp)
        else:
            logger.warning("RefreshConfig response missing config key")


async def start_heartbeat(stop_event: asyncio.Event) -> None:
    if not CfnID:
        logger.error("heartbeat started without CfnID")
        return

    heartbeat_url = f"{MGMT_URL}/api/cognition-fabric-nodes/{CfnID}/heartbeat"

    interval_seconds = int(HEARTBEAT_INTERVAL_SECONDS)

    logger.info("starting heartbeat to %s", heartbeat_url)

    async with httpx.AsyncClient(timeout=10.0) as client:
        while not stop_event.is_set():
            try:
                resp = await client.put(
                    heartbeat_url,
                    headers={"Accept": "application/json"},
                )

                if resp.status_code == 200:
                    result = resp.json()
                    new_ts = result.get("config_timestamp")

                    if isinstance(new_ts, str):
                        async with cfn_config_lock:
                            current_ts = CfnTimestamp

                        if current_ts:
                            new_time = datetime.fromisoformat(
                                new_ts.replace("Z", "+00:00")
                            )
                            cur_time = datetime.fromisoformat(
                                current_ts.replace("Z", "+00:00")
                            )

                            logger.debug(
                                "heartbeat response: mgmt=%s local=%s",
                                new_ts,
                                current_ts,
                            )

                            if new_time > cur_time:
                                logger.info(
                                    "config update detected: mgmt=%s local=%s - refreshing",
                                    new_ts,
                                    current_ts,
                                )
                                try:
                                    await refresh_config(MGMT_URL)
                                except Exception as exc:
                                    logger.error("failed to refresh config: %s", exc)

                else:
                    logger.error("heartbeat failed, status=%d", resp.status_code)

            except Exception as exc:
                logger.error("heartbeat failed: %s", exc)

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue

    logger.info("stopping heartbeat")


# ----------------------------
# Registration to Management Plane
# ----------------------------
async def register_on_startup(
    *,
    stop_event: asyncio.Event,
) -> None:
    """
    Registers this CFN with the management plane and starts heartbeat.
    """
    if DISABLE_REGISTRATION:
        logger.info("Service registration disabled (test mode)")
        return

    global CfnID, CfnConfig, CfnTimestamp

    app_port = int(APP_PORT)
    app_ip = get_outbound_ip()

    if not MGMT_URL:
        raise RuntimeError("MGMT_URL not set")

    if not CFN_NAME or not app_ip or not app_port:
        raise RuntimeError(
            f"registration prereqs missing: "
            f"cfnName={CFN_NAME!r} appIP={app_ip!r} appPort={app_port}"
        )

    register_url = f"{MGMT_URL}/api/cognition-fabric-nodes/register"
    logger.info("registering CFN at %s", register_url)

    payload = {
        "cfn_name": CFN_NAME,
        "ip_address": app_ip,
        "port": app_port,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            register_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    try:
        result = resp.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to decode registration response: {exc}") from exc

    if resp.status_code < 200 or resp.status_code >= 300:
        raise RuntimeError(
            f"CFN registration failed: status={resp.status_code}, response={result}"
        )

    cfn_id = result.get("cfn_id")
    if not isinstance(cfn_id, str) or not cfn_id:
        raise RuntimeError("registration response missing cfn_id")

    CfnID = cfn_id

    async with cfn_config_lock:
        cfg_blob = result.get("config")
        if isinstance(cfg_blob, dict):
            CfnConfig = cfg_blob
            CfnTimestamp = cfg_blob.get("config_timestamp")

    logger.info(
        "CFN registered successfully: cfn_id=%s cfn_name=%s ip_address=%s port=%d config=%s timestamp=%s",
        CfnID,
        CFN_NAME,
        app_ip,
        app_port,
        CfnConfig,
        CfnTimestamp,
    )

    # Start heartbeat in background
    asyncio.create_task(start_heartbeat(stop_event))
