"""Password hashing utilities for merchant authentication."""

import bcrypt


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt (adaptive, salted)."""
    pw_bytes = password.encode("utf-8")
    # bcrypt recommends truncation at 72 bytes to avoid library errors
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
    hashed = bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
    return bcrypt.checkpw(pw_bytes, hashed.encode("ascii"))
