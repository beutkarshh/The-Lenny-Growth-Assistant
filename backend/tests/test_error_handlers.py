import anthropic
from sqlalchemy.exc import OperationalError

from app.agent.providers.ollama_provider import OllamaChatError
from app.ingestion.embeddings import EmbeddingError


def _session(client):
    return client.post("/sessions", json={"llm_provider": "ollama"}).json()


def test_embedding_error_returns_structured_503(client, mocker):
    """The Phase 7 flagship case (architecture.md §8): retrieval's embedding
    call failing must be distinct from a chat-provider failure, not a raw
    500 or a silent empty-retrieval fallback."""
    mocker.patch(
        "app.api.routes.sessions.run_agent",
        side_effect=EmbeddingError("Ollama embedding call failed (host=http://test:11434): connection refused"),
    )
    session = _session(client)

    response = client.post(f"/sessions/{session['id']}/messages", json={"content": "hi"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "OLLAMA_EMBEDDING_UNREACHABLE"


def test_ollama_chat_error_returns_structured_503(client, mocker):
    mocker.patch(
        "app.api.routes.sessions.run_agent",
        side_effect=OllamaChatError("Ollama chat call failed (host=http://test:11434): connection refused"),
    )
    session = _session(client)

    response = client.post(f"/sessions/{session['id']}/messages", json={"content": "hi"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "OLLAMA_CHAT_UNREACHABLE"


def test_database_operational_error_returns_structured_503_not_raw_details(client, mocker):
    """Generic message, not str(exc) — a raw OperationalError can include
    connection details (host, DSN fragments) that shouldn't reach clients."""
    mocker.patch(
        "app.api.routes.sessions.run_agent",
        side_effect=OperationalError("connection to server failed", None, None),
    )
    session = _session(client)

    response = client.post(f"/sessions/{session['id']}/messages", json={"content": "hi"})

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "DATABASE_UNAVAILABLE"
    assert "connection to server failed" not in body["message"]


def test_anthropic_api_error_returns_structured_503(client, mocker):
    """Verified against real live failures during Phase 7 (an invalid key,
    then an actual insufficient-credit-balance account) — this test just
    pins that behavior so it can't silently regress."""
    fake_response = mocker.Mock()
    fake_response.request = mocker.Mock()
    error = anthropic.AuthenticationError(
        "Error code: 401 - API key is invalid.", response=fake_response, body=None
    )
    mocker.patch("app.api.routes.sessions.run_agent", side_effect=error)
    session = _session(client)

    response = client.post(f"/sessions/{session['id']}/messages", json={"content": "hi"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "CLAUDE_PROVIDER_ERROR"


def test_unexpected_exception_returns_generic_500_not_raw_traceback(client, mocker):
    mocker.patch("app.api.routes.sessions.run_agent", side_effect=RuntimeError("boom"))
    session = _session(client)

    response = client.post(f"/sessions/{session['id']}/messages", json={"content": "hi"})

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "INTERNAL_ERROR"
    assert "boom" not in body["message"]
