from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.message import MessageOut


class SessionCreate(BaseModel):
    # Hardcoded default until Phase 4 introduces LLM_PROVIDER config; matches
    # PRD.md's local-first framing (Ollama as the no-key-required default).
    llm_provider: Literal["claude", "ollama"] = "ollama"
    metadata: dict = Field(default_factory=dict)


class SessionOut(BaseModel):
    id: UUID
    created_at: datetime
    llm_provider: str
    metadata: dict


class SessionDetailOut(SessionOut):
    messages: list[MessageOut] = []
