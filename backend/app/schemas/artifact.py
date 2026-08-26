from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ArtifactOut(BaseModel):
    id: UUID
    session_id: UUID
    type: Literal["markdown", "html"]
    content: str
    created_at: datetime
