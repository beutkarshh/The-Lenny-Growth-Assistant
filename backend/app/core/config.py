from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, read from environment variables / .env.

    Grows one phase at a time — only settings something actually reads
    are defined here.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "The Lenny Growth Assistant"
    environment: str = "development"

    postgres_user: str = "lenny"
    postgres_password: str = "change_me"
    postgres_db: str = "lenny_growth_assistant"
    postgres_host: str = "db"
    postgres_port: int = 5432

    ollama_host: str = "http://host.docker.internal:11434"

    # Governs chat/generation only — embeddings always go through Ollama
    # regardless of this setting. See architecture.md §6.
    llm_provider: Literal["claude", "ollama"] = "ollama"
    anthropic_api_key: str | None = None
    ollama_chat_model: str = "llama3.2:3b"
    # Deliberately a different model from ollama_chat_model — llama3.2:3b is
    # the only one of the tested small models that supports tool calling
    # (needed for grounded_qa routing), but it measurably under-shoots the
    # ~1,250-word essay target (~450-600 words). gemma3:4b doesn't support
    # tool calling at all, but ship30_essay is a plain generation call, not
    # a tool call, so that's not a constraint here — and it reaches
    # ~1,000-1,150 words at roughly half phi3:3.8b's latency. See
    # architecture.md §6 and agent-transcripts/README.md for the comparison.
    ollama_essay_model: str = "gemma3:4b"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
