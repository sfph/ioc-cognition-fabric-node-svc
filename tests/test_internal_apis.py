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


def test_logger_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/internal/diagnostics/logger")

    assert response.status_code == 200
    data = response.json()

    assert data["log_level"] == "INFO"
