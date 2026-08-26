import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Embedding dimension matches Ollama's nomic-embed-text model — see architecture.md §6.
EMBEDDING_DIM = 768


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TranscriptChunk(Base):
    """A chunk of an episode transcript with its embedding, per architecture.md §2/§4."""

    __tablename__ = "transcript_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    episode_title: Mapped[str] = mapped_column(Text)
    episode_source_url: Mapped[str] = mapped_column(Text)
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    start_timestamp: Mapped[str] = mapped_column(String(16))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))


class Session(Base):
    """A chat session, per architecture.md §2. Artifact is added in Phase 5/6
    when the endpoints that use it exist."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    llm_provider: Mapped[str] = mapped_column(String(16))
    # Python attribute avoids the name "metadata", reserved by SQLAlchemy's
    # declarative Base (Base.metadata); the actual DB column is still "metadata"
    # per architecture.md §2.
    session_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    messages: Mapped[list["Message"]] = relationship(back_populates="session", order_by="Message.created_at")


class Message(Base):
    """A single turn in a session, per architecture.md §2.

    `artifact_id` is an addition beyond the original schema table, added in
    Phase 5: when ship30_essay produces an artifact, the frontend needs a way
    to know which message triggered it, to open the viewer panel. Nullable —
    only set for the assistant turn that created an artifact.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="messages")


class Artifact(Base):
    """A generated Markdown/HTML document, per architecture.md §2."""

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    type: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
