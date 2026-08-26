from sqlalchemy.orm import Session as DBSession

from app.agent.retrieval import RetrievedChunk, retrieve

NOT_COVERED_MESSAGE = (
    "No relevant material was found in the available transcripts for this query. "
    "Tell the user explicitly that this isn't covered in the source material, "
    "rather than answering from general knowledge."
)


def format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return NOT_COVERED_MESSAGE
    return "\n\n---\n\n".join(
        f"[Source: {c.episode_title}, at {c.start_timestamp}]\n{c.chunk_text}" for c in chunks
    )


def chunks_to_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    return [
        {
            "episode_title": c.episode_title,
            "episode_source_url": c.episode_source_url,
            "start_timestamp": c.start_timestamp,
            "chunk_id": c.chunk_id,
        }
        for c in chunks
    ]


def resolve_search_text(messages: list[dict]) -> str:
    """The LLM's tool-call query argument is never trusted for retrieval —
    the search text is always built deterministically from session history
    instead. Empirically (see agent-transcripts/README.md), llama3.2:3b
    unreliably formulates good retrieval queries: only ~1-in-3 to 1-in-4
    first-turn tool calls used a full question rather than a terse fragment
    that measurably hurt embedding-based retrieval, and letting it reformulate
    follow-ups fared even worse (3/5 = 60% success across repeated trials).

    First turn: use the user's raw message directly — naturally well-formed,
    nothing to reformulate.
    Follow-up: concatenate the previous user question with the current
    message, rather than trusting the LLM's own synthesis of the two. Not
    as precise as a good LLM-written reformulation would be, but a fixed
    string the model can't get wrong is preferable to one it gets wrong
    40% of the time.
    """
    user_turns = [m["content"] for m in messages if m["role"] == "user"]
    if len(user_turns) <= 1:
        return user_turns[-1] if user_turns else ""
    return f"{user_turns[-2]} {user_turns[-1]}"


def grounded_qa_query(db: DBSession, query: str, captured_citations: list[dict]) -> str:
    """Shared retrieval logic behind the grounded_qa tool for both providers.

    Tool results are plain text on both Claude's Tool Runner and Ollama's
    /api/chat, so structured citation data can't travel back through the
    tool-calling mechanism itself. `captured_citations` is a mutable list
    the caller (each provider module) reads after the agent loop finishes,
    to attach as the persisted Message's `citations` field.
    """
    chunks = retrieve(db, query)
    captured_citations.extend(chunks_to_citations(chunks))
    return format_context(chunks)
