# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0
from contextlib import asynccontextmanager
from fastapi.testclient import TestClient

from src.app.main import create_app


@asynccontextmanager
async def fake_lifespan(app):
    yield


def test_app_startup_and_shutdown():
    app = create_app(lifespan=fake_lifespan)

    # TestClient triggers lifespan startup/shutdown automatically
    with TestClient(app) as client:
        response = client.get("/api/internal/diagnostics/health")
        assert response.status_code == 200
