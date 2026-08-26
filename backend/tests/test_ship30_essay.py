import uuid

from app.agent.ship30_essay import (
    MAX_ESSAY_EPISODES,
    RECENT_TOPIC_TURNS,
    _gather_grounding,
    _guest_label,
    _recent_topic_messages,
)
from app.db.models import TranscriptChunk


def test_guest_label_extracts_name_from_pipe_delimited_title():
    title = "Why most product managers are unprepared for the demands of a real startup | Casey Winters"
    assert _guest_label(title) == "Casey Winters"


def test_guest_label_strips_trailing_parenthetical_context():
    title = "Lessons from scaling Ramp | Sri Batchu (Ramp, Instacart, Opendoor)"
    assert _guest_label(title) == "Sri Batchu"


def test_guest_label_falls_back_to_full_title_when_no_pipe_present():
    title = "Gokul Rajaram on designing your product development process, and more"
    assert _guest_label(title) == title


def _insert_chunk(db_session, episode_title, embedding=None):
    chunk = TranscriptChunk(
        id=uuid.uuid4(),
        episode_title=episode_title,
        episode_source_url=f"https://youtube.com/watch?v={episode_title}",
        chunk_text="Some transcript text.",
        chunk_index=0,
        start_timestamp="00:00:00",
        embedding=embedding if embedding is not None else [0.0] * 768,
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def _citation_message(chunk):
    return {
        "role": "assistant",
        "content": "answer",
        "citations": [
            {
                "chunk_id": str(chunk.id),
                "episode_title": chunk.episode_title,
                "episode_source_url": chunk.episode_source_url,
                "start_timestamp": chunk.start_timestamp,
            }
        ],
    }


def _user_message(text):
    return {"role": "user", "content": text, "citations": None}


def test_recent_topic_messages_keeps_only_the_tail_within_the_turn_budget():
    messages = []
    for i in range(RECENT_TOPIC_TURNS + 2):
        messages.append(_user_message(f"question {i}"))
        messages.append({"role": "assistant", "content": f"answer {i}", "citations": None})

    recent = _recent_topic_messages(messages)

    user_turns_kept = [m for m in recent if m["role"] == "user"]
    assert len(user_turns_kept) == RECENT_TOPIC_TURNS
    assert user_turns_kept[-1]["content"] == f"question {RECENT_TOPIC_TURNS + 1}"


def test_recent_topic_messages_returns_everything_when_under_budget():
    messages = [_user_message("only question"), {"role": "assistant", "content": "a", "citations": None}]

    assert _recent_topic_messages(messages) == messages


def test_gather_grounding_excludes_citations_outside_the_recent_topic_window(db_session):
    """Regression test for the real bug found in Phase 8: a long session that
    drifted across many unrelated guests produced an essay that attributed
    real quotes to the wrong guest, because grounding accumulated citations
    from the entire session instead of just the current topic. An old,
    unrelated guest's chunk must NOT show up in grounding for a fresh essay
    request several topics later."""
    old_chunk = _insert_chunk(db_session, "Old Unrelated Guest Episode")
    recent_chunk = _insert_chunk(db_session, "Recent On-Topic Guest Episode")

    messages = [
        _user_message("question about an old, unrelated topic"),
        _citation_message(old_chunk),
    ]
    for i in range(RECENT_TOPIC_TURNS):
        messages.append(_user_message(f"unrelated filler question {i}"))
        messages.append({"role": "assistant", "content": "filler answer", "citations": None})
    messages.append(_user_message("question about the current topic"))
    messages.append(_citation_message(recent_chunk))
    messages.append(_user_message("write an essay about that"))

    chunks = _gather_grounding(db_session, messages)

    episode_titles = {c.episode_title for c in chunks}
    assert "Recent On-Topic Guest Episode" in episode_titles
    assert "Old Unrelated Guest Episode" not in episode_titles


def test_gather_grounding_caps_episode_diversity_on_a_broad_single_turn_request(db_session, mocker):
    """Regression test for the actual real bug found in Phase 8: a single,
    broad essay request with NO prior grounded turns (so _gather_grounding
    falls into the fresh-retrieval fallback) legitimately cleared the
    relevance threshold against 10 different episodes at once, and the
    essay model cross-attributed real quotes to the wrong guest among them.
    RECENT_TOPIC_TURNS doesn't catch this — there's no session history to
    bound — so this needs the separate MAX_ESSAY_EPISODES cap."""
    unit_vector = [0.0] * 768
    unit_vector[0] = 1.0
    for i in range(MAX_ESSAY_EPISODES + 3):
        _insert_chunk(db_session, f"Episode {i}", embedding=unit_vector)
    mocker.patch("app.agent.retrieval.embed_text", return_value=unit_vector)

    messages = [_user_message("a broad question spanning many guests")]
    chunks = _gather_grounding(db_session, messages)

    distinct_episodes = {c.episode_title for c in chunks}
    assert len(distinct_episodes) == MAX_ESSAY_EPISODES


def test_gather_grounding_still_includes_citations_within_the_recent_window(db_session):
    chunk_a = _insert_chunk(db_session, "Guest A Episode")
    chunk_b = _insert_chunk(db_session, "Guest B Episode")

    messages = [
        _user_message("question about guest A's topic"),
        _citation_message(chunk_a),
        _user_message("follow-up on the same topic"),
        _citation_message(chunk_b),
        _user_message("write an essay about this"),
    ]

    chunks = _gather_grounding(db_session, messages)

    episode_titles = {c.episode_title for c in chunks}
    assert episode_titles == {"Guest A Episode", "Guest B Episode"}
