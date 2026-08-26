import httpx

from app.core.config import get_settings

settings = get_settings()

EMBEDDING_MODEL = "nomic-embed-text"


class EmbeddingError(Exception):
    """Raised when the local Ollama embedding call fails. Reused at the
    retrieval-call boundary in later phases — see architecture.md §8's
    "Ollama unreachable for embeddings" resilience case."""


def embed_text(text: str) -> list[float]:
    try:
        response = httpx.post(
            f"{settings.ollama_host}/api/embeddings",
            json={"model": EMBEDDING_MODEL, "prompt": text},
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EmbeddingError(
            f"Ollama embedding call failed (host={settings.ollama_host}): {exc}"
        ) from exc
    return response.json()["embedding"]
