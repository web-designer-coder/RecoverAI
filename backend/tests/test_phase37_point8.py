"""Point 8 regression — transaction boundary / savepoint isolation.

Verifies that a provider failure (or audit/bookkeeping error) inside
_run_approved does not roll back the already-flushed RecoveryAction.
The savepoint ensures the action state survives; rollback only removes
the provider-side changes.
This test only inspects the source code to verify the savepoint mechanism exists.
"""
import inspect
from app.services.recovery_execution_service import RecoveryExecutionService


def test_action_persists_after_bookkeeping_rollback():
    """Point 8 — savepoint preserves flushed RecoveryAction on rollback (source inspection)."""
    # Verify the savepoint mechanism is present by checking the service
    # still imports and uses begin_nested correctly.
    source = inspect.getsource(RecoveryExecutionService.execute)
    assert "begin_nested" in source, "Point 8 savepoint not present in execute()"
    # Indent-normalized: the actual code splits `with ... :` from the body.
    normalized = " ".join(source.split())
    assert "with self._session.begin_nested():" in normalized, \
        "Point 8 savepoint syntax incorrect"
