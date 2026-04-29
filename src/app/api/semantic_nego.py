import logging
import time
from typing import List, Optional, Dict, Any, Literal

from caching.app.agent import CachingLayer
from fastapi import (
    APIRouter,
    Body,
    HTTPException,
    Path,
    status,
    Depends,
    BackgroundTasks,
)
from ingestion.app.agent import KnowledgeProcessor
from ingestion.app.agent.concept_vector_store import VectorStore
from ingestion.app.agent.ingest_data import IngestDataService
from ingestion.app.agent.service import ConceptRelationshipExtractionService
from pydantic import BaseModel
from requests import session
from semantic_negotiation.app.agent.semantic_negotiation import (
    SemanticNegotiationInputError,
    SemanticNegotiationPipeline,
)


from src.app.api.shared_memory import (
    get_vector_cache_layer_for_mas,
    get_rag_cache_layer_for_mas,
)
from src.app.config.config import (
    LLM_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
    APP_PORT
)

from src.app.utils.mgmt_plane_client import check_workspace_and_mas
from src.app.utils.utils import upsert_shared_memories_to_db_and_cache

router = APIRouter()
logger = logging.getLogger(__name__)


class Agent(BaseModel):
    """Participant metadata for a semantic negotiation session."""

    id: str
    """Unique agent identifier."""

    name: str
    """Human-readable agent name."""


class InitiateNegotiationRequest(BaseModel):
    """Request body to start a new semantic negotiation session."""

    session_id: str
    """Client-provided session identifier.

    Notes:
        Currently assumed globally unique (not scoped by workspace/mas).
    """

    content_text: str
    """The negotiation prompt/context used to initialize the session."""

    agents: List[Agent]
    """List of participating agents."""

    n_steps: Optional[int] = 20
    """Maximum negotiation steps.

    If omitted, defaults to 20.
    """


class AgentReply(BaseModel):
    """A single agent reply used to advance an existing session."""

    agent_id: str
    """Agent identifier (must match one of the initiated agents)."""

    action: Literal["accept", "reject", "counter_offer"]
    """Agent action.

    Allowed values:
        - ``accept``
        - ``reject``
        - ``counter_offer``
    """

    offer: Optional[Dict[str, Any]] = None
    """Optional structured offer payload.

    Required when ``action`` is ``counter_offer``.
    """


class DecideRequest(BaseModel):
    """Request body to advance an existing semantic negotiation session."""

    session_id: str
    """Session identifier previously provided to the start endpoint."""

    agent_replies: List[AgentReply]
    """Replies produced by agents since the last step."""


pipeline = SemanticNegotiationPipeline(n_steps=20)


@router.post(
    "/workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/semantic-negotiation/start",
    status_code=status.HTTP_200_OK,
    # response_model=CreateOrUpdateResponse,
    response_model_exclude_none=True,
    tags=["semantic-negotiation"],
)
async def start_negotiation(
    req: InitiateNegotiationRequest = Body(...),
    workspace_id: str = Path(..., description="Workspace ID"),
    mas_id: str = Path(..., description="Multi-Agentic System ID"),
    _: None = Depends(check_workspace_and_mas),
):
    """Start a semantic negotiation session.

    Route:
        POST /workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/semantic-negotiation/start

    Body:
        See :class:`InitiateNegotiationRequest`.

    Returns:
        The pipeline execution result (shape defined by the semantic negotiation library).

    Notes:
        ``workspace_id`` and ``mas_id`` are currently included for route consistency with
        other APIs, but ``session_id`` is assumed globally unique (not scoped by workspace/mas).
    """
    try:
        result = await pipeline.async_execute(
            session_id=req.session_id,
            content_text=req.content_text,
            agents_raw=[agent.model_dump() for agent in req.agents],
            n_steps=req.n_steps,
            workspace_id=workspace_id,
            mas_id=mas_id,
            fabric_node_base_url=f"http://127.0.0.1:{APP_PORT}",
            agent_names=[agent.name for agent in req.agents],
        )
        return result
    except SemanticNegotiationInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Unhandled error in semantic negotiation execute()")
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error",
        )


