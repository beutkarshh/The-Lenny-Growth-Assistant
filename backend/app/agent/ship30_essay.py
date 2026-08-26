from typing import Callable

from sqlalchemy.orm import Session as DBSession

from app.agent.retrieval import RetrievedChunk, retrieve
from app.agent.ship30_prompt import SHIP30_SYSTEM_PROMPT
from app.agent.tools import chunks_to_citations
from app.db.models import TranscriptChunk

# Broader than grounded_qa's 5 — an essay needs more source material than a
# single conversational answer.
ESSAY_TOP_K = 15

NOT_ENOUGH_MATERIAL_MESSAGE = (
    "Not enough grounded material was found in the available transcripts to write "
    "a properly sourced essay on this topic. Tell the user this explicitly rather "
    "than generating an essay without adequate grounding."
)


def _gather_grounding(db: DBSession, messages: list[dict]) -> list[RetrievedChunk]:
    """Prefer the session's own accumulated grounded_qa citations over a fresh
    retrieval call — per PRD.md §6 flow 4, the essay synthesizes what was
    ALREADY discussed and grounded in the conversation, not a new topic.
    These chunks were already verified relevant by a real similarity search
    when grounded_qa first retrieved them, so distance=0.0 here is a marker
    ("already verified"), not a fresh score.

    Falls back to a fresh, broader retrieval on the latest user message only
    if the session has no prior grounding yet (e.g. "write an essay about X"
    with no preceding Q&A) — same reasoning as agent/tools.py's
    resolve_search_text: don't trust an LLM-supplied topic argument when a
    deterministic source is available.
    """
    accumulated_citations: list[dict] = []
    for m in messages:
        if m.get("citations"):
            accumulated_citations.extend(m["citations"])

    if accumulated_citations:
        seen_ids: set[str] = set()
        chunks = []
        for citation in accumulated_citations:
            chunk_id = citation["chunk_id"]
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            chunk = db.get(TranscriptChunk, chunk_id)
            if chunk is not None:
                chunks.append(
                    RetrievedChunk(
                        chunk_id=str(chunk.id),
                        episode_title=chunk.episode_title,
                        episode_source_url=chunk.episode_source_url,
                        chunk_text=chunk.chunk_text,
                        start_timestamp=chunk.start_timestamp,
                        distance=0.0,
                    )
                )
        return chunks

    user_turns = [m["content"] for m in messages if m["role"] == "user"]
    if not user_turns:
        return []
    return retrieve(db, user_turns[-1], top_k=ESSAY_TOP_K)


def generate_essay(
    db: DBSession, messages: list[dict], generate_text: Callable[[str, str], str]
) -> tuple[str | None, list[dict]]:
    """Returns (essay_markdown, citations). essay_markdown is None when there
    isn't enough grounded material — the caller should surface that like
    grounded_qa's "not covered" fallback, never generate ungrounded prose.
    `generate_text(system, user) -> str` is the active provider's plain
    (non-tool-calling) completion function.
    """
    chunks = _gather_grounding(db, messages)
    if not chunks:
        return None, []

    citations = chunks_to_citations(chunks)
    context = "\n\n---\n\n".join(
        f"[Source: {c.episode_title}, at {c.start_timestamp}]\n{c.chunk_text}" for c in chunks
    )
    user_prompt = f"Write the essay based on the following grounded source material:\n\n{context}"
    essay_markdown = generate_text(SHIP30_SYSTEM_PROMPT, user_prompt)
    return essay_markdown, citations
