from app.agent.providers.ollama_provider import _looks_like_essay_request, _recover_malformed_tool_call
from app.agent.tools import resolve_search_text


def test_resolve_search_text_first_turn_uses_raw_message():
    """Phase 4 finding: trusting the LLM's own tool-call query for a
    first-turn question succeeded only ~1-in-3 times (see
    agent-transcripts/README.md). The raw user message is used instead."""
    messages = [{"role": "user", "content": "What have guests said about referral programs?"}]
    assert resolve_search_text(messages) == "What have guests said about referral programs?"


def test_resolve_search_text_follow_up_concatenates_not_llm_query():
    """Phase 5 finding: trusting the LLM's follow-up reformulation succeeded
    only 3/5 times; concatenating the previous and current question reached
    5/5. The LLM's tool-call query argument is never used for either case."""
    messages = [
        {"role": "user", "content": "What have guests said about referral programs?"},
        {"role": "assistant", "content": "Sean Ellis discussed this..."},
        {"role": "user", "content": "How do they prevent gaming?"},
    ]
    result = resolve_search_text(messages)
    assert "What have guests said about referral programs?" in result
    assert "How do they prevent gaming?" in result


def test_resolve_search_text_empty_messages_returns_empty_string():
    assert resolve_search_text([]) == ""


def test_essay_request_pattern_matches_writing_requests():
    assert _looks_like_essay_request("Can you turn this into an essay for me?")
    assert _looks_like_essay_request("Write this up as a blog post")
    assert _looks_like_essay_request("Turn our conversation into something I can publish")


def test_essay_request_pattern_does_not_match_questions():
    """The deterministic pre-check must not misfire on ordinary questions —
    a false positive here would route a real question into essay
    generation instead of grounded_qa."""
    assert not _looks_like_essay_request("What have guests said about referral programs?")
    assert not _looks_like_essay_request("How do they prevent incentive gaming?")


def test_recover_malformed_tool_call_extracts_known_tool_name():
    """Phase 5 finding: llama3.2:3b occasionally emits a broken tool-call
    attempt as plain text instead of a real tool_calls entry (measured
    ~1-in-5 for ship30_essay specifically)."""
    broken = '{"name":"ship30_essay","parameters":{"}$'
    recovered = _recover_malformed_tool_call(broken)
    assert recovered is not None
    assert recovered["function"]["name"] == "ship30_essay"


def test_recover_malformed_tool_call_returns_none_for_unrelated_text():
    assert _recover_malformed_tool_call("The available transcripts don't cover this topic.") is None
    assert _recover_malformed_tool_call("") is None
