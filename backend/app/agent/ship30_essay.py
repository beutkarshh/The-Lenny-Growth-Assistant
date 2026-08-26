import re
from typing import Callable

from sqlalchemy.orm import Session as DBSession

from app.agent.retrieval import RetrievedChunk, retrieve
from app.agent.ship30_prompt import SHIP30_SYSTEM_PROMPT
from app.agent.tools import chunks_to_citations
from app.db.models import TranscriptChunk

# Broader than grounded_qa's 5 — an essay needs more source material than a
# single conversational answer.
ESSAY_TOP_K = 15

# How many of the most recent user turns to pull accumulated citations from,
# rather than the entire session. Guards against a long, multi-topic session
# dumping citations from every guest ever discussed into one essay. PRD.md
# §6's own example flow is 2 grounded turns (a question, then a follow-up)
# before the essay ask; this adds a little headroom.
RECENT_TOPIC_TURNS = 3

# Maximum distinct episodes (guests) allowed to ground a single essay.
# Found necessary in Phase 8 after a real test — a single broad essay
# request ("what are important factors in the growth of the business"), on
# a session with NO prior grounded turns, fell into the fresh-retrieval
# fallback below and legitimately cleared MAX_DISTANCE against 10 different
# episodes at once (distances 0.29-0.345 — a broad query is close to the
# whole podcast's core subject, not a retrieval bug). The essay model then
# cross-attributed real quotes to the wrong guest among those 10 — despite
# the system prompt explicitly forbidding it. RECENT_TOPIC_TURNS alone does
# NOT catch this case, since it only bounds session *history*, and this
# failure had no history to bound. This cap bounds diversity within a
# single retrieval instead: fewer, more deeply-covered sources per essay is
# both easier for a small local model to attribute correctly and more in
# keeping with the Ship 30 format's own 3-5 section structure. See
# agent-transcripts/README.md, Phase 8, for the full investigation
# (including the earlier, incomplete diagnosis this constant corrects).
MAX_ESSAY_EPISODES = 4

NOT_ENOUGH_MATERIAL_MESSAGE = (
    "Not enough grounded material was found in the available transcripts to write "
    "a properly sourced essay on this topic. Tell the user this explicitly rather "
    "than generating an essay without adequate grounding."
)


def _recent_topic_messages(messages: list[dict]) -> list[dict]:
    """The tail of the conversation covering at most RECENT_TOPIC_TURNS user
    turns — the essay's actual topic, not everything ever discussed in the
    session. Walks backward from the end and stops once that many user
    messages have been passed, so a long session that drifted across many
    unrelated guests/topics doesn't dump all of them into one essay."""
    cutoff = 0
    user_turns_seen = 0
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user":
            user_turns_seen += 1
            if user_turns_seen > RECENT_TOPIC_TURNS:
                cutoff = i + 1
                break
    return messages[cutoff:]


def _cap_episode_diversity(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Keep only chunks from the first MAX_ESSAY_EPISODES distinct episodes
    encountered, in existing order (best-distance-first for a fresh
    retrieval, chronological for accumulated citations) — depth over
    breadth, so the essay model has fewer speakers to keep straight."""
    allowed_episodes: set[str] = set()
    kept = []
    for chunk in chunks:
        if chunk.episode_title not in allowed_episodes:
            if len(allowed_episodes) >= MAX_ESSAY_EPISODES:
                continue
            allowed_episodes.add(chunk.episode_title)
        kept.append(chunk)
    return kept


def _gather_grounding(db: DBSession, messages: list[dict]) -> list[RetrievedChunk]:
    """Prefer the session's own accumulated grounded_qa citations over a fresh
    retrieval call — per PRD.md §6 flow 4, the essay synthesizes what was
    ALREADY discussed and grounded in the conversation, not a new topic.
    These chunks were already verified relevant by a real similarity search
    when grounded_qa first retrieved them, so distance=0.0 here is a marker
    ("already verified"), not a fresh score.

    Only looks at the recent-topic tail (see _recent_topic_messages), not the
    whole session — otherwise a long, multi-topic session accumulates
    citations from every guest ever discussed, not just the one the essay
    is actually about.

    Falls back to a fresh, broader retrieval on the latest user message only
    if the session has no prior grounding yet (e.g. "write an essay about X"
    with no preceding Q&A) — same reasoning as agent/tools.py's
    resolve_search_text: don't trust an LLM-supplied topic argument when a
    deterministic source is available.
    """
    accumulated_citations: list[dict] = []
    for m in _recent_topic_messages(messages):
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
        return _cap_episode_diversity(chunks)

    user_turns = [m["content"] for m in messages if m["role"] == "user"]
    if not user_turns:
        return []
    return _cap_episode_diversity(retrieve(db, user_turns[-1], top_k=ESSAY_TOP_K))


def _guest_label(episode_title: str) -> str:
    """Episode titles are formatted "{descriptive title} | {Guest Name}
    (context)" for 52 of the 53 real episodes — e.g. "Why most product
    managers are unprepared for the demands of a real startup | Casey
    Winters". Used only to label source chunks in the essay-generation
    prompt (not citations, which keep the full title for the UI's citation
    chips): with up to MAX_ESSAY_EPISODES distinct sources in one prompt,
    burying the guest's name at the end of a long descriptive title made it
    easy for the model to lose track of who said what — see
    agent-transcripts/README.md, Phase 8. Falls back to the full title
    unchanged if it doesn't contain " | " (one real episode has no pipe at
    all, but its title already leads with the guest's name)."""
    if " | " not in episode_title:
        return episode_title
    guest_part = episode_title.rsplit(" | ", 1)[-1]
    return re.sub(r"\s*\([^)]*\)\s*$", "", guest_part).strip()


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
        f"[Source: {_guest_label(c.episode_title)}, at {c.start_timestamp}]\n{c.chunk_text}" for c in chunks
    )
    user_prompt = f"Write the essay based on the following grounded source material:\n\n{context}"
    essay_markdown = generate_text(SHIP30_SYSTEM_PROMPT, user_prompt)
    return essay_markdown, citations
