"""Action-vocabulary mapping between the frontend contract and canonical storage.

Frontend token NOTIFY ↔ backend CUSTOMER_NOTIFICATION. Everything else is
identical in both vocabularies.
"""

from app.models.enums import RecommendedAction

_FRONTEND_ALIASES: dict[str, str] = {
    "NOTIFY": "CUSTOMER_NOTIFICATION",
}


def frontend_to_canonical_action(token: str) -> str:
    """Normalize any accepted action token to the canonical storage value."""
    upper = token.upper()
    return _FRONTEND_ALIASES.get(upper, upper)


def canonical_to_frontend_action(action: RecommendedAction | str | None) -> str:
    """Convert a stored action into the frontend's vocabulary."""
    if action is None:
        return "NOTIFY"
    value = action.value if isinstance(action, RecommendedAction) else str(action)
    if value == "CUSTOMER_NOTIFICATION":
        return "NOTIFY"
    return value
