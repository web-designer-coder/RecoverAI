"""Minimal scheduler mechanism for recovery execution.

Uses a thread-safe background thread with scheduled polling intervals.
Compatible with the existing single-process architecture.
No Celery/APScheduler dependency is required.

Documented for production: start with `python -m app.scheduler` or call
`start_scheduler()` during application startup.
"""
import threading
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import get_session_factory, get_engine
from app.services.recovery_execution_service import RecoveryExecutionService
from app.repositories.recovery_repository import RecoveryRepository
from app.models import Merchant

logger = __import__("logging").getLogger("recoverai.scheduler")

# Polling interval in seconds (production: 60-300; dev/test: 30 for faster feedback)
POLL_INTERVAL = 60


class RecoveryScheduler:
    """Polls due SCHEDULED actions and executes them safely."""

    def __init__(self, session_factory=None, interval=POLL_INTERVAL):
        # session_factory: must be a callable that returns a SQLAlchemy Session.
        # Accepts either get_session_factory (function returning sessionmaker)
        # or a sessionmaker, or a lambda/functools.partial returning a session.
        if session_factory is not None:
            # Detect whether it returns a sessionmaker (needs one more call)
            # or a session (used directly).
            result = session_factory()
            if hasattr(result, "close") and callable(result.close):
                # It's already a session — keep the factory as-is
                self.session_factory = session_factory
            else:
                # It's a sessionmaker — wrap so one extra call gives a session
                maker = result
                self.session_factory = lambda: maker()
        else:
            self.session_factory = lambda: get_session_factory()()
        self.interval = interval
        self._thread = None
        self._running = False
        self._lock = threading.Lock()

    def _poll_cycle(self):
        try:
            session: Session = self.session_factory()
            try:
                now = datetime.now(timezone.utc)
                # Merchant-scoped: get all merchants to process
                from sqlalchemy import select
                from app.models import Merchant

                merchants = session.scalars(select(Merchant)).all()
                for merchant in merchants:
                    repo = RecoveryRepository(session)
                    due = repo.due_scheduled_actions(merchant.id, now)
                    for action in due:
                        # Idempotency / concurrency guard: only process if still SCHEDULED
                        refreshed = session.query(type(action)).filter(
                            type(action).id == action.id,
                            type(action).status == action.status,
                        ).first()
                        if refreshed is None:
                            continue  # already processed by another thread/request
                        try:
                            service = RecoveryExecutionService(
                                session,
                                provider=None,
                            )
                            service.execute(
                                merchant_id=str(merchant.id),
                                external_payment_id=action.payment.external_payment_id,
                                idempotency_key=action.idempotency_key,
                                now=now,
                            )
                        except Exception as exc:
                            logger.error(
                                "scheduled execution failed payment=%s key=%s: %s",
                                action.payment.external_payment_id,
                                action.idempotency_key,
                                exc,
                            )
                session.commit()
            finally:
                session.close()
        except Exception as exc:
            logger.error("scheduler poll cycle error: %s", exc)

    def _run(self):
        while self._running:
            try:
                self._poll_cycle()
            except Exception as exc:
                logger.error("scheduler poll exception: %s", exc)
            time.sleep(self.interval)

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            logger.info("scheduler started (interval=%ds)", self.interval)

    def stop(self):
        with self._lock:
            self._running = False
            if self._thread:
                self._thread.join(timeout=self.interval + 5)
                self._thread = None
            logger.info("scheduler stopped")


def start_scheduler():
    """Convenience entry point for application startup."""
    scheduler = RecoveryScheduler()
    scheduler.start()
    return scheduler


def run_once():
    """Run a single poll cycle — useful for manual/admin/CLI invocation."""
    scheduler = RecoveryScheduler()
    scheduler._poll_cycle()
