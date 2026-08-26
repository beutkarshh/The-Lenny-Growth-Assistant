from typing import Callable

from sqlalchemy.orm import Session as DBSession

from app.agent.providers import claude_provider, ollama_provider
from app.agent.providers.base import AgentResult
from app.core.config import get_settings

settings = get_settings()


def run_agent(db: DBSession, messages: list[dict]) -> AgentResult:
    if settings.llm_provider == "claude":
        return claude_provider.run(db, messages)
    return ollama_provider.run(db, messages)


def get_generate_text() -> Callable[[str, str], str]:
    """The active provider's plain completion function — used directly by
    POST /sessions/{id}/artifacts, which triggers ship30_essay without going
    through tool-call routing (the endpoint itself already signals intent)."""
    if settings.llm_provider == "claude":
        return claude_provider.generate_text
    return ollama_provider.generate_text
