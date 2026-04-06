import asyncio
import logging
import json

from caching.app.agent import CachingLayer
from caching.app.agent.caching_layer_manager import CachingLayerManager
from evidence.app.api.schemas import (
    ReasonerCognitionRequest,
    Header,
    RequestPayload,
    NeighborsResponse,
    ConceptsByIdsRequest,
    ConceptsByIdsResponse,
    Concept,
    GraphPathsResponse,
    GraphPathsRequest,
    PathEdge,
    Path,
)
from evidence.app.data.http_repo import HttpDataRepository
from fastapi import APIRouter, Body, HTTPException, status, Depends
from fastapi import Path as ApiPath
from typing import List, Optional, Dict, Any, Set

from ingestion.app.agent import KnowledgeProcessor
from ingestion.app.agent.concept_vector_store import VectorStore
from ingestion.app.agent.ingest_data import IngestDataService
from knowledge_memory import query_knowledge_graph_async

from ingestion.app.agent.service import ConceptRelationshipExtractionService

from fastapi import Request

from src.app.api.schemas import (
    CreateOrUpdateRequest,
    QueryResponse,
    QueryRequest,
    CreateOrUpdateResponse,
)
from src.app.config.config import (
    LLM_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
    APP_PORT,
)
from src.app.utils.mgmt_plane_client import check_workspace_and_mas
from src.app.utils.utils import upsert_shared_memories_to_db_and_cache

router = APIRouter()
logger = logging.getLogger(__name__)


def get_vector_cache_manager(request: Request) -> CachingLayerManager:
    """Get the global vector cache manager."""
    return request.app.state.vector_cache_manager


def get_rag_cache_manager(request: Request) -> CachingLayerManager:
    """Get the global RAG cache manager."""
    return request.app.state.rag_cache_manager


def get_embed_fn(request: Request):
    """Get the embedding function."""
    return request.app.state.embed_fn


def get_vector_cache_layer_for_mas(
    mas_id: str = ApiPath(..., description="Multi-Agentic System ID"),
    manager: CachingLayerManager = Depends(get_vector_cache_manager),
    embed_fn=Depends(get_embed_fn),
) -> CachingLayer:
    """Get or create an isolated cache layer for the given mas_id.

    This dependency automatically extracts mas_id from the path and
    retrieves/creates the appropriate cache layer.

    Args:
        mas_id: Multi-Agentic System ID for isolation
        manager: The CachingLayerManager instance
        embed_fn: Embedding function for the cache layer (required for text-based
                  similarity queries)

    Returns:
        CachingLayer instance isolated to this mas_id
    """
    cache = manager.get_cache(mas_id)
    if cache is None:
        logger.info(f"Cache miss: Creating new vector cache layer for mas_id={mas_id}")
        cache = manager.create_cache(
            cache_id=mas_id,
            vector_dimension=384,  # granite-embedding-30m-english dimension
            metric="l2",
            embed_fn=embed_fn,  # Required for text-based similarity search
        )
    else:
        logger.info(f"Cache hit: Using existing cache for mas_id={mas_id}")
    return cache


def get_rag_cache_layer_for_mas(
    mas_id: str = ApiPath(..., description="Multi-Agentic System ID"),
    manager: CachingLayerManager = Depends(get_rag_cache_manager),
    embed_fn=Depends(get_embed_fn),
) -> CachingLayer:
    """Get or create an isolated cache layer for the given mas_id.

    This dependency automatically extracts mas_id from the path and
    retrieves/creates the appropriate cache layer.

    Args:
        mas_id: Multi-Agentic System ID for isolation
        manager: The CachingLayerManager instance
        embed_fn: Embedding function for the cache layer (required for text-based
                  similarity queries)

    Returns:
        CachingLayer instance isolated to this mas_id
    """
    cache = manager.get_cache(mas_id)
    if cache is None:
        logger.info(f"Cache miss: Creating new RAG cache layer for mas_id={mas_id}")
        cache = manager.create_cache(
            cache_id=mas_id,
            vector_dimension=384,  # granite-embedding-30m-english dimension
            metric="l2",
            embed_fn=embed_fn,  # Required for text-based similarity search
        )
    else:
        logger.info(f"Cache hit: Using existing RAG cache for mas_id={mas_id}")
    return cache


