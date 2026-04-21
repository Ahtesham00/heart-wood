from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField
from pydantic import ConfigDict
import uuid
from datetime import datetime, timezone
import json

class Decision(BaseModel):
    value: Any
    source: Literal["user", "inferred-confirmed"]

class Assumption(BaseModel):
    value: Any
    rationale: str

class Skipped(BaseModel):
    reason: str

class Artifacts(BaseModel):
    foundations_md: Optional[str] = None
    ui_spec_md: Optional[str] = None
    assumptions_md: Optional[str] = None
    html_mock: Optional[str] = None

class SessionStateObj(BaseModel):
    name: str = "New Project"
    layer: Literal[0, 1, 2, 3] = 0
    brief: str
    decisions: Dict[str, Decision] = Field(default_factory=dict)
    assumptions: Dict[str, Assumption] = Field(default_factory=dict)
    skipped: Dict[str, Skipped] = Field(default_factory=dict)
    open_questions: List[str] = Field(default_factory=list)
    transcript: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts: Artifacts = Field(default_factory=Artifacts)

from sqlalchemy.types import JSON
from sqlalchemy import Column
class SessionRecord(SQLModel, table=True):
    id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    layer: int = 0
    brief: str
    # Store the rest of the complicated structures as JSON
    state_json: str = SQLField(default="{}", description="JSON serialized SessionStateObj")
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))

class CreateSessionRequest(BaseModel):
    brief: str
    layer: Literal[0, 1] = 0

class ChatRequest(BaseModel):
    message: str

class ReviewAssumptionsRequest(BaseModel):
    # Mapping of item_id -> tuple of (accepted: bool, override_value: Optional[value])
    # Or just individual lists
    accepted: List[str] = []
    overrides: Dict[str, Any] = {}
