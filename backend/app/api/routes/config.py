from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/config")
def get_config() -> dict:
    """Active LLM provider, for the UI header per design.md §2."""
    return {
        "llm_provider": settings.llm_provider,
        "available_providers": ["claude", "ollama"],
    }
