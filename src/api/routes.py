"""API route handlers."""

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.api.dependencies import db_dep, read_body_with_limit
from src.api.schemas import (
    RecallRequest,
    RecallResponse,
    SearchRequest,
    SearchResponse,
    TurnCreateRequest,
    TurnCreateResponse,
    MemorySchema,
)
from src.services.memory_service import DeletionService, MemoryQueryService
from src.services.recall_service import RecallService
from src.services.turn_service import TurnService
from src.core.health import readiness_check

router = APIRouter()

_turn_service = TurnService()
_recall_service = RecallService()
_memory_service = MemoryQueryService()
_deletion_service = DeletionService()


@router.get("/health")
def health(db: Session = Depends(db_dep)):
    payload, ready = readiness_check(db)
    if not ready:
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.post("/turns", status_code=status.HTTP_201_CREATED, response_model=TurnCreateResponse)
async def create_turn(
    request: Request,
    db: Session = Depends(db_dep),
) -> TurnCreateResponse:
    body = await read_body_with_limit(request)
    payload = TurnCreateRequest.model_validate_json(body)
    turn = _turn_service.create_turn(db, payload)
    return TurnCreateResponse(id=turn.id)


@router.post("/recall", response_model=RecallResponse)
def recall(payload: RecallRequest, db: Session = Depends(db_dep)) -> RecallResponse:
    return _recall_service.recall(db, payload)


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(db_dep)) -> SearchResponse:
    return _recall_service.search(db, payload)


@router.get("/users/{user_id}/memories", response_model=list[MemorySchema])
def get_user_memories(user_id: str, db: Session = Depends(db_dep)) -> list[MemorySchema]:
    return _memory_service.list_user_memories(db, user_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, db: Session = Depends(db_dep)) -> Response:
    _deletion_service.delete_session(db, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: Session = Depends(db_dep)) -> Response:
    _deletion_service.delete_user(db, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
