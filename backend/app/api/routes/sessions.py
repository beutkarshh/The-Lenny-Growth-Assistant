from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.agent.runner import run_agent
from app.core.errors import AppError
from app.db.models import Artifact, Message, Session
from app.db.session import get_db
from app.schemas.message import MessageCreate, MessageOut
from app.schemas.session import SessionCreate, SessionDetailOut, SessionOut, SessionSummaryOut

router = APIRouter()


def _to_session_out(session: Session) -> SessionOut:
    return SessionOut(
        id=session.id,
        created_at=session.created_at,
        llm_provider=session.llm_provider,
        metadata=session.session_metadata,
    )


def _to_message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=message.citations,
        artifact_id=message.artifact_id,
        created_at=message.created_at,
    )


def _get_session_or_404(session_id: UUID, db: DBSession) -> Session:
    session = db.get(Session, session_id)
    if session is None:
        raise AppError(404, "SESSION_NOT_FOUND", f"Session {session_id} not found")
    return session


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(payload: SessionCreate, db: DBSession = Depends(get_db)) -> SessionOut:
    session = Session(llm_provider=payload.llm_provider, session_metadata=payload.metadata)
    db.add(session)
    db.commit()
    db.refresh(session)
    return _to_session_out(session)


@router.get("/sessions", response_model=list[SessionSummaryOut])
def list_sessions(db: DBSession = Depends(get_db)) -> list[SessionSummaryOut]:
    """Added Phase 6 for the session sidebar (design.md §2) — see
    schemas/session.py's SessionSummaryOut docstring."""
    sessions = db.query(Session).order_by(Session.created_at.desc()).all()
    summaries = []
    for session in sessions:
        first_user_message = next((m for m in session.messages if m.role == "user"), None)
        preview = first_user_message.content[:120] if first_user_message else None
        summaries.append(
            SessionSummaryOut(
                **_to_session_out(session).model_dump(),
                first_message_preview=preview,
            )
        )
    return summaries


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
def get_session(session_id: UUID, db: DBSession = Depends(get_db)) -> SessionDetailOut:
    session = _get_session_or_404(session_id, db)
    return SessionDetailOut(
        **_to_session_out(session).model_dump(),
        messages=[_to_message_out(m) for m in session.messages],
    )


@router.post("/sessions/{session_id}/messages", response_model=MessageOut, status_code=201)
def send_message(session_id: UUID, payload: MessageCreate, db: DBSession = Depends(get_db)) -> MessageOut:
    session = _get_session_or_404(session_id, db)

    # Built from prior messages before adding the new one, then the new turn
    # is appended explicitly — avoids relying on relationship-refresh timing.
    # Citations travel alongside role/content here (not sent to the LLM APIs
    # directly — each provider strips them before the actual API call) so
    # ship30_essay can gather the session's already-grounded material without
    # a second DB round-trip.
    history = [
        {"role": m.role, "content": m.content, "citations": m.citations} for m in session.messages
    ]

    user_message = Message(session_id=session.id, role="user", content=payload.content)
    db.add(user_message)

    history.append({"role": "user", "content": payload.content, "citations": None})
    result = run_agent(db, history)

    artifact_id = None
    if result.artifact_content:
        artifact = Artifact(
            session_id=session.id,
            type=result.artifact_type or "markdown",
            content=result.artifact_content,
        )
        db.add(artifact)
        db.flush()  # assigns artifact.id without committing yet
        artifact_id = artifact.id

    assistant_message = Message(
        session_id=session.id,
        role="assistant",
        content=result.content,
        citations=result.citations or None,
        artifact_id=artifact_id,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return _to_message_out(assistant_message)
