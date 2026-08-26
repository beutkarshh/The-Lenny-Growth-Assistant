from app.agent.providers.base import AgentResult


def test_health_returns_ok_with_healthy_dependencies(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_create_session_persists_and_returns_it(client):
    response = client.post("/sessions", json={"llm_provider": "ollama"})
    assert response.status_code == 201
    body = response.json()
    assert body["llm_provider"] == "ollama"
    assert "id" in body


def test_get_nonexistent_session_returns_structured_404(client):
    response = client.get("/sessions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "SESSION_NOT_FOUND"
    assert "message" in body


def test_create_session_rejects_invalid_provider(client):
    """architecture.md §3: structured errors, not raw Pydantic tracebacks."""
    response = client.post("/sessions", json={"llm_provider": "not-a-real-provider"})
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "VALIDATION_ERROR"


def test_list_sessions_returns_newest_first_with_preview(client):
    first = client.post("/sessions", json={"llm_provider": "ollama"}).json()
    second = client.post("/sessions", json={"llm_provider": "ollama"}).json()

    response = client.get("/sessions")
    assert response.status_code == 200
    ids_in_order = [s["id"] for s in response.json()]
    assert ids_in_order.index(second["id"]) < ids_in_order.index(first["id"])


def test_send_message_persists_both_turns_and_returns_assistant_reply(client, mocker):
    """Mocks the agent layer — this tests routing/persistence/API contract,
    not model quality (that's covered by the real, repeatedly-measured
    trials in agent-transcripts/README.md)."""
    mocker.patch(
        "app.api.routes.sessions.run_agent",
        return_value=AgentResult(
            content="Sean Ellis discussed referral programs.",
            citations=[
                {
                    "episode_title": "Test Episode",
                    "episode_source_url": "https://youtube.com/watch?v=abc",
                    "start_timestamp": "00:01:00",
                    "chunk_id": "11111111-1111-1111-1111-111111111111",
                }
            ],
        ),
    )
    session = client.post("/sessions", json={"llm_provider": "ollama"}).json()

    response = client.post(f"/sessions/{session['id']}/messages", json={"content": "What have guests said?"})
    assert response.status_code == 201
    assistant_message = response.json()
    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"] == "Sean Ellis discussed referral programs."
    assert len(assistant_message["citations"]) == 1

    detail = client.get(f"/sessions/{session['id']}").json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][0]["content"] == "What have guests said?"
    assert detail["messages"][1]["role"] == "assistant"


def test_send_message_creates_artifact_and_links_it(client, mocker):
    """Phase 5: ship30_essay's artifact must be persisted and the triggering
    message must carry artifact_id, so the frontend knows to open the
    viewer panel (design.md §2)."""
    mocker.patch(
        "app.api.routes.sessions.run_agent",
        return_value=AgentResult(
            content="I've put together an essay on this.",
            citations=[],
            artifact_content="# A Test Essay\n\nBody text.",
            artifact_type="markdown",
        ),
    )
    session = client.post("/sessions", json={"llm_provider": "ollama"}).json()

    response = client.post(f"/sessions/{session['id']}/messages", json={"content": "Turn this into an essay"})
    assistant_message = response.json()
    assert assistant_message["artifact_id"] is not None

    artifact = client.get(f"/artifacts/{assistant_message['artifact_id']}").json()
    assert artifact["type"] == "markdown"
    assert artifact["content"] == "# A Test Essay\n\nBody text."


def test_send_message_to_nonexistent_session_returns_404_not_500(client):
    response = client.post(
        "/sessions/00000000-0000-0000-0000-000000000000/messages", json={"content": "hi"}
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "SESSION_NOT_FOUND"


def test_send_empty_message_is_rejected_by_validation(client):
    session = client.post("/sessions", json={"llm_provider": "ollama"}).json()
    response = client.post(f"/sessions/{session['id']}/messages", json={"content": ""})
    assert response.status_code == 422


def test_config_reports_active_provider(client):
    response = client.get("/config")
    assert response.status_code == 200
    body = response.json()
    assert body["llm_provider"] in ("claude", "ollama")
    assert set(body["available_providers"]) == {"claude", "ollama"}
