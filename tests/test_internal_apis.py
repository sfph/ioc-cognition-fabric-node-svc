from fastapi.testclient import TestClient

from src.app.main import create_app
from src.app.utils.utils import service_name, get_app_version


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/internal/diagnostics/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == service_name
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

    test_loglevel_endpoint()