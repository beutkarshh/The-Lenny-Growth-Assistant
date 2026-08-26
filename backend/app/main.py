import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.config import router as config_router
from app.api.routes.health import router as health_router
from app.api.routes.sessions import router as sessions_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.db.session import init_db

settings = get_settings()
logger = logging.getLogger("app.startup")


def _check_provider_config() -> None:
    """Fail fast if LLM_PROVIDER=claude but no key is present, per
    architecture.md §6 — not a runtime crash on first use."""
    if settings.llm_provider == "claude" and not settings.anthropic_api_key:
        logger.error(
            "LLM_PROVIDER=claude but ANTHROPIC_API_KEY is not set. "
            "Set it in .env or switch LLM_PROVIDER=ollama."
        )
        sys.exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_provider_config()
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Frontend runs in the browser on its own origin (localhost:5173) and calls
# this API on localhost:8000 — a cross-origin request, unlike every prior
# test in this project so far (curl/PowerShell aren't subject to CORS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(config_router)
app.include_router(artifacts_router)
