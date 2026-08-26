import anthropic
from anthropic import beta_tool
from sqlalchemy.orm import Session as DBSession

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.providers.base import AgentResult
from app.agent.ship30_essay import NOT_ENOUGH_MATERIAL_MESSAGE, generate_essay
from app.agent.tools import grounded_qa_query, resolve_search_text
from app.core.config import get_settings

settings = get_settings()

# claude-sonnet-5, not the more capable (and ~2.5x pricier) claude-opus-5:
# grounded Q&A and essay formatting don't need frontier-tier reasoning, and
# this project runs on a small API budget (see the Phase 4 cost discussion
# in agent-transcripts/). Not exhaustively benchmarked against Opus for this
# specific workload — revisit if answer quality turns out to be the binding
# constraint rather than cost.
MODEL = "claude-sonnet-5"


def generate_text(system: str, user: str) -> str:
    """Plain (non-tool-calling) completion — used by ship30_essay's dedicated
    generation call, per architecture.md §5's Phase 5 design (a nested call
    with its own Ship-30-specific system prompt, not the outer agent turn)."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return next((b.text for b in response.content if b.type == "text"), "")


def run(db: DBSession, messages: list[dict]) -> AgentResult:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    captured_citations: list[dict] = []
    captured_artifact: dict = {"content": None}
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    @beta_tool
    def grounded_qa(query: str) -> str:
        """Answer product/growth questions using Lenny's Podcast transcripts.

        Args:
            query: A self-contained question to search the transcript
                knowledge base for. Incorporate relevant context from the
                conversation so far — this tool has no memory of prior turns.
        """
        search_text = resolve_search_text(messages)
        return grounded_qa_query(db, search_text, captured_citations)

    @beta_tool
    def ship30_essay() -> str:
        """Turn the grounded conversation so far into a Ship 30 for 30-style essay."""
        essay_markdown, citations = generate_essay(db, messages, generate_text)
        if essay_markdown is None:
            return NOT_ENOUGH_MATERIAL_MESSAGE
        captured_artifact["content"] = essay_markdown
        captured_citations.extend(citations)
        return "The essay has been created and will be shown to the user in the artifact panel."

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[grounded_qa, ship30_essay],
        messages=llm_messages,
    )

    last_message = None
    for message in runner:
        last_message = message

    final_text = ""
    if last_message is not None:
        final_text = next((b.text for b in last_message.content if b.type == "text"), "")

    return AgentResult(
        content=final_text,
        citations=captured_citations,
        artifact_content=captured_artifact["content"],
        artifact_type="markdown" if captured_artifact["content"] else None,
    )