def get_cache_layer_for_query(
    mas_id: str = ApiPath(..., description="Multi-Agentic System ID"),
    manager: CachingLayerManager = Depends(get_vector_cache_manager),
) -> CachingLayer:
    """Get cache layer for query operations (read-only).

    Returns 404 if cache doesn't exist for the MAS, indicating no data
    has been stored yet.

    Args:
        mas_id: Multi-Agentic System ID for isolation
        manager: The CachingLayerManager instance

    Returns:
        CachingLayer instance isolated to this mas_id

    Raises:
        HTTPException: 404 if no cache exists for this MAS
    """
    cache = manager.get_cache(mas_id)
    if cache is None:
        logger.warning(f"No cache found for mas_id={mas_id}, no data in shared memory")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No shared memory data found for MAS {mas_id}. Create memories first.",
        )
    logger.info(f"Cache hit: Using existing cache for mas_id={mas_id}")
    return cache


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
    vector_cache_layer: CachingLayer = Depends(get_vector_cache_layer_for_mas),
    rag_cache_layer: CachingLayer = Depends(get_rag_cache_layer_for_mas),
    _: None = Depends(check_workspace_and_mas),
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
        llm_model=LLM_MODEL,
        llm_api_key=LLM_API_KEY,
        llm_base_url=LLM_BASE_URL,
    )

    processor = KnowledgeProcessor(enable_embeddings=True, enable_dedup=False)
    try:
        ingest_service = IngestDataService(concept_service=concept_service)
        ingestion_result = ingest_service.ingest(
            records=extraction_payload.data,
            request_id=request_id,
            format_descriptor=extraction_payload.metadata.format,
        )
        processed_result = processor.process(ingestion_result)
    except Exception as exc:
        logger.exception(
            "Failed to ingest data via Cognition Engine | workspace=%s mas=%s",
            workspace_id,
            mas_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to create or update shared memories, error: {exc}",
        )

    vector_store = VectorStore(
        cache_layer=vector_cache_layer, rag_cache_layer=rag_cache_layer
    )

    kg_resp = await upsert_shared_memories_to_db_and_cache(
        mas_id, workspace_id, request_id, processed_result, vector_store
    )

    logger.info(f"create or update shared memories succeeded: {kg_resp}")

    return CreateOrUpdateResponse(
        response_id=request_id,
        message=kg_resp.message,
    )


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
    vector_cache_layer: CachingLayer = Depends(get_vector_cache_layer_for_mas),
    rag_cache_layer: CachingLayer = Depends(get_rag_cache_layer_for_mas),
    _: None = Depends(check_workspace_and_mas),
):
    # Avoid importing heavy runtime dependencies at module load time
    from evidence.app.agent.evidence import process_evidence

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

    repo = HttpDataRepository(
        base_url=f"http://localhost:{APP_PORT}",
        workspace_id=workspace_id,
        mas_id=mas_id,
    )

    try:
        eg_response = await process_evidence(
            request,
            repo_adapter=repo,
            cache_layer=vector_cache_layer,
            rag_cache_layer=rag_cache_layer,
        )
    except Exception as exc:
        logger.exception(
            "Failed to process evidence | workspace=%s mas=%s",
            workspace_id,
            mas_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to process evidence: {exc}",
        )

    logger.debug(f"Evidence gathering response: {eg_response}")

    # extract evidence fields
    evidence = {}
    if getattr(eg_response, "records", None):
        rec0 = eg_response.records[0]
        content = getattr(rec0, "content", None)
        if isinstance(content, dict):
            evidence = content.get("evidence") or {}

    evidence_status = evidence.get("status")  # e.g. "insufficient"
    final_response = evidence.get("final_response")  # may be missing

    if final_response == "The evidence does not support an answer to this question.":
        logger.error(
            f"Insufficient evidence to answer user intent, "
            f"eg_response: {eg_response}"
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insufficient evidence to answer provided user intent",
        )

    if final_response:
        message = final_response
    elif evidence_status:
        message = f"Evidence status: {evidence_status}"
    else:
        message = "evidence processed"

    return QueryResponse(
        response_id=request_id,
        message=message,
    )


