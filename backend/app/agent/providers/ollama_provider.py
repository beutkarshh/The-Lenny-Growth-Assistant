import re

import httpx
from sqlalchemy.orm import Session as DBSession

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.providers.base import AgentResult
from app.agent.ship30_essay import NOT_ENOUGH_MATERIAL_MESSAGE, generate_essay
from app.agent.tools import grounded_qa_query, resolve_search_text
from app.core.config import get_settings

settings = get_settings()

# Verified live against Ollama 0.13.4 / llama3.2:3b: /api/chat accepts an
# OpenAI-style `tools` array and returns message.tool_calls with parsed
# (not string) arguments; a role:"tool" message with tool_call_id continues
# the loop and produces a normal text reply. No SDK for this — raw HTTP,
# matching how ingestion's embeddings.py already talks to Ollama.
#
# gemma3:4b and phi3:3.8b were also tested and both hard-error
# ("does not support tools") rather than just being less reliable — see
# architecture.md §6. OLLAMA_CHAT_MODEL must be a model that supports tools.
GROUNDED_QA_SCHEMA = {
    "type": "function",
    "function": {
        "name": "grounded_qa",
        "description": "Answer product/growth questions using Lenny's Podcast transcripts.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A self-contained question to search the transcript knowledge "
                        "base for. Incorporate relevant context from the conversation "
                        "so far — this tool has no memory of prior turns."
                    ),
                }
            },
            "required": ["query"],
        },
    },
}

SHIP30_ESSAY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ship30_essay",
        "description": "Turn the grounded conversation so far into a Ship 30 for 30-style essay.",
        "parameters": {"type": "object", "properties": {}},
    },
}

MAX_TOOL_ITERATIONS = 4

KNOWN_TOOL_NAMES = ("grounded_qa", "ship30_essay")


def _recover_malformed_tool_call(content: str) -> dict | None:
    """llama3.2:3b occasionally emits a broken tool-call attempt as plain text
    in `content` instead of a proper `tool_calls` entry, rather than an empty
    response — e.g. `{"name":"ship30_essay","parameters":{"}$"}`. Measured at
    ~1-in-5 for ship30_essay specifically, in a multi-turn context with two
    tools registered (see agent-transcripts/README.md). Safe to recover just
    the tool name and ignore any garbled arguments: grounded_qa's query
    argument is never trusted anyway (resolve_search_text derives it
    deterministically), and ship30_essay takes no arguments at all.
    """
    if not content or '"name"' not in content:
        return None
    match = re.search(r'"name"\s*:\s*"(' + "|".join(KNOWN_TOOL_NAMES) + r')"', content)
    if not match:
        return None
    return {"id": "recovered", "function": {"name": match.group(1), "arguments": {}}}


# Deliberate, evidenced exception to architecture.md §5's "intent-based
# routing, not keyword matching in application code" principle — for THIS
# provider only. Testing found llama3.2:3b's own tool-choice between
# grounded_qa/ship30_essay unreliable even with explicit few-shot routing
# examples in the system prompt (2/5 correct across repeated trials — see
# agent-transcripts/README.md). A deterministic pre-check here doesn't fix
# the model's tool-calling, it routes around needing it for this one
# decision. The Claude provider is left on pure intent-based tool routing —
# nothing observed suggests it has this problem.
ESSAY_REQUEST_PATTERN = re.compile(
    r"\b(essay|blog post|write.{0,15}up|turn.{0,20}into|make.{0,20}into|"
    r"publish|write.{0,10}(post|piece|article))\b",
    re.IGNORECASE,
)


def _looks_like_essay_request(text: str) -> bool:
    return bool(ESSAY_REQUEST_PATTERN.search(text))


class OllamaChatError(Exception):
    """Raised when the local Ollama chat call fails. Distinct from
    ingestion.embeddings.EmbeddingError per architecture.md §8 — chat-Ollama-down
    and embedding-Ollama-down are different failure modes needing different
    error_codes once Phase 7 registers handlers for both."""


