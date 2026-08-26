from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    """Liveness check.

    Phase 1 scope: confirms the API process is up and responding — no
    dependency checks yet. Upgraded in Phase 3 to also report DB and LLM
    provider reachability per architecture.md §3.
    """
    return {"status": "ok"}
