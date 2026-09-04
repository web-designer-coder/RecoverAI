"""Domain enumerations shared by models and schemas.

All enums are stored as VARCHAR (`native_enum=False`) so new values — e.g. raw
Razorpay failure codes in Phase 3 — can be added without a Postgres enum migration.
"""

import enum


class MerchantStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    PENDING = "PENDING"


class Environment(str, enum.Enum):
    TEST = "TEST"
    LIVE = "LIVE"


class PaymentMethod(str, enum.Enum):
    UPI = "UPI"
    CARD = "CARD"
    NET_BANKING = "NET_BANKING"
    # Added in Phase 3 for Razorpay ingestion: provider methods outside the
    # original three map to WALLET (wallets/EMI etc. are refined here) or OTHER.
    WALLET = "WALLET"
    OTHER = "OTHER"


class PaymentStatus(str, enum.Enum):
    FAILED = "FAILED"
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    PROCESSING = "PROCESSING"
    RECOVERED = "RECOVERED"
    HALTED = "HALTED"
    NEEDS_ACTION = "NEEDS_ACTION"
    # Phase 3: funds authorized at the bank but not yet captured. Deliberately
    # distinct from RECOVERED — authorization alone is not money received.
    AUTHORIZED = "AUTHORIZED"


class Priority(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FailureCategory(str, enum.Enum):
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    EXPIRED_CARD = "EXPIRED_CARD"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    BANK_DECLINE = "BANK_DECLINE"
    INVALID_DETAILS = "INVALID_DETAILS"
    OTHER = "OTHER"


class RecommendedAction(str, enum.Enum):
    RETRY = "RETRY"
    PAYMENT_UPDATE = "PAYMENT_UPDATE"
    CUSTOMER_NOTIFICATION = "CUSTOMER_NOTIFICATION"
    ESCALATE = "ESCALATE"
    STOP = "STOP"


class RecoveryActionStatus(str, enum.Enum):
    PENDING = "PENDING"
    # Phase 5 execution state machine (VARCHAR storage — no migration needed):
    VERIFYING_POLICY = "VERIFYING_POLICY"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    # The recovery step requires the customer to act (e.g. complete a payment
    # link, update their method) — recorded honestly, never faked as success.
    CUSTOMER_ACTION_REQUIRED = "CUSTOMER_ACTION_REQUIRED"


class PolicyOutcome(str, enum.Enum):
    """Final policy-engine verdicts. Precedence: BLOCKED > ESCALATED > APPROVED."""

    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"


class AuditEventType(str, enum.Enum):
    PAYMENT_FAILED = "PAYMENT_FAILED"
    AI_DIAGNOSIS = "AI_DIAGNOSIS"
    RECOVERY_PREDICTION = "RECOVERY_PREDICTION"
    ACTION_SELECTED = "ACTION_SELECTED"
    POLICY_CHECK = "POLICY_CHECK"
    RECOVERY_SCHEDULED = "RECOVERY_SCHEDULED"
    # Phase 5 execution lifecycle (VARCHAR storage — no migration needed).
    RECOVERY_PROCESSING = "RECOVERY_PROCESSING"
    RECOVERY_EXECUTED = "RECOVERY_EXECUTED"
    PAYMENT_RECOVERED = "PAYMENT_RECOVERED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    RECOVERY_HALTED = "RECOVERY_HALTED"
    CUSTOMER_NOTIFIED = "CUSTOMER_NOTIFIED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    POLICY_ESCALATED = "POLICY_ESCALATED"
    # Phase 3: webhook ingestion + reconciliation.
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PROVIDER_SYNC = "PROVIDER_SYNC"


class AuditCategory(str, enum.Enum):
    AI_DECISION = "AI_DECISION"
    POLICY = "POLICY"
    EXECUTION = "EXECUTION"
    RESULT = "RESULT"
    INGESTION = "INGESTION"


class ActorType(str, enum.Enum):
    SYSTEM = "SYSTEM"
    AI_ENGINE = "AI_ENGINE"
    OPERATOR = "OPERATOR"
    MERCHANT = "MERCHANT"
