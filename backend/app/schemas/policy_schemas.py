"""Policy schemas — validated storage round-trip for the merchant rule set."""

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import FailureCategory, RecommendedAction
from app.utils.mapping import frontend_to_canonical_action

_ALL_CATEGORIES = {c.value for c in FailureCategory}


def _normalize_rules(rules: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in rules.items():
        if key not in _ALL_CATEGORIES:
            raise ValueError(f"Unknown failure category: {key}")
        normalized[key] = frontend_to_canonical_action(value)
    return normalized


class FailureRuleMap(dict[str, str]):
    """dict subclass carrying validation for the JSONB failure_rules column."""

    @classmethod
    def validate(cls, rules: dict[str, str]) -> "FailureRuleMap":
        return cls(_normalize_rules(rules))


class PolicyUpsertRequest(BaseModel):
    maximum_retries: int = Field(ge=1, le=10)
    recovery_window_days: int = Field(ge=1, le=90)
    minimum_ai_confidence: Decimal = Field(ge=0, le=100)
    high_value_threshold: Decimal = Field(ge=0)
    prevent_duplicate_recovery: bool = True
    require_policy_approval: bool = True
    maintain_audit_log: bool = True
    escalate_high_value: bool = True
    # Accepts canonical actions or the frontend's NOTIFY alias; stored canonically.
    failure_rules: dict[str, str]

    @field_validator("failure_rules")
    @classmethod
    def check_failure_rules(cls, v: dict[str, str]) -> dict[str, str]:
        try:
            return _normalize_rules(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class PolicyResponse(BaseModel):
    policy_version: int = 1
    maximum_retries: int
    recovery_window_days: int
    minimum_ai_confidence: float
    high_value_threshold: float
    prevent_duplicate_recovery: bool
    require_policy_approval: bool
    maintain_audit_log: bool
    escalate_high_value: bool
    # Returned using canonical action tokens.
    failure_rules: dict[str, str]
