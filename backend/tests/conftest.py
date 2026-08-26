import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

settings = get_settings()

# A dedicated test database — never the real one. Tests truncate tables
# between runs, and the real transcript_chunks table took real ingestion
# work to build (53 episodes, ~1000 chunks); tests must never be able to
# touch it, even by accident.
TEST_DB_NAME = f"{settings.postgres_db}_test"
TEST_DATABASE_URL = (
    f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/{TEST_DB_NAME}"
)


@pytest.fixture(scope="session", autouse=True)
def _create_test_database():
    """Connects to the default database to CREATE the test database if it
    doesn't exist yet, then creates the vector extension and all tables in
    it. Session-scoped: runs once per test run, not once per test."""
    admin_engine = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()

    test_engine = create_engine(TEST_DATABASE_URL)
    with test_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture()
def db_session():
    """One fresh, truncated database per test — cheap enough at this table
    count/size not to need transactional rollback tricks."""
    engine = create_engine(TEST_DATABASE_URL)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """TestClient wired to the test database via FastAPI's dependency
    override — the app under test never sees the real database_url.

    Deliberately NOT used as a context manager: that would trigger the
    real app lifespan, which runs init_db() against the *dev* database
    (wrong DB for tests) and could fail-fast (sys.exit) on a misconfigured
    LLM_PROVIDER — neither should be able to affect whether tests run.

    raise_server_exceptions=False: Starlette's TestClient re-raises any
    exception that reaches the outermost generic Exception handler by
    default (for debug visibility mid-test-run). Manual testing in Phase 7
    already confirmed the real running server returns structured
    {"error_code": "INTERNAL_ERROR", ...} JSON for unhandled exceptions —
    this flag just lets the test observe that same HTTP-level behavior
    instead of the exception propagating into the test process itself.
    """
    app.dependency_overrides[get_db] = lambda: db_session
    test_client = TestClient(app, raise_server_exceptions=False)
    yield test_client
    app.dependency_overrides.clear()
