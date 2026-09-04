"""Phase 5 policy-engine tests.

Pure evaluator/check tests run against transient model instances (no DB);
version-history tests run against the transaction-scoped test database.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import MerchantPolicy, Payment, PaymentFailure, RecoveryAction, RecoveryDecision
from app.models.enums import FailureCategory, PaymentStatus, RecommendedAction, RecoveryActionStatus
from app.policy import CheckStatus, evaluate
from app.policy.models import PolicyContext
from app.schemas.policy_schemas import PolicyUpsertRequest
from app.services.policy_service import PolicyService as PolicyStorageService

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


def make_policy(**overrides) -> MerchantPolicy:
    kw = dict(
        maximum_retries=3,
        recovery_window_days=14,
        minimum_ai_confidence=Decimal("70.00"),
        high_value_threshold=Decimal("50000.00"),
        prevent_duplicate_recovery=True,
        require_policy_approval=False,   # tests opt in explicitly
        maintain_audit_log=True,
        escalate_high_value=False,       # tests opt in explicitly
        failure_rules={
            "INSUFFICIENT_FUNDS": "RETRY", "NETWORK_FAILURE": "RETRY",
            "EXPIRED_CARD": "PAYMENT_UPDATE", "INVALID_DETAILS": "CUSTOMER_NOTIFICATION",
            "BANK_DECLINE": "STOP", "OTHER": "ESCALATE",
        },
        version=1,
    )
    kw.update(overrides)
    return MerchantPolicy(**kw)


def make_failure(category=FailureCategory.INSUFFICIENT_FUNDS, **overrides) -> PaymentFailure:
    kw = dict(
        failure_category=category, failure_code="insufficient_fund",
        failure_reason="insufficient balance", attempt_number=1,
        occurred_at=NOW - timedelta(hours=1),
    )
    kw.update(overrides)
    return PaymentFailure(**kw)


def make_decision(confidence="0.8800", action=RecommendedAction.RETRY) -> RecoveryDecision:
    return RecoveryDecision(
        diagnosis="Insufficient funds", ai_confidence=Decimal(confidence),
        recovery_probability=Decimal("0.6800"), recommended_action=action,
        model_version="recoverai-v1", version_number=2,
    )


def make_ctx(**overrides) -> PolicyContext:
    payment = Payment(
        external_payment_id="PAY_POL_TEST", status=PaymentStatus.FAILED,
        attempt_number=1, amount=Decimal("8499.00"), currency="INR",
    )
    decision = make_decision()
    kw = dict(
        payment=payment,
        payment_failure=make_failure(),
        recovery_decision=decision,
        decision_is_current=True,
        policy_rules=make_policy(),
        existing_recovery_actions=[],
        retry_count=payment.attempt_number,
        payment_age_days=1.0,
        recovery_window_at=NOW + timedelta(hours=12),
        ai_confidence=0.88,
        recovery_probability=0.68,
        recommended_action=decision.recommended_action,
        payment_amount=payment.amount,
        failure_category="INSUFFICIENT_FUNDS",
        now=NOW,
    )
    kw.update(overrides)
    return PolicyContext(**kw)


def check(result, name):
    return next(c for c in result.checks if c.check_name == name)


# --- 1–2. retry limits -------------------------------------------------------


def test_retry_within_limit_passes():
    result = evaluate(make_ctx())
    assert check(result, "retry_limit").status is CheckStatus.PASS


def test_retry_at_limit_blocks():
    result = evaluate(make_ctx(retry_count=3))
    assert check(result, "retry_limit").status is CheckStatus.FAIL
    assert result.decision == "BLOCKED"
    assert not result.allowed


# --- 3–4. recovery window ----------------------------------------------------


def test_recovery_window_valid_passes():
    result = evaluate(make_ctx())
    assert check(result, "recovery_window").status is CheckStatus.PASS


def test_recovery_window_expired_blocks():
    stale = make_failure(occurred_at=NOW - timedelta(days=20))
    result = evaluate(make_ctx(payment_failure=stale))
    assert check(result, "recovery_window").status is CheckStatus.FAIL
    assert result.decision == "BLOCKED"


# --- 5–6. AI confidence ------------------------------------------------------


def test_confidence_above_threshold_passes():
    result = evaluate(make_ctx())
    assert check(result, "ai_confidence").status is CheckStatus.PASS


def test_confidence_below_threshold_blocks():
    # Confidence stays separate from probability: only confidence gates here.
    low = make_decision(confidence="0.4000")
    result = evaluate(make_ctx(recovery_decision=low, ai_confidence=0.40))
    assert check(result, "ai_confidence").status is CheckStatus.FAIL
    assert check(result, "ai_confidence").metadata["confidence"] == 0.40
    assert result.decision == "BLOCKED"


# --- 7–8. failure/action compatibility ----------------------------------------


def test_compatible_action_passes():
    result = evaluate(make_ctx())
    assert check(result, "action_compatibility").status is CheckStatus.PASS


def test_incompatible_action_blocks_without_replacement():
    result = evaluate(make_ctx(failure_category="BANK_DECLINE"))
    c = check(result, "action_compatibility")
    assert c.status is CheckStatus.FAIL
    # The recommendation surfaces untouched — never silently replaced.
    assert c.metadata["recommended_action"] == "RETRY"
    assert c.metadata["failure_category"] == "BANK_DECLINE"
    assert result.decision == "BLOCKED"


# --- 9. duplicates -----------------------------------------------------------


@pytest.mark.parametrize("status", [
    RecoveryActionStatus.PENDING, RecoveryActionStatus.SCHEDULED,
    RecoveryActionStatus.PROCESSING, RecoveryActionStatus.SUCCEEDED,
])
def test_blocking_action_statuses_block(status):
    active = RecoveryAction(action_type=RecommendedAction.RETRY, status=status)
    result = evaluate(make_ctx(existing_recovery_actions=[active]))
    assert check(result, "duplicate_recovery").status is CheckStatus.FAIL


def test_terminal_nonblocking_statuses_allow():
    done = RecoveryAction(action_type=RecommendedAction.RETRY,
                          status=RecoveryActionStatus.CANCELLED)
    result = evaluate(make_ctx(existing_recovery_actions=[done]))
    assert check(result, "duplicate_recovery").status is CheckStatus.PASS


# --- 10. recovered payment ---------------------------------------------------


def test_recovered_payment_blocks():
    payment = Payment(external_payment_id="P", status=PaymentStatus.RECOVERED,
                      attempt_number=1, amount=Decimal("100.00"), currency="INR")
    result = evaluate(make_ctx(payment=payment))
    assert check(result, "payment_state").status is CheckStatus.FAIL
    assert check(result, "payment_state").message == "Payment is already recovered."
    assert result.decision == "BLOCKED"


# --- 11–12. high value -------------------------------------------------------


def test_high_value_with_escalation_escalates():
    payment = Payment(external_payment_id="P", status=PaymentStatus.FAILED,
                      attempt_number=1, amount=Decimal("60000.00"), currency="INR")
    rules = make_policy(escalate_high_value=True)
    result = evaluate(make_ctx(payment=payment, payment_amount=payment.amount, policy_rules=rules))
    hv = check(result, "high_value")
    assert hv.status is CheckStatus.ESCALATE
    assert hv.metadata["requirement"] == "HUMAN_APPROVAL_REQUIRED"
    assert result.decision == "ESCALATED"
    assert not result.allowed


def test_high_value_with_escalation_disabled_continues():
    rules = make_policy(escalate_high_value=False)
    payment = Payment(external_payment_id="P", status=PaymentStatus.FAILED,
                      attempt_number=1, amount=Decimal("60000.00"), currency="INR")
    result = evaluate(make_ctx(payment=payment, payment_amount=payment.amount, policy_rules=rules))
    assert check(result, "high_value").status is CheckStatus.PASS
    assert result.decision == "APPROVED"
    assert result.allowed


# --- 13. explicit approval requirement ----------------------------------------


def test_required_approval_escalates_never_autoapproves():
    result = evaluate(make_ctx(policy_rules=make_policy(require_policy_approval=True)))
    assert check(result, "policy_approval").status is CheckStatus.ESCALATE
    assert "no automated approval" in check(result, "policy_approval").message
    assert result.decision == "ESCALATED"
    assert not result.allowed


# --- 14. missing policy fails safe --------------------------------------------


def test_missing_policy_blocked_not_approved():
    result = evaluate(make_ctx(policy_rules=None))
    assert result.decision == "BLOCKED"
    assert not result.allowed
    assert any("POLICY_NOT_CONFIGURED" in c.message for c in result.checks)
    assert result.policy_version == "none"


# --- 15–16. precedence ---------------------------------------------------------


def test_all_failed_checks_returned_together():
    payment = Payment(external_payment_id="P", status=PaymentStatus.HALTED,
                      attempt_number=5, amount=Decimal("100.00"), currency="INR")
    stale = make_failure(
        category=FailureCategory.BANK_DECLINE, failure_code="do_not_honour",
        attempt_number=5, occurred_at=NOW - timedelta(days=30),
    )
    result = evaluate(make_ctx(payment=payment, payment_failure=stale, retry_count=5))
    failed_names = {c.check_name for c in result.checks if c.status is CheckStatus.FAIL}
    assert {"payment_state", "recovery_window", "retry_limit"} <= failed_names
    # No short-circuiting: every applicable check still ran and is reported.
    assert len(result.checks) == 11


def test_hard_block_overrides_escalation():
    # Escalation-worthy amount AND a hard state block → BLOCKED wins.
    payment = Payment(external_payment_id="P", status=PaymentStatus.PROCESSING,
                      attempt_number=1, amount=Decimal("90000.00"), currency="INR")
    rules = make_policy(escalate_high_value=True)
    result = evaluate(make_ctx(payment=payment, payment_amount=payment.amount, policy_rules=rules))
    assert result.decision == "BLOCKED"
    assert any(c.status is CheckStatus.ESCALATE for c in result.checks)


# --- 17–18. policy versioning (DB-backed) --------------------------------------


def _upsert_request(base) -> PolicyUpsertRequest:
    return PolicyUpsertRequest(
        maximum_retries=base.maximum_retries + 1,
        recovery_window_days=base.recovery_window_days,
        minimum_ai_confidence=Decimal(str(base.minimum_ai_confidence)),
        high_value_threshold=Decimal(str(base.high_value_threshold)),
        prevent_duplicate_recovery=base.prevent_duplicate_recovery,
        require_policy_approval=False,
        maintain_audit_log=True,
        escalate_high_value=False,
        failure_rules=dict(base.failure_rules),
    )


def test_policy_update_bumps_version(db_session, merchant_id):
    storage = PolicyStorageService(db_session)
    before = storage.get_policies(merchant_id)
    updated = storage.upsert_policies(merchant_id, _upsert_request(before))

    assert updated.policy_version == before.policy_version + 1
    assert updated.maximum_retries == before.maximum_retries + 1


def test_policy_update_affects_new_evaluations_only(db_session, merchant_id):
    """Historical evaluation rows are immutable; only NEW evaluations see v+1."""
    from app.models import PolicyEvaluation
    from app.policy.service import PolicyService as PolicyEngineService
    from app.services.recovery_intelligence_service import RecoveryIntelligenceService

    engine = PolicyEngineService(db_session)

    # Build an approved-eligible payment: FAILED + analyzed + no approval gate.
    storage = PolicyStorageService(db_session)
    current = storage.get_policies(merchant_id)
    relaxed = PolicyUpsertRequest(
        maximum_retries=current.maximum_retries,
        recovery_window_days=current.recovery_window_days,
        minimum_ai_confidence=Decimal(str(current.minimum_ai_confidence)),
        high_value_threshold=Decimal(str(current.high_value_threshold)),
        prevent_duplicate_recovery=current.prevent_duplicate_recovery,
        require_policy_approval=False,
        maintain_audit_log=True,
        escalate_high_value=False,
        failure_rules=dict(current.failure_rules),
    )
    storage.upsert_policies(merchant_id, relaxed)

    RecoveryIntelligenceService(db_session).analyze(merchant_id, "PAY_82961")

    first_decision, first_eval = engine.evaluate_for_payment(merchant_id, "PAY_82961")
    version_before = first_eval.policy_version

    storage.upsert_policies(merchant_id, _upsert_request(current))
    _, second_eval = engine.evaluate_for_payment(merchant_id, "PAY_82961")

    assert second_eval.policy_version != version_before
    # The first row still points at the version that authorized it.
    db_session.expire_all()
    rows = db_session.scalars(select(PolicyEvaluation).where(
        PolicyEvaluation.payment_id == first_eval.payment_id
    ).order_by(PolicyEvaluation.created_at)).all()
    assert [r.policy_version for r in rows][-2:] == [version_before, second_eval.policy_version]
