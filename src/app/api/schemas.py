from typing import Any, Optional, List, Dict
from uuid import uuid4

from evidence.app.api.schemas import KnowledgeRecord
from knowledge_memory.server.schemas.knowledge_graph import (
    KnowledgeGraphQueryResponseRecord,
)
from pydantic import BaseModel, Field, model_validator, ConfigDict


class ExtractionPayloadMetadata(BaseModel):
    format: str = Field(
        "openclaw",
        description="Payload format. Supported values: 'observe-sdk-otel' and 'openclaw'. Defaults to 'openclaw'.",
    )


class ExtractionPayload(BaseModel):
    metadata: ExtractionPayloadMetadata = Field(
        ...,
        description="Metadata describing the format and interpretation of the payload.",
    )

    data: list[dict[str, Any]] = Field(
        ...,
        description=(
            "Extraction payload as a list of JSON objects. "
            "The objects are not validated by this service and are processed as-is. "
            "Clients must ensure each object matches the format specified by `metadata.format`."
        ),
        json_schema_extra={
            "examples": [
                {
                    "schema": "openclaw-conversation-v1",
                    "session": {
                        "agentId": "agent-123",
                        "sessionId": "906630a9-bf57-48d8-bbae-9d41e7639d29",
                        "channel": "matrix",
                    },
                    "turns": [
                        {
                            "index": 0,
                            "timestamp": "2026-02-25T20:32:14.783Z",
                            "model": "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0",
                            "stopReason": "stop",
                            "userMessage": "It's Q2 budget planning.",
                            "thinking": None,
                            "toolCalls": [],
                            "response": "Opening request from Engineering.",
                        }
                    ],
                }
            ]
        },
    )


class Header(BaseModel):
    agent_id: Optional[str] = Field(
        default=None,
        description=("Optional identifier of the agent sending the request."),
        json_schema_extra={"example": "agent-123"},
    )


class CreateOrUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: Optional[Header] = Field(
        default=None,
        description=("Optional header of the request."),
    )
    request_id: Optional[str] = Field(
        default_factory=lambda: str(uuid4()),
        description=(
            "Client-supplied request identifier for tracing and idempotency. "
            "If omitted, the service generates a UUID."
        ),
        json_schema_extra={
            "example": "0f7c2b1e-8d0d-4d4d-9e2d-1a2b3c4d5e6f",
        },
    )
    payload: ExtractionPayload


class CreateOrUpdateResponse(BaseModel):
    response_id: str = Field(
        ..., description="ID of the response. This is populated from `request_id`."
    )
    status: str = Field(..., description="Status of the request.")
    message: Optional[str] = Field(
        default=None, description="Optional message providing additional information."
    )


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: Optional[Header] = Field(
        default=None,
        description=("Optional header of the request."),
    )

    request_id: Optional[str] = Field(
        default=None,
        description=(
            "Client-supplied request identifier for tracing and idempotency. "
            "If omitted, the service generates a UUID."
        ),
        json_schema_extra={"example": "0f7c2b1e-8d0d-4d4d-9e2d-1a2b3c4d5e6f"},
    )

    intent: str = Field(
        ...,
        description=(
            "The user’s query intent. This field is required and describes what "
            "the caller wants to search for or retrieve."
        ),
        json_schema_extra={"example": "what does the website_selector_agent do?"},
    )

    search_strategy: Optional[str] = Field(
        default="semantic_graph_traversal",
        description=(
            "Search strategy to use when processing the query. "
            'If omitted, defaults to `"semantic_graph_traversal"`.'
        ),
        json_schema_extra={"example": "semantic_graph_traversal"},
    )

    additional_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional additional context used to influence query processing. "
            "May include arbitrary JSON key-value pairs such as filters, "
            "user context, or execution hints."
        ),
        json_schema_extra={
            "example": {"filters": {"environment": "prod"}, "session_id": "abc-123"},
        },
    )

    @model_validator(mode="after")
    def validate_and_apply_default(self) -> "QueryRequest":
        if not self.intent:
            raise ValueError("intent is required")

        if not self.request_id:
            self.request_id = str(uuid4())

        if not self.search_strategy:
            self.search_strategy = "semantic_graph_traversal"

        if self.search_strategy != "semantic_graph_traversal":
            raise ValueError(
                "the only supported search_strategy is semantic_graph_traversal"
            )

        return self


class Concept(BaseModel):
    id: str
    name: str


class Relationship(BaseModel):
    id: str
    type: str


class Record(BaseModel):
    concepts: List[Concept]
    relationships: List[Relationship]


class QueryResponse(BaseModel):
    response_id: str = Field(
        ..., description="ID of the response. This is populated from `request_id`."
    )
    status: str = Field(..., description="Status of the request.")
    message: Optional[str] = Field(
        default=None, description="Optional message providing additional information."
    )
