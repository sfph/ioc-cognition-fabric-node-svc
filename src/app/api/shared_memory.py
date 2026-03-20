import asyncio
import logging
import json
import os

from caching.app.agent import CachingLayer
from evidence.app.agent.evidence import process_evidence
from evidence.app.api.schemas import (ReasonerCognitionRequest, Header,
                                      RequestPayload, ReasonerCognitionResponse,
                                      NeighborsResponse, ConceptsByIdsRequest,
                                      ConceptsByIdsResponse, Concept,
                                      GraphPathsResponse, GraphPathsRequest,
                                      PathEdge, Path)
from evidence.app.data.http_repo import HttpDataRepository
from evidence.app.data.mock_repo import MockDataRepository
from fastapi import APIRouter, Body, HTTPException, status, Depends
from fastapi import Path as ApiPath
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
    workspace_id: str = ApiPath(..., description="Workspace ID"),
    mas_id: str = ApiPath(..., description="Multi-Agentic System ID"),
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

        logger.info(f"Concepts from extraction: {concepts}")
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
    workspace_id: str = ApiPath(..., description="Workspace ID"),
    mas_id: str = ApiPath(..., description="Multi-Agentic System ID"),
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
    repo = HttpDataRepository(base_url="http://localhost:9002")
    eg_response = await process_evidence(
        request, repo_adapter=repo, cache_layer=cache_layer
    )

    logger.info(f"Evidence gathering response:  {eg_response}")

    # extract evidence fields
    evidence = {}
    trace = {}
    if getattr(eg_response, "records", None):
        rec0 = eg_response.records[0]
        content = getattr(rec0, "content", None)
        if isinstance(content, dict):
            evidence = content.get("evidence") or {}
            trace = content.get("trace") or {}

    evidence_status = evidence.get("status")  # e.g. "insufficient"
    final_response = evidence.get("final_response")  # may be missing
    entity_name = (evidence.get("entity") or {}).get("name")

    message = (
        final_response
        or (f"Insufficient evidence for entity '{entity_name}'" if evidence_status == "insufficient" and entity_name else None)
        or (f"Evidence status: {evidence_status}" if evidence_status else None)
        or "evidence processed"
    )

    return QueryResponse(
        response_id=request_id,
        status="success",
        message=message,
    )


@router.get(
    "/v1/graph/neighbors/{concept_id}",
    response_model=NeighborsResponse,
    status_code=status.HTTP_200_OK,
    response_model_exclude_none=True,
    tags=["shared-memories"],
)
async def get_neighbors_by_id(
    concept_id: str = ApiPath(..., description="Concept ID"),
):
    try:
        kg_response = await query_knowledge_graph_async(
            mas_id="mas_openclaw_test",
            concepts=[{'id': concept_id}],
            query_type="neighbour",
        )
    except Exception as exc:
        logger.exception(
            f"Knowledge graph query failed | concept ID={concept_id}: {exc}",
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to fetch concept: {exc}",
        )

    logger.info(f"Returning {len(kg_response.records)} neighbors: {kg_response.records}")

    return NeighborsResponse(
        records=[record.model_dump() for record in (kg_response.records or [])]
    )


@router.post(
    "/v1/graph/concepts/by_ids",
    response_model=ConceptsByIdsResponse,
    status_code=status.HTTP_200_OK,
    response_model_exclude_none=True,
    tags=["shared-memories"],
)
async def fetch_concepts_by_ids(
    request_body: ConceptsByIdsRequest = Body(..., description="Concepts IDs"),
):
    # TODO: make knowledge provider support querying multiple concepts at a time
    try:
        tasks = [
            query_knowledge_graph_async(
                mas_id="mas_openclaw_test",
                concepts=[{"id": concept_id}],
                query_type="concept",
            )
            for concept_id in request_body.ids
        ]

        responses = await asyncio.gather(*tasks)

        concepts = [
            Concept(
                id=concept.id,
                name=concept.name,
                type=(concept.attributes or {}).get("concept_type", ""),
                description=concept.description or "",
            )
            for response in responses
            for record in (response.records or [])
            for concept in (record.concepts or [])
        ]

        logger.info(f"Returning {len(responses)} concepts: {concepts}")

        return ConceptsByIdsResponse(concepts=concepts)

    except Exception as exc:
        logger.exception(
            f"Knowledge graph query failed | concept IDs={request_body.ids}: {exc}",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to fetch concepts by IDs: {exc}",
        )



@router.post(
    "/v1/graph/paths",
    response_model=GraphPathsResponse,
    status_code=status.HTTP_200_OK,
    response_model_exclude_none=True,
    tags=["shared-memories"],
)
async def fetch_paths_by_ids(
    request_body: GraphPathsRequest = Body(...),
):
    # TODO: use limit and relations in knowledge graph query?
    try:
        resp = await query_knowledge_graph_async(
            depth=request_body.max_depth,
            mas_id="mas_openclaw_test",
            concepts=[{"id": request_body.source_id}, {"id": request_body.target_id}],
            query_type="path",
        )

        paths: list[Path] = []

        for rec in (resp.records or []):
            # Map concept id -> name (for from_name/to_name fallback)
            id_to_name: Dict[str, str] = {
                c.id: (c.name or "") for c in (rec.concepts or [])
            }

            edges: list[PathEdge] = []
            node_ids_in_order: list[str] = []

            for rel in (rec.relationships or []):
                if not rel.node_ids or len(rel.node_ids) < 2:
                    continue

                from_id, to_id = rel.node_ids[0], rel.node_ids[1]

                from_name = None
                to_name = None

                # Prefer relationship attributes if present, otherwise concept names
                if isinstance(rel.attributes, dict):
                    from_name = rel.attributes.get("source_name")
                    to_name = rel.attributes.get("target_name")

                from_name = from_name or id_to_name.get(from_id)
                to_name = to_name or id_to_name.get(to_id)

                edges.append(
                    PathEdge(
                        from_id=from_id,
                        relation=rel.relation,
                        to_id=to_id,
                        from_name=from_name,
                        to_name=to_name,
                    )
                )

                # Build an ordered node_id list from edges
                if not node_ids_in_order:
                    node_ids_in_order.extend([from_id, to_id])
                else:
                    if node_ids_in_order[-1] == from_id:
                        node_ids_in_order.append(to_id)
                    else:
                        # if edges aren't strictly chained, just ensure uniqueness
                        if from_id not in node_ids_in_order:
                            node_ids_in_order.append(from_id)
                        if to_id not in node_ids_in_order:
                            node_ids_in_order.append(to_id)

            symbolic = " -> ".join(
                [
                    f"{e.from_name or e.from_id}-[{e.relation}]->{e.to_name or e.to_id}"
                    for e in edges
                ]
            )

            paths.append(
                Path(
                    node_ids=node_ids_in_order or None,
                    edges=edges,
                    path_length=len(edges),
                    symbolic=symbolic,
                )
            )

        logger.info(f"Returning {len(paths)} paths: {paths}")

        return GraphPathsResponse(status="success", paths=paths)

    except Exception as exc:
        logger.exception(f"Knowledge graph query failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to fetch paths: {exc}",
        )