def generate_text(system: str, user: str) -> str:
    """Plain (non-tool-calling) completion — used by ship30_essay's dedicated
    generation call, per architecture.md §5's Phase 5 design.

    Uses ollama_essay_model (gemma3:4b), not ollama_chat_model (llama3.2:3b).
    num_ctx/num_predict were raised as a first hypothesis for llama3.2:3b's
    short essays (~450-600 words vs ~1,250 target), but instrumenting a real
    call showed prompt_eval_count at only ~1,200 tokens against this 16,384
    window (no truncation) and done_reason "stop" with most of the
    num_predict budget unused — llama3.2:3b was choosing to stop short, not
    being cut off. Switching the essay-generation model to gemma3:4b (not
    tool-calling-capable, but this call doesn't need tool calling) resolved
    it directly: ~1,000-1,150 words at roughly half phi3:3.8b's latency in
    testing. Full comparison in agent-transcripts/README.md.
    """
    try:
        response = httpx.post(
            f"{settings.ollama_host}/api/chat",
            json={
                "model": settings.ollama_essay_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "options": {"num_ctx": 16384, "num_predict": 2500},
                "stream": False,
            },
            timeout=180.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OllamaChatError(
            f"Ollama chat call failed (host={settings.ollama_host}): {exc}"
        ) from exc
    return response.json()["message"].get("content", "")


def run(db: DBSession, messages: list[dict]) -> AgentResult:
    latest_user_message = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    if _looks_like_essay_request(latest_user_message):
        essay_markdown, citations = generate_essay(db, messages, generate_text)
        if essay_markdown is None:
            return AgentResult(content=NOT_ENOUGH_MATERIAL_MESSAGE, citations=[])
        return AgentResult(
            content=(
                "I've put together an essay on this — you'll find it in the panel "
                "alongside our conversation."
            ),
            citations=citations,
            artifact_content=essay_markdown,
            artifact_type="markdown",
        )

    captured_citations: list[dict] = []
    captured_artifact: dict = {"content": None}
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
    chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}, *llm_messages]

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            response = httpx.post(
                f"{settings.ollama_host}/api/chat",
                json={
                    "model": settings.ollama_chat_model,
                    "messages": chat_messages,
                    "tools": [GROUNDED_QA_SCHEMA, SHIP30_ESSAY_SCHEMA],
                    "stream": False,
                },
                timeout=180.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaChatError(
                f"Ollama chat call failed (host={settings.ollama_host}): {exc}"
            ) from exc

        message = response.json()["message"]
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            recovered = _recover_malformed_tool_call(message.get("content", ""))
            if recovered is not None:
                tool_calls = [recovered]
            else:
                return AgentResult(
                    content=message.get("content", ""),
                    citations=captured_citations,
                    artifact_content=captured_artifact["content"],
                    artifact_type="markdown" if captured_artifact["content"] else None,
                )

        chat_messages.append(message)
        for call in tool_calls:
            name = call["function"]["name"]
            if name == "grounded_qa":
                search_text = resolve_search_text(messages)
                result_text = grounded_qa_query(db, search_text, captured_citations)
            elif name == "ship30_essay":
                essay_markdown, citations = generate_essay(db, messages, generate_text)
                if essay_markdown is None:
                    result_text = NOT_ENOUGH_MATERIAL_MESSAGE
                else:
                    captured_artifact["content"] = essay_markdown
                    captured_citations.extend(citations)
                    result_text = (
                        "The essay has been created and will be shown to the user in "
                        "the artifact panel."
                    )
            else:
                result_text = f"Unknown tool: {name}"
            chat_messages.append(
                {"role": "tool", "content": result_text, "tool_call_id": call.get("id", "")}
            )

    return AgentResult(
        content="I wasn't able to finish answering within the allotted tool-call budget.",
        citations=captured_citations,
    )
