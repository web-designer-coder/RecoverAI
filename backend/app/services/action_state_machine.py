"""Recovery action state machine — explicit, validated transitions.

    PENDING ──► VERIFYING_POLICY ──► APPROVED ──► PROCESSING ──► SUCCEEDED
       │              │                  │             │
       │              │                  │             └──► FAILED
       ├─► SCHEDULED ─┘                  ├─► BLOCKED / CANCELLED
       └─► BLOCKED / ESCALATED / CANCELLED
                                         ├──► ESCALATED
                                         └──► CUSTOMER_ACTION_REQUIRED

From APPROVED, an ESCALATE/STOP recommendation terminates without a provider
call, and a customer-facing action ends in CUSTOMER_ACTION_REQUIRED (the
customer must complete it themselves). PROCESSING can end the same way when
the provider reports it.

Terminal states: SUCCEEDED, FAILED, CANCELLED, BLOCKED, ESCALATED,
CUSTOMER_ACTION_REQUIRED. Anything not listed is invalid and raises
InvalidTransitionError — arbitrary jumps are refused, never guessed.
"""

from datetime import datetime, timezone

from app.models import RecoveryAction
from app.models.enums import RecoveryActionStatus as S


class InvalidTransitionError(Exception):
    def __init__(self, current: S, target: S) -> None:
        super().__init__(f"Invalid recovery-action transition {current.value} → {target.value}")
        self.current = current
        self.target = target


ALLOWED_TRANSITIONS: dict[S, frozenset[S]] = {
    S.PENDING: frozenset({
        S.VERIFYING_POLICY, S.APPROVED, S.SCHEDULED,
        S.BLOCKED, S.ESCALATED, S.CANCELLED,
    }),
    S.VERIFYING_POLICY: frozenset({S.APPROVED, S.BLOCKED, S.ESCALATED}),
    S.APPROVED: frozenset({
        S.PROCESSING, S.SCHEDULED, S.BLOCKED, S.CANCELLED,
        S.ESCALATED, S.CUSTOMER_ACTION_REQUIRED,
    }),
    S.SCHEDULED: frozenset({S.PROCESSING, S.CANCELLED}),
    S.PROCESSING: frozenset({S.SUCCEEDED, S.FAILED, S.CUSTOMER_ACTION_REQUIRED}),
    # Terminal states.
    S.SUCCEEDED: frozenset(),
    S.FAILED: frozenset(),
    S.CANCELLED: frozenset(),
    S.BLOCKED: frozenset(),
    S.ESCALATED: frozenset(),
    S.CUSTOMER_ACTION_REQUIRED: frozenset(),
}

_TERMINAL_OUTCOMES = {
    S.SUCCEEDED, S.FAILED, S.CANCELLED, S.BLOCKED, S.ESCALATED,
    S.CUSTOMER_ACTION_REQUIRED,
}


def validate_transition(current: S, target: S) -> None:
    """Raise InvalidTransitionError if the move is not allowed."""
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransitionError(current, target)


def apply_transition(action: RecoveryAction, target: S) -> RecoveryAction:
    """Validate then mutate the action's status and lifecycle timestamps."""
    validate_transition(action.status, target)
    action.status = target
    now = datetime.now(timezone.utc)
    if target is S.PROCESSING and action.started_at is None:
        action.started_at = now
    if target in _TERMINAL_OUTCOMES:
        action.completed_at = now
    return action
