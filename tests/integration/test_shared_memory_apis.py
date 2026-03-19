import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.app.main import create_app, cognition_engine_lifespan, \
    km_lifespan

pytestmark = pytest.mark.integration


TESTDATA_DIR = Path(__file__).parent.parent / "testdata"


@pytest.fixture(scope="module")
def client():
    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        async with km_lifespan(
            app,
            db_name=os.environ.get("TEST_DB_NAME", os.environ.get("DB_NAME")),
            user=os.environ.get("TEST_DB_USER", os.environ.get("DB_USER")),
            password=os.environ.get("TEST_DB_PASSWORD", os.environ.get("DB_PASSWORD")),
            host=os.environ.get("TEST_DB_HOST", os.environ.get("DB_HOST")),
            port=int(os.environ.get("TEST_DB_PORT", os.environ.get("DB_PORT", 5432))),
            register_provider_enabled=False,
            provider_config=None,
        ):
            async with cognition_engine_lifespan(app):
                yield

    app = create_app(lifespan=test_lifespan)

    with TestClient(app) as client:
        yield client


def _load_json_file(name: str):
    path = TESTDATA_DIR / name
    raw = path.read_text(encoding="utf-8")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        pytest.fail(f"{name} is not valid JSON: {exc}")

def _create_shared_memories_otel(client: TestClient):
    data = _load_json_file("otel.json")

    body = {
        "header": {
            "agent_id": "agent-1",
        },
        "request_id": "test-create-otel",
        "payload": {
            "metadata": {"format": "observe-sdk-otel"},
            "data": data,
        },
    }

    response = client.post(
        "/api/workspaces/ws1/multi-agentic-systems/mas_otel/shared-memories",
        json=body,
    )
    assert response.status_code == 201, response.text
    assert "response_id" in response.json() and response.json().get("response_id") == "test-create-otel"


def _query_shared_memories_otel(client: TestClient):
    otel_body = {
        "header": {
            "agent_id": "agent-1",
        },
        "request_id": "test-query-otel",
        "search_strategy": "semantic_graph_traversal",
        "intent": "what does the website_selector_agent do?",
    }

    response = client.post(
        "/api/workspaces/ws1/multi-agentic-systems/mas_otel/shared-memories/query",
        json=otel_body,
    )
    assert response.status_code == 200, response.text
    assert "response_id" in response.json() and response.json().get("response_id") == "test-query-otel"
    assert "status" in response.json() and response.json().get("status") == "success"


def _create_shared_memories_openclaw(client: TestClient):
    data = _load_json_file("openclaw.json")

    body = {
        "header": {
            "agent_id": "agent-1",
        },
        "request_id": "test-create-openclaw",
        "payload": {
            "metadata": {"format": "openclaw"},
            "data": data,
        },
    }

    response = client.post(
        "/api/workspaces/ws1/multi-agentic-systems/mas_openclaw/shared-memories",
        json=body,
    )
    assert response.status_code == 201, response.text
    assert "response_id" in response.json() and response.json().get("response_id") == "test-create-openclaw"


def _query_shared_memories_openclaw(client: TestClient):

    openclaw_body = {
        "header": {
            "agent_id": "agent-2",
        },
        "request_id": "test-query-openclaw",
        "search_strategy": "semantic_graph_traversal",
        "intent": "Tell me something about Q2 budget planning",
    }

    response = client.post(
        "/api/workspaces/ws1/multi-agentic-systems/mas_openclaw/shared-memories/query",
        json=openclaw_body,
    )
    assert response.status_code == 200, response.text
    assert "response_id" in response.json() and response.json().get("response_id") == "test-query-openclaw"
    assert "status" in response.json() and response.json().get("status") == "success"


def test_shared_memories_flow(client: TestClient):
    _create_shared_memories_otel(client)
    _query_shared_memories_otel(client)

    _create_shared_memories_openclaw(client)
    _query_shared_memories_openclaw(client)