@router.post(
    "/workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/semantic-negotiation/decide",
    status_code=status.HTTP_200_OK,
    # response_model=CreateOrUpdateResponse,
    response_model_exclude_none=True,
    tags=["semantic-negotiation"],
)
async def decide_negotiation(
    req: DecideRequest = Body(...),
    workspace_id: str = Path(..., description="Workspace ID"),
    mas_id: str = Path(..., description="Multi-Agentic System ID"),
    _: None = Depends(check_workspace_and_mas),
    vector_cache_layer: CachingLayer = Depends(get_vector_cache_layer_for_mas),
    rag_cache_layer: CachingLayer = Depends(get_rag_cache_layer_for_mas),
    background_tasks: BackgroundTasks = None,
):
    """Advance a semantic negotiation session.

    Route:
        POST /workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/semantic-negotiation/decide

    Body:
        See :class:`DecideRequest`.

    Returns:
        The pipeline execution result (shape defined by the semantic negotiation library).

    Errors:
        - 404 if the session does not exist (start it first).
        - 400 for input validation errors raised by the pipeline.

    Notes:
        ``workspace_id`` and ``mas_id`` are currently included for route consistency with
        other APIs, but ``session_id`` is assumed globally unique (not scoped by workspace/mas).
    """
    if req.session_id not in pipeline._sessions:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Session {req.session_id} not found. Please first initiate a "
                f"session via the "
                f"'/workspaces/{{workspace_id}}/multi-agentic-systems/{{mas_id}}/semantic-negotiation/start' endpoint."
            ),
        )

    # Stamp wall-clock time around each phase of the handler and attach a
    # ``_timing`` envelope to the response so callers can localise /decide
    # latency without log-scraping.  Additive, backwards-compatible: callers
    # that don't know about ``_timing`` simply ignore it.
    t0 = time.perf_counter()

    try:
        result = await pipeline.async_execute(
            session_id=req.session_id,
            agent_replies=[
                {**reply.model_dump(), "participant_id": reply.agent_id}
                for reply in req.agent_replies
            ],

        )

    except SemanticNegotiationInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Unhandled error in semantic negotiation execute()")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    t_pipeline_done = time.perf_counter()

    def to_dict(obj):
        if isinstance(obj, dict):
            return {k: to_dict(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [to_dict(v) for v in obj]
        if hasattr(obj, "__dict__"):
            return {k: to_dict(v) for k, v in vars(obj).items()}
        return obj

    converted_result = to_dict(result)

    t_serialised = time.perf_counter()

    has_agreement = converted_result.get("status", "") == "agreed"

    sstp_commit_message = converted_result.get("final_result", {})

    # Only persist the data to DB and cache if agreement is reached
    if has_agreement:
        background_tasks.add_task(
            persist_negotiation_agreement_background,
            result=sstp_commit_message,
            session_id=req.session_id,
            workspace_id=workspace_id,
            mas_id=mas_id,
            vector_cache_layer=vector_cache_layer,
            rag_cache_layer=rag_cache_layer,
        )

    # Attach the timing envelope.  Merge (don't overwrite) so any envelope
    # produced inside the pipeline (e.g. by the engines repo) is preserved.
    if isinstance(result, dict):
        timing = result.setdefault("_timing", {})
        timing["pipeline_ms"] = round((t_pipeline_done - t0) * 1000, 2)
        timing["to_dict_ms"] = round((t_serialised - t_pipeline_done) * 1000, 2)
        # Total covers from t0 (post-deps, post-validation) — middleware
        # adds route_handler_ms separately for the full wall-clock view.
        timing["pipeline_plus_persist_setup_ms"] = round(
            (time.perf_counter() - t0) * 1000, 2
        )
        # Merge per-stage timings collected by middleware and deps.
        # Includes route_handler_ms (full middleware-to-here wall-clock)
        # and individual deps (check_workspace_and_mas_ms,
        # vector_cache_layer_ms, rag_cache_layer_ms).
        try:
            from src.app.api._request_timing import timing_snapshot

            snap = timing_snapshot()
            req_started = snap.pop("request_started_perf", None)
            snap.pop("request_finished_perf", None)  # set by middleware after this
            if req_started is not None:
                timing["route_handler_ms"] = round(
                    (time.perf_counter() - req_started) * 1000, 2
                )
            timing.update(snap)
        except Exception:  # never let instrumentation break the call
            logger.exception("per-request timing snapshot failed")

    return result


async def persist_negotiation_agreement_background(
    *,
    result: dict,
    session_id: str,
    workspace_id: str,
    mas_id: str,
    vector_cache_layer: CachingLayer,
    rag_cache_layer: CachingLayer,
):
    logger.info(f"persisting negotiation agreement to DB and cache: {result}")

    try:
        concept_service = ConceptRelationshipExtractionService(
            llm_model=LLM_MODEL,
            llm_api_key=LLM_API_KEY,
            llm_base_url=LLM_BASE_URL,
        )

        processor = KnowledgeProcessor(
            enable_embeddings=True,
            enable_dedup=False,
        )

        ingest_service = IngestDataService(concept_service=concept_service)

        ingested_result = ingest_service.ingest(
            records=[result],
            request_id=session_id,
            format_descriptor="semneg",
        )
        processed_result = processor.process(ingested_result)

        await upsert_shared_memories_to_db_and_cache(
            result=processed_result,
            mas_id=mas_id,
            workspace_id=workspace_id,
            request_id=session_id,
            vector_store=VectorStore(
                cache_layer=vector_cache_layer,
                rag_cache_layer=rag_cache_layer,
            ),
        )

        logger.info(
            "Persisted negotiation agreement to shared memory | workspace=%s mas=%s session_id=%s",
            workspace_id,
            mas_id,
            session_id,
        )
    except Exception:
        logger.exception(
            "Failed to persist negotiation agreement | workspace=%s mas=%s session_id=%s",
            workspace_id,
            mas_id,
            session_id,
        )
