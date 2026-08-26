from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.db.models import TranscriptChunk
from app.ingestion.embeddings import embed_text

TOP_K = 5

# Cosine distance threshold below which a chunk counts as "covered".
# Calibrated empirically against this corpus (see agent-transcripts/README.md):
# on-topic queries (referral programs, activation/retention) scored 0.21-0.29;
# off-topic queries (cake recipes, movie plots) scored 0.42-0.47. 0.35 sits
# with margin on both sides of that observed gap. Not a universal constant —
# worth revisiting against PRD.md §3's ~20-30 question eval set once it exists.
MAX_DISTANCE = 0.35


@dataclass
class RetrievedChunk:
    chunk_id: str
    episode_title: str
    episode_source_url: str
    chunk_text: str
    start_timestamp: str
    distance: float


def retrieve(db: DBSession, query: str, top_k: int = TOP_K) -> list[RetrievedChunk]:
    """Embed the query and return the top-k chunks that clear MAX_DISTANCE.

    Empty list is the normal "not covered" signal, not an error — per
    architecture.md §4 step 3 and §8. `top_k` is overridable since
    ship30_essay needs broader source material than a single grounded_qa
    answer (Phase 5).
    """
    query_embedding = embed_text(query)
    distance = TranscriptChunk.embedding.cosine_distance(query_embedding)

    rows = db.execute(
        select(TranscriptChunk, distance.label("distance"))
        .where(distance < MAX_DISTANCE)
        .order_by(distance)
        .limit(top_k)
    ).all()

    return [
        RetrievedChunk(
            chunk_id=str(chunk.id),
            episode_title=chunk.episode_title,
            episode_source_url=chunk.episode_source_url,
            chunk_text=chunk.chunk_text,
            start_timestamp=chunk.start_timestamp,
            distance=dist,
        )
        for chunk, dist in rows
    ]
