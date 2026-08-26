import httpx
from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.db.session import SessionLocal

router = APIRouter()
settings = get_settings()


def _check_database() -> str:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return "ok"
    except OperationalError:
        return "unreachable"


def _check_llm_provider() -> str:
    if settings.llm_provider == "ollama":
        try:
            response = httpx.get(f"{settings.ollama_host}/api/version", timeout=3.0)
            return "ok" if response.status_code == 200 else "unreachable"
        except httpx.HTTPError:
            return "unreachable"
    # Claude: key presence is already enforced at startup fail-fast
    # (main.py). Not making a live, billed API call just to answer a health
    # check — "configured" reflects that, distinct from a verified "ok".
    return "configured"


@router.get("/health")
def health_check(response: Response) -> dict:
    """Liveness + dependency check, per architecture.md §3.

    DB is the one dependency that fails the whole app if it's down (nothing
    works without it), so that alone drives the 503. LLM provider status is
    reported but doesn't flip overall status to unhealthy — e.g. Ollama
    being down for chat still leaves existing sessions readable.
    """
    database_status = _check_database()
    llm_provider_status = _check_llm_provider()

    overall = "ok" if database_status == "ok" else "degraded"
    if overall != "ok":
        response.status_code = 503

    return {
        "status": overall,
        "database": database_status,
        "llm_provider": settings.llm_provider,
        "llm_provider_status": llm_provider_status,
    }
