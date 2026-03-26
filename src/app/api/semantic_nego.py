import logging
from typing import List, Optional, Dict, Any, Literal

from fastapi import APIRouter, Body, HTTPException, Path, status
from pydantic import BaseModel
from semantic_negotiation.app.agent.semantic_negotiation import (
    SemanticNegotiationInputError,
    SemanticNegotiationPipeline,
)


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
def start_negotiation(
    req: InitiateNegotiationRequest = Body(...),
    workspace_id: str = Path(..., description="Workspace ID"),
    mas_id: str = Path(..., description="Multi-Agentic System ID"),
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
        result = pipeline.execute(
            session_id=req.session_id,
            content_text=req.content_text,
            agents_raw=[agent.model_dump() for agent in req.agents],
            n_steps=req.n_steps,
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
def decide_negotiation(
    req: DecideRequest = Body(...),
    workspace_id: str = Path(..., description="Workspace ID"),
    mas_id: str = Path(..., description="Multi-Agentic System ID"),
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

    try:
        result = pipeline.execute(
            session_id=req.session_id,
            agent_replies=[
                {**reply.model_dump(), "participant_id": reply.agent_id}
                for reply in req.agent_replies
            ],
        )
        return result
    except SemanticNegotiationInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Unhandled error in semantic negotiation execute()")
        raise HTTPException(status_code=500, detail="Internal Server Error")
