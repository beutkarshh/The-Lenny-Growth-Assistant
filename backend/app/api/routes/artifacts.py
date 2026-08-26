from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.agent.runner import get_generate_text
from app.agent.ship30_essay import NOT_ENOUGH_MATERIAL_MESSAGE, generate_essay
from app.core.errors import AppError
from app.db.models import Artifact, Session
from app.db.session import get_db
from app.schemas.artifact import ArtifactOut

router = APIRouter()


def _to_artifact_out(artifact: Artifact) -> ArtifactOut:
    return ArtifactOut(
        id=artifact.id,
        session_id=artifact.session_id,
        type=artifact.type,
        content=artifact.content,
        created_at=artifact.created_at,
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
def get_artifact(artifact_id: UUID, db: DBSession = Depends(get_db)) -> ArtifactOut:
    artifact = db.get(Artifact, artifact_id)
    if artifact is None:
        raise AppError(404, "ARTIFACT_NOT_FOUND", f"Artifact {artifact_id} not found")
    return _to_artifact_out(artifact)


@router.post("/sessions/{session_id}/artifacts", response_model=ArtifactOut, status_code=201)
def create_artifact(session_id: UUID, db: DBSession = Depends(get_db)) -> ArtifactOut:
    """Direct trigger for ship30_essay, bypassing chat intent-routing — the
    endpoint itself already signals intent. Same generation logic
    POST /sessions/{id}/messages uses when routing selects ship30_essay."""
    session = db.get(Session, session_id)
    if session is None:
        raise AppError(404, "SESSION_NOT_FOUND", f"Session {session_id} not found")

    history = [
        {"role": m.role, "content": m.content, "citations": m.citations} for m in session.messages
    ]
    essay_markdown, citations = generate_essay(db, history, get_generate_text())
    if essay_markdown is None:
        raise AppError(422, "NOT_ENOUGH_MATERIAL", NOT_ENOUGH_MATERIAL_MESSAGE)

    artifact = Artifact(session_id=session.id, type="markdown", content=essay_markdown)
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return _to_artifact_out(artifact)
