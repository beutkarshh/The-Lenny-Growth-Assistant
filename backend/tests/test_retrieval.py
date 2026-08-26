import uuid

from app.agent.retrieval import MAX_DISTANCE, retrieve
from app.db.models import EMBEDDING_DIM, TranscriptChunk


def _unit_vector(index: int) -> list[float]:
    """A 768-dim one-hot vector — orthogonal to every other _unit_vector(j)
    for j != index, giving a predictable cosine distance for test purposes
    without needing a real embedding model."""
    vec = [0.0] * EMBEDDING_DIM
    vec[index] = 1.0
    return vec


def _insert_chunk(db_session, embedding, episode_title="Test Episode"):
    chunk = TranscriptChunk(
        id=uuid.uuid4(),
        episode_title=episode_title,
        episode_source_url="https://youtube.com/watch?v=test",
        chunk_text="Some transcript text.",
        chunk_index=0,
        start_timestamp="00:00:00",
        embedding=embedding,
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def test_retrieve_returns_close_match_within_threshold(db_session, mocker):
    _insert_chunk(db_session, _unit_vector(0), episode_title="Matching Episode")
    mocker.patch("app.agent.retrieval.embed_text", return_value=_unit_vector(0))

    results = retrieve(db_session, "irrelevant text, embedding is mocked")

    assert len(results) == 1
    assert results[0].episode_title == "Matching Episode"
    assert results[0].distance < MAX_DISTANCE


def test_retrieve_excludes_orthogonal_chunk_beyond_threshold(db_session, mocker):
    """Cosine distance between orthogonal unit vectors is 1.0 — well above
    MAX_DISTANCE (0.35). This is the mechanism behind the "not covered"
    fallback (architecture.md §4 step 3): empty results are a normal path,
    not an error."""
    _insert_chunk(db_session, _unit_vector(1), episode_title="Unrelated Episode")
    mocker.patch("app.agent.retrieval.embed_text", return_value=_unit_vector(0))

    results = retrieve(db_session, "irrelevant text, embedding is mocked")

    assert results == []


def test_retrieve_orders_by_distance_closest_first(db_session, mocker):
    _insert_chunk(db_session, _unit_vector(0), episode_title="Exact Match")
    # A vector close to, but not exactly, the query — should still clear
    # MAX_DISTANCE but rank behind the exact match.
    near_match = _unit_vector(0)
    near_match[1] = 0.3
    _insert_chunk(db_session, near_match, episode_title="Near Match")
    mocker.patch("app.agent.retrieval.embed_text", return_value=_unit_vector(0))

    results = retrieve(db_session, "irrelevant text, embedding is mocked")

    assert len(results) == 2
    assert results[0].episode_title == "Exact Match"
    assert results[1].episode_title == "Near Match"
    assert results[0].distance < results[1].distance


def test_retrieve_respects_top_k(db_session, mocker):
    for i in range(5):
        vec = _unit_vector(0)
        vec[i + 1] = 0.05 * (i + 1)  # all still well within MAX_DISTANCE
        _insert_chunk(db_session, vec, episode_title=f"Episode {i}")
    mocker.patch("app.agent.retrieval.embed_text", return_value=_unit_vector(0))

    results = retrieve(db_session, "irrelevant text, embedding is mocked", top_k=3)

    assert len(results) == 3