@router.get(
    "/workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/graph/neighbors/{concept_id}",
    response_model=NeighborsResponse,
    status_code=status.HTTP_200_OK,
    response_model_exclude_none=True,
    include_in_schema=False,
    tags=["shared-memories"],
)
async def get_neighbors_by_id(
    workspace_id: str = ApiPath(..., description="Workspace ID"),
    mas_id: str = ApiPath(..., description="Multi-Agentic System ID"),
    concept_id: str = ApiPath(..., description="Concept ID"),
    _: None = Depends(check_workspace_and_mas),
):
    logger.info(
        "Querying neighbors | workspace=%s, mas=%s, concept_id=%s",
        workspace_id,
        mas_id,
        concept_id,
    )

    try:
        kg_response = await query_knowledge_graph_async(
            wksp_id=workspace_id,
            mas_id=mas_id,
            concepts=[{"id": concept_id}],
            query_type="neighbour",
        )
    except Exception as exc:
        logger.exception(
            "Failed to fetch neighbors by id from knowledge graph | workspace=%s mas=%s concept_id=%s",
            workspace_id,
            mas_id,
            concept_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to fetch concept: {exc}",
        )

    logger.info(
        f"{len(kg_response.records)} neighbor(s) found for concept {concept_id}"
    )

    logger.debug(f"Found neighbors: {kg_response.records}")

    return NeighborsResponse(
        records=[record.model_dump() for record in (kg_response.records or [])]
    )


