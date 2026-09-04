"""Simple in-memory rate limiter for authentication endpoints (Phase 26.5).

Tracks per-key attempt counts within a sliding window. No external dependencies
beyond the Python standard library. The singleton `limiter` is imported by both
main.py (for the exception handler) and route modules (for hit/reset checks).
"""

import time
from collections import defaultdict


class _RateLimiter:
    """Fixed-window rate limiter backed by an in-memory dict.

    Each key maps to a list of timestamps. ``hit()`` appends the current time
    and returns *True* if the count within the window is within the limit.
    ``reset()`` clears the key's history.
    """

    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = defaultdict(list)

    @staticmethod
    def _parse_window(limit_str: str) -> tuple[int, float]:
        """Parse ``'5/minute'`` → (max_attempts, window_seconds)."""
        count_str, period = limit_str.split("/")
        count = int(count_str)
        periods = {
            "second": 1.0,
            "minute": 60.0,
            "hour": 3600.0,
            "day": 86400.0,
        }
        return count, periods.get(period, 60.0)

    def hit(self, limit_str: str, key: str) -> bool:
        """Record an attempt. Returns True if within limit, False if exceeded."""
        max_attempts, window = self._parse_window(limit_str)
        now = time.monotonic()
        cutoff = now - window

        # Prune expired entries.
        self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]

        if len(self._attempts[key]) >= max_attempts:
            return False

        self._attempts[key].append(now)
        return True

    def reset(self, key: str) -> None:
        """Clear all recorded attempts for *key*."""
        self._attempts.pop(key, None)

    def clear(self) -> None:
        """Clear all recorded attempts (for testing)."""
        self._attempts.clear()


# Module-level singleton — shared by main.py and route modules.
limiter = _RateLimiter()
