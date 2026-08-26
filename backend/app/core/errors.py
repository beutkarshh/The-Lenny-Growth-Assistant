import anthropic
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.agent.providers.ollama_provider import OllamaChatError
from app.ingestion.embeddings import EmbeddingError


class AppError(Exception):
    """Raise this for any expected, named failure. Caught by the handler
    below and turned into architecture.md §3's {error_code, message} shape.
    """

    def __init__(self, status_code: int, error_code: str, message: str):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": exc.error_code, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "VALIDATION_ERROR", "message": details},
        )

    # Phase 7 (architecture.md §8): each of these was previously an unhandled
    # exception falling through to the generic 500 below. All are upstream
    # dependency failures, not client mistakes — 503, not 500 or 4xx.

    @app.exception_handler(EmbeddingError)
    async def embedding_error_handler(request: Request, exc: EmbeddingError) -> JSONResponse:
        # The flagship Phase 7 case: LLM_PROVIDER=claude, valid key, Ollama
        # down. Chat works fine; retrieval silently breaks underneath it
        # unless this is distinct from the chat-provider error below.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error_code": "OLLAMA_EMBEDDING_UNREACHABLE", "message": str(exc)},
        )

    @app.exception_handler(OllamaChatError)
    async def ollama_chat_error_handler(request: Request, exc: OllamaChatError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error_code": "OLLAMA_CHAT_UNREACHABLE", "message": str(exc)},
        )

    @app.exception_handler(OperationalError)
    async def database_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
        # Generic message, not str(exc) — SQLAlchemy/psycopg OperationalError
        # messages can include connection details (host, DSN fragments).
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_code": "DATABASE_UNAVAILABLE",
                "message": "The database is currently unreachable. Please try again shortly.",
            },
        )

    @app.exception_handler(anthropic.APIError)
    async def claude_provider_error_handler(request: Request, exc: anthropic.APIError) -> JSONResponse:
        # Base class for every Anthropic SDK error (confirmed via the actual
        # class hierarchy, not assumed) — auth failures, insufficient credit
        # balance, rate limits, connection errors all land here. str(exc) is
        # already an SDK-crafted, safe, informative message (e.g. "Error
        # code: 401 - ... 'API key is invalid.'"), not a raw traceback.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error_code": "CLAUDE_PROVIDER_ERROR", "message": str(exc)},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Safety net for genuinely unexpected bugs — architecture.md §3 requires
        # structured errors, never a raw stack trace reaching the client.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error_code": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
        )