@router.post(
    "/workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/graph/concepts/by_ids",
    response_model=ConceptsByIdsResponse,
    status_code=status.HTTP_200_OK,
    response_model_exclude_none=True,
    include_in_schema=False,
    tags=["shared-memories"],
)
async def fetch_concepts_by_ids(
    workspace_id: str = ApiPath(..., description="Workspace ID"),
    mas_id: str = ApiPath(..., description="Multi-Agentic System ID"),
    request_body: ConceptsByIdsRequest = Body(..., description="Concepts IDs"),
    _: None = Depends(check_workspace_and_mas),
):
    logger.info(
        "Querying concepts | workspace=%s, mas=%s, concept_ids=%s",
        workspace_id,
        mas_id,
        request_body.ids,
    )

    # TODO: make knowledge provider support querying multiple concepts at a time
    try:
        tasks = [
            query_knowledge_graph_async(
                wksp_id=workspace_id,
                mas_id=mas_id,
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

        logger.info(f"{len(responses)} concept(s) found for {request_body.ids}")
        logger.debug(f"Returning concepts: {concepts}")

        return ConceptsByIdsResponse(concepts=concepts)

    except Exception as exc:
        logger.exception(
            "Failed to fetch concepts by ids from knowledge graph | workspace=%s mas=%s concept_ids=%s",
            workspace_id,
            mas_id,
            request_body.ids,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to fetch concepts by IDs: {exc}",
        )


@router.post(
    "/workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/graph/paths",
    response_model=GraphPathsResponse,
    status_code=status.HTTP_200_OK,
    response_model_exclude_none=True,
    include_in_schema=False,
    tags=["shared-memories"],
)
async def fetch_paths_by_ids(
    workspace_id: str = ApiPath(..., description="Workspace ID"),
    mas_id: str = ApiPath(..., description="Multi-Agentic System ID"),
    request_body: GraphPathsRequest = Body(...),
    _: None = Depends(check_workspace_and_mas),
) -> GraphPathsResponse:
    logger.info(
        "Querying path | workspace=%s, mas=%s, source_id=%s, target_id=%s",
        workspace_id,
        mas_id,
        request_body.source_id,
        request_body.target_id,
    )

    try:
        # 1) Query KG for paths
        kg_resp = await query_knowledge_graph_async(
            wksp_id=workspace_id,
            mas_id=mas_id,
            depth=request_body.max_depth,
            concepts=[{"id": request_body.source_id}, {"id": request_body.target_id}],
            query_type="path",
        )

        allowed_relations: Set[str] = set(request_body.relations or [])
        limit: Optional[int] = request_body.limit

        paths: list[Path] = []

        # 2) Each record is assumed to represent a path candidate
        for rec in kg_resp.records or []:
            concepts = rec.concepts or []
            relationships = rec.relationships or []

            # Map concept id -> concept name
            id_to_name: Dict[str, str] = {
                c.id: (c.name or "") for c in concepts if getattr(c, "id", None)
            }

            # 3) Optionally filter relationships by allowed relations
            rels = [
                r
                for r in relationships
                if getattr(r, "node_ids", None)
                and len(r.node_ids) >= 2
                and (not allowed_relations or r.relation in allowed_relations)
            ]

            if not rels:
                continue

            # 4) Try to chain relationships into an ordered path
            #    Strategy:
            #      - Build adjacency from from_id -> [rel...]
            #      - Start from source_id if possible
            from_to_rels: Dict[str, list[Any]] = {}
            in_degree: Dict[str, int] = {}

            for r in rels:
                from_id, to_id = r.node_ids[0], r.node_ids[1]
                from_to_rels.setdefault(from_id, []).append(r)
                in_degree[to_id] = in_degree.get(to_id, 0) + 1
                in_degree.setdefault(from_id, in_degree.get(from_id, 0))

            start_id = request_body.source_id
            if start_id not in from_to_rels:
                # fallback: pick a node with 0 in-degree if possible
                zero_in = [
                    nid
                    for nid, deg in in_degree.items()
                    if deg == 0 and nid in from_to_rels
                ]
                if zero_in:
                    start_id = zero_in[0]
                else:
                    # last resort: just use the first relationship's from_id
                    start_id = rels[0].node_ids[0]

            ordered_rels: list[Any] = []
            visited_rel_ids: Set[str] = set()
            current = start_id

            # Greedy walk: pick the first unused outgoing rel each step
            # Stop on dead-end or when target reached
            while current in from_to_rels:
                next_rel = None
                for cand in from_to_rels[current]:
                    rid = (
                        getattr(cand, "id", None)
                        or f"{cand.node_ids[0]}->{cand.relation}->{cand.node_ids[1]}"
                    )
                    if rid not in visited_rel_ids:
                        next_rel = cand
                        visited_rel_ids.add(rid)
                        break

                if not next_rel:
                    break

                ordered_rels.append(next_rel)
                current = next_rel.node_ids[1]
                if current == request_body.target_id:
                    break

            # If chaining failed to include everything, fall back to filtered order
            if not ordered_rels:
                ordered_rels = rels

            # 5) Build edges and node_ids in order
            edges: list[PathEdge] = []
            node_ids_in_order: list[str] = []

            for r in ordered_rels:
                from_id, to_id = r.node_ids[0], r.node_ids[1]

                from_name = None
                to_name = None
                if isinstance(getattr(r, "attributes", None), dict):
                    from_name = r.attributes.get("source_name")
                    to_name = r.attributes.get("target_name")

                from_name = from_name or id_to_name.get(from_id)
                to_name = to_name or id_to_name.get(to_id)

                edges.append(
                    PathEdge(
                        from_id=from_id,
                        relation=r.relation,
                        to_id=to_id,
                        from_name=from_name,
                        to_name=to_name,
                    )
                )

                if not node_ids_in_order:
                    node_ids_in_order.extend([from_id, to_id])
                else:
                    # chain if possible; otherwise just append if new
                    if node_ids_in_order[-1] == from_id:
                        node_ids_in_order.append(to_id)
                    else:
                        if from_id not in node_ids_in_order:
                            node_ids_in_order.append(from_id)
                        if to_id not in node_ids_in_order:
                            node_ids_in_order.append(to_id)

            if not edges:
                continue

            symbolic = " -> ".join(
                f"{e.from_name or e.from_id}-[{e.relation}]->{e.to_name or e.to_id}"
                for e in edges
            )

            paths.append(
                Path(
                    node_ids=node_ids_in_order or None,
                    edges=edges,
                    path_length=len(edges),
                    symbolic=symbolic,
                )
            )

            # 6) Enforce limit across returned paths
            if limit is not None and 0 < limit <= len(paths):
                break

        logger.info(
            f"{len(paths)} path(s) found between {request_body.source_id} and {request_body.target_id}"
        )
        logger.info(f"Returning paths: {paths}")

        return GraphPathsResponse(status="success", paths=paths)

    except Exception as exc:
        logger.exception(
            "Failed to fetch paths by ids from knowledge graph | workspace=%s mas=%s source_id=%s target_id=%s",
            workspace_id,
            mas_id,
            request_body.source_id,
            request_body.target_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to fetch paths: {exc}",
        )
