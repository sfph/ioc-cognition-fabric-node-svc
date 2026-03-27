# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

from fastapi.testclient import TestClient

from src.app.config.config import SERVICE_NAME
from src.app.main import create_app
from src.app.utils.utils import get_app_version


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/internal/diagnostics/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == SERVICE_NAME
    assert data["version"] == get_app_version()


def test_loglevel_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/internal/diagnostics/log-level")

    assert response.status_code == 200
    data = response.json()

    assert "log_level" in data
    assert data["log_level"] == "INFO"


def test_loglevels_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/internal/diagnostics/log-levels")

    assert response.status_code == 200
    data = response.json()

    assert "supported_log_levels" in data
    assert len(data["supported_log_levels"]) == 5

    supported = set(data["supported_log_levels"])

    expected_levels = {
        "DEBUG",
        "INFO",
        "WARN",
        "ERROR",
        "CRITICAL",
    }

    assert supported == expected_levels


def test_update_log_level_endpoint():
    app = create_app()
    client = TestClient(app)

    payload = {
        "module": "ROOT",
        "level": "DEBUG",
    }

    response = client.post(
        "/api/internal/diagnostics/log-level",
        json=payload,
    )

    assert response.status_code == 200

    data = response.json()

    # Response contract
    assert data["module"] == "ROOT"
    assert data["level"] == "DEBUG"
    assert "supported_levels" in data
    assert "root_level" in data

    # Root logger actually changed
    assert data["root_level"] == "DEBUG"


def test_diagnostics_info_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/internal/diagnostics/info")

    assert response.status_code == 200
    data = response.json()

    assert "git" in data
    assert "commit" in data["git"]
    assert "id" in data["git"]["commit"]
    assert "time" in data["git"]["commit"]
    assert "branch" in data["git"]
