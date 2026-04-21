import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from sqlmodel import Session, select
from app.database import engine
from app.models import (
    SessionRecord, SessionStateObj, CreateSessionRequest, ChatRequest, ReviewAssumptionsRequest
)
from app.services.llm_agent import process_chat_stream
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.post("", response_model=SessionRecord)
def create_session(request: CreateSessionRequest):
    new_state = SessionStateObj(layer=request.layer, brief=request.brief)
    record = SessionRecord(
        layer=request.layer,
        brief=request.brief,
        state_json=new_state.model_dump_json()
    )
    with Session(engine) as db_session:
        db_session.add(record)
        db_session.commit()
        db_session.refresh(record)
        return record

@router.get("")
def list_sessions():
    with Session(engine) as db_session:
        statement = select(SessionRecord).order_by(SessionRecord.created_at.desc())
        results = db_session.exec(statement).all()
        # Return a light representation
        return [{"id": r.id, "layer": r.layer, "brief": r.brief, "created_at": r.created_at} for r in results]

@router.get("/{session_id}", response_model=SessionStateObj)
def get_session(session_id: str):
    with Session(engine) as db_session:
        record = db_session.get(SessionRecord, session_id)
        if not record:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Hydrate back into Pydantic model
        state_dict = json.loads(record.state_json)
        return SessionStateObj(**state_dict)

@router.post("/{session_id}/chat")
async def chat_with_agent(session_id: str, request: ChatRequest, req: Request):
    with Session(engine) as db_session:
        record = db_session.get(SessionRecord, session_id)
        if not record:
            raise HTTPException(status_code=404, detail="Session not found")
            
        state_dict = json.loads(record.state_json)
        state_obj = SessionStateObj(**state_dict)
        
    return EventSourceResponse(process_chat_stream(session_id, state_obj, request.message))

@router.post("/{session_id}/review")
def review_assumptions(session_id: str, payload: ReviewAssumptionsRequest):
    with Session(engine) as db_session:
        record = db_session.get(SessionRecord, session_id)
        if not record:
            raise HTTPException(status_code=404, detail="Session not found")
            
        state_dict = json.loads(record.state_json)
        state_obj = SessionStateObj(**state_dict)
        
        # Move assumptions to decisions if accepted
        for item_id in payload.accepted:
            if item_id in state_obj.assumptions:
                assumption = state_obj.assumptions.pop(item_id)
                from app.models import Decision
                state_obj.decisions[item_id] = Decision(value=assumption.value, source="user")
                
        # Override values
        for item_id, override_val in payload.overrides.items():
            if item_id in state_obj.assumptions:
                state_obj.assumptions.pop(item_id)
                state_obj.decisions[item_id] = Decision(value=override_val, source="user")
                
        # Save changes
        record.state_json = state_obj.model_dump_json()
        db_session.add(record)
        db_session.commit()
        db_session.refresh(record)
        
    return {"status": "success", "message": "Assumptions reviewed and updated"}

from pydantic import BaseModel
class NameUpdate(BaseModel):
    name: str

@router.put("/{session_id}/name")
def update_session_name(session_id: str, payload: NameUpdate):
    with Session(engine) as db_session:
        record = db_session.get(SessionRecord, session_id)
        if not record:
            raise HTTPException(status_code=404, detail="Session not found")
            
        state_dict = json.loads(record.state_json)
        state_obj = SessionStateObj(**state_dict)
        state_obj.name = payload.name
        
        record.state_json = state_obj.model_dump_json()
        record.updated_at = datetime.utcnow()
        db_session.add(record)
        db_session.commit()
        
        return {"status": "success", "name": state_obj.name}

@router.delete("/{session_id}")
def delete_session(session_id: str):
    with Session(engine) as db_session:
        record = db_session.get(SessionRecord, session_id)
        if not record:
            raise HTTPException(status_code=404, detail="Session not found")
        db_session.delete(record)
        db_session.commit()
        return {"status": "success", "message": "Session deleted"}
