import logging
import json
import os

from caching.app.agent import CachingLayer
from evidence.app.agent.evidence import process_evidence
from evidence.app.api.schemas import (
    ReasonerCognitionRequest,
    Header,
    RequestPayload,
    ReasonerCognitionResponse,
)
from evidence.app.data.mock_repo import MockDataRepository
from fastapi import APIRouter, Path, Body, HTTPException, status, Depends
from typing import List, Optional, Dict, Any

from ingestion.app.agent import KnowledgeProcessor
from ingestion.app.agent.concept_vector_store import ConceptVectorStore
from knowledge_memory import query_knowledge_graph_async, upsert_knowledge_graph_async

from ingestion.app.agent.service import ConceptRelationshipExtractionService

from fastapi import Request

from src.app.api.schemas import (
    CreateOrUpdateRequest,
    QueryResponse,
    QueryRequest,
    CreateOrUpdateResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def get_cache_layer(request: Request):
    return request.app.state.cache_layer


def get_settings(request: Request):
    return request.app.state.settings


def json_escape_string(value: str) -> str:
    return json.dumps(value)[1:-1]


def transform_concept_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    # Required / known field
    out["concept_type"] = attrs.get("conceptType")

    # Extra attributes
    for k, v in attrs.get("extra", {}).items():
        out[k] = v

    return out


def transform_concept_embedding(attrs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    embedding = attrs.get("embedding")

    if not embedding or not embedding[0]:
        return None

    return {
        "name": "BAAI/bge-small-en-v1.5",  # TODO: make dynamic
        "data": embedding[0],
    }


def transform_extraction_concepts(
    src: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    if not src:
        return None

    out: List[Dict[str, Any]] = []

    for c in src:
        description = c.get("description", "")
        desc_value = None

        # Preserve empty string vs nil semantics
        if description:
            desc_value = json_escape_string(description)

        out.append(
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "description": desc_value,
                "attributes": transform_concept_attributes(c.get("attributes", {})),
                "embeddings": transform_concept_embedding(c.get("attributes", {})),
            }
        )

    return out


def transform_extraction_relations(
    src: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    if not src:
        return None

    out: List[Dict[str, Any]] = []

    for r in src:
        out.append(
            {
                "id": r.get("id"),
                "relation": r.get("relationship"),
                "node_ids": r.get("node_ids"),
                "attributes": r.get("attributes"),
            }
        )

    return out


def transform_extraction_response_to_records(
    resp: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if resp is None:
        return None

    return {
        "concepts": transform_extraction_concepts(resp.get("concepts", [])),
        "relations": transform_extraction_relations(resp.get("relations", [])),
    }


@router.post(
    "/workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/shared-memories",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateOrUpdateResponse,
    response_model_exclude_none=True,
    tags=["shared-memories"],
)
async def create_or_update_shared_memories(
    body: CreateOrUpdateRequest = Body(...),
    workspace_id: str = Path(..., description="Workspace ID"),
    mas_id: str = Path(..., description="Multi-Agentic System ID"),
    cache_layer: CachingLayer = Depends(get_cache_layer),
):
    request_id = body.request_id
    agent_id = body.header.agent_id if body.header else None

    logger.info(
        "Creating or updating shared memories | workspace=%s, mas=%s,request_id=%s, agent_id=%s",
        workspace_id,
        mas_id,
        request_id,
        agent_id,
    )

    extraction_payload = body.payload

    # Initialize services (requires Azure OpenAI credentials)
    concept_service = ConceptRelationshipExtractionService(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        azure_api_version=os.environ.get("AZURE_OPENAI_API_VERSION"),
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
    )

    result = concept_service.extract_concepts_and_relationships(
        extraction_payload.data,
        request_id=request_id,
        format_descriptor=extraction_payload.metadata.format,
    )
    processor = KnowledgeProcessor(enable_embeddings=True, enable_dedup=False)
    result = processor.process(result)
    vector_store = ConceptVectorStore(cache_layer=cache_layer)  # Uses shared cache
    vector_store.store_concepts(result.get("concepts", []))

    # -------------------------
    # Upsert knowledge graph
    # -------------------------
    try:
        concepts = transform_extraction_concepts(result.get("concepts", []))
        relations = transform_extraction_relations(result.get("relations", []))

        logger.debug(f"Concepts from extraction: {concepts}")
        logger.debug(f"Relations from extraction: {relations}")

        kg_resp = await upsert_knowledge_graph_async(
            mas_id=mas_id,
            wksp_id=workspace_id,
            request_id=request_id,
            concepts=concepts,
            relations=relations,
            force_replace=True,
        )
    except Exception as exc:
        logger.exception(
            "UpsertKnowledgeGraph failed | workspace=%s mas=%s",
            workspace_id,
            mas_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to create or update shared memories, error: {exc}",
        )

    logger.info(f"create or update shared memories succeeded: {kg_resp}")

    return CreateOrUpdateResponse(
        response_id=request_id,
        status=kg_resp.status,
        message=kg_resp.message,
    )


def transform_reasoner_response_to_concepts(
    reasoner_resp: ReasonerCognitionResponse,
) -> Optional[List[Dict[str, str]]]:
    """
    Extract concept IDs and names from a ReasonerCognitionResponse.

    Expected input is a ReasonerCognitionResponse object whose `records` contain
    `KnowledgeRecord` items. Each record's `content` is a dict, and concepts are
    expected at:

        record.content["evidence"]["details"]["concepts"]

    Example shape:

        ReasonerCognitionResponse(
            ...,
            records=[
                KnowledgeRecord(
                    ...,
                    content={
                        "evidence": {
                            "details": {
                                "concepts": [
                                    {
                                        "concept_id": "...",
                                        "name": "..."
                                    }
                                ]
                            }
                        }
                    }
                )
            ]
        )

    Notes:
    - If `reasoner_resp` is None, returns None.
    - If no concepts are present, returns an empty list.
    - Records that do not contain `evidence.details.concepts` are skipped.
    - Each returned concept is normalized to:
        {"id": <conceptId>, "name": <name>}
    """
    if reasoner_resp is None:
        return None

    concepts: List[Dict[str, str]] = []

    for rec in reasoner_resp.records:
        details = rec.content.get("evidence", {}).get("details", {})

        for c in details.get("concepts", []):
            concepts.append(
                {
                    "id": c.get("concept_id"),
                    "name": c.get("name"),
                }
            )

    return concepts


@router.post(
    "/workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/shared-memories/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    response_model_exclude_none=True,
    tags=["shared-memories"],
)
async def fetch_shared_memories(
    body: QueryRequest = Body(...),
    workspace_id: str = Path(..., description="Workspace ID"),
    mas_id: str = Path(..., description="Multi-Agentic System ID"),
    cache_layer: CachingLayer = Depends(get_cache_layer),
):
    request_id = body.request_id
    agent_id = body.header.agent_id if body.header else None

    logger.info(
        "Fetching shared memories | workspace=%s, mas=%s, request_id=%s, agent_id=%s",
        workspace_id,
        mas_id,
        request_id,
        agent_id,
    )

    request = ReasonerCognitionRequest(
        header=Header(workspace_id=workspace_id, mas_id=mas_id, agent_id=agent_id),
        request_id=request_id,
        payload=RequestPayload(intent=body.intent),
    )
    repo = MockDataRepository()
    response = await process_evidence(
        request, repo_adapter=repo, cache_layer=cache_layer
    )

    concepts = transform_reasoner_response_to_concepts(response)
    if len(concepts) == 0:
        return QueryResponse(
            response_id=request_id,
            status="success",
            message="no relevant concepts found",
            records=None,
        )

    try:
        kg_response = await query_knowledge_graph_async(
            mas_id=mas_id,
            wksp_id=workspace_id,
            concepts=concepts,
            request_id=request_id,
            query_type="neighbour",
        )
    except Exception as exc:
        logger.exception(
            f"Knowledge graph query failed | workspace={workspace_id} mas={mas_id}: {exc}",
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to fetch shared memories: {exc}",
        )

    # -----------------------
    # Build response
    # -----------------------
    response_dict = QueryResponse(
        response_id=request_id,
        status=kg_response.status,
        message=kg_response.message,
        records=kg_response.records,
    ).model_dump()

    # -----------------------
    # Remove embeddings
    # -----------------------
    for record in response_dict["records"]:
        for concept in record.get("concepts", []):
            concept["embeddings"] = None
        for rel in record.get("relations", []):
            rel["embeddings"] = None

    response = QueryResponse.model_validate(response_dict)

    logger.info(
        "Shared memories query succeeded | status=%s records=%d",
        response.status,
        len(response.records),
    )

    return response
