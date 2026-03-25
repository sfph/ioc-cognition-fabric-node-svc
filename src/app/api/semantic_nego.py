import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Body, HTTPException, status, Path
from pydantic import BaseModel
from semantic_negotiation.app.agent.semantic_negotiation import SemanticNegotiationPipeline


router = APIRouter()
logger = logging.getLogger(__name__)

class Agent(BaseModel):
    id: str
    name: str

class InitiateNegotiationRequest(BaseModel):
    session_id: str
    content_text: str
    agents_raw: List[Agent]
    n_steps: Optional[int] = 20

class AgentReply(BaseModel):
    participant_id: str
    action: str
    offer: Optional[Dict[str, Any]] = None


class DecideRequest(BaseModel):
    session_id: str
    agent_replies: List[AgentReply]

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
):
    try:
        result = pipeline.execute(
            session_id=req.session_id,
            content_text=req.content_text,
            agents_raw=[agent.model_dump() for agent in req.agents_raw],
            n_steps=req.n_steps,
        )
        return result
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/workspaces/{workspace_id}/multi-agentic-systems/{mas_id}/semantic-negotiation/decide",
    status_code=status.HTTP_200_OK,
    # response_model=CreateOrUpdateResponse,
    response_model_exclude_none=True,
    tags=["semantic-negotiation"],
)
def decide_negotiation(req: DecideRequest):
    try:
        result = pipeline.execute(
            session_id=req.session_id,
            agent_replies=[reply.model_dump() for reply in req.agent_replies]
        )
        return result
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))
