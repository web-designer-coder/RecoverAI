"""Test fixtures.

The suite runs against a dedicated ``recoverai_test`` database so it can
never destroy development data. The URL is forced before any app module is
imported, the schema is created with Alembic (same migrations as production),
and the demo seed is applied once per session. Each test runs inside a
transaction that is rolled back afterwards — no test leaks rows.
"""

import os
from collections.abc import Iterator

# Must happen before app.config is imported anywhere.
TEST_DATABASE_URL = os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:recoverai_dev@localhost:5432/recoverai_test",
)
# Test-only webhook secret (matches tests/rzp_fixtures.WEBHOOK_SECRET).
# No live credentials are ever used by this suite.
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_local_only")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import Base, dispose_engine, get_engine, get_session_factory
from app.dependencies import get_db
from app.limiter import limiter
from app.main import create_app
from app.seed import MERCHANT_NAME, seed_database


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """Reset the in-memory rate limiter before and after every test.

    Without this, rate-limit counters accumulate across tests because
    ``limiter`` is a module-level singleton shared by all test clients.
    """
    limiter.clear()
    yield
    limiter.clear()


def _run_migrations() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg = Config(os.path.join(root, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    """Fresh schema + one seeded demo dataset for the whole test session."""
    from app.config import get_settings

    get_settings.cache_clear()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    # Drop leftover Alembic state so migrations run from a truly clean slate.
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        conn.commit()
    _run_migrations()

    factory = get_session_factory()
    session = factory()
    try:
        seed_database(session)

        # Configure the seeded merchant with the test webhook secret so that
        # Phase 3 webhook tests can verify signatures against it.  This mirrors
        # what a real merchant does via POST /merchants/me/razorpay/webhook-secret.
        from app.models import Merchant
        from app.utils.encryption import encrypt_value

        webhook_secret = os.environ["RAZORPAY_WEBHOOK_SECRET"]
        merchant = session.scalars(
            select(Merchant).where(Merchant.name == MERCHANT_NAME)
        ).one()
        merchant.razorpay_webhook_secret_encrypted = encrypt_value(webhook_secret)
        merchant.razorpay_webhook_configured = True

        session.commit()
    finally:
        session.close()
    yield
    dispose_engine()


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """Transaction-scoped session: every test is rolled back on exit."""
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    """API client wired to the transaction-scoped test session."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def merchant_id(db_session: Session) -> str:
    from sqlalchemy import select

    from app.models import Merchant

    return str(
        db_session.scalars(
            select(Merchant).where(Merchant.name == MERCHANT_NAME)
        ).one().id
    )
