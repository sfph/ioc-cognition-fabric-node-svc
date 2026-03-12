from fastapi.testclient import TestClient

from src.app.main import create_app


def test_app_startup_and_shutdown():
    app = create_app()

    # TestClient triggers lifespan startup/shutdown automatically
    with TestClient(app) as client:
        response = client.get("/api/internal/diagnostics/health")
        assert response.status_code == 200
