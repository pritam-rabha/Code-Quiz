"""Administrator authentication.

Credentials come from (in priority order):
  1. ADMIN_USERNAME + ADMIN_PASSWORD_HASH environment variables
  2. data/admin.json (created with ``python scripts/admin_tool.py create-admin``)
Only password *hashes* are ever stored or configured.
"""
from __future__ import annotations

import functools
import hmac
import threading
from typing import Mapping

from werkzeug.security import check_password_hash, generate_password_hash

MIN_PASSWORD_LENGTH = 10


@functools.lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return generate_password_hash("not-a-real-password")


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    return generate_password_hash(password)


def get_admin_credentials(db, config: Mapping) -> tuple[str, str] | None:
    env_hash = (config.get("ADMIN_PASSWORD_HASH") or "").strip()
    if env_hash:
        return config.get("ADMIN_USERNAME") or "admin", env_hash
    stored = db.admin.read()
    username, pw_hash = stored.get("username"), stored.get("password_hash")
    if isinstance(username, str) and isinstance(pw_hash, str) and username and pw_hash:
        return username, pw_hash
    return None


def admin_configured(db, config: Mapping) -> bool:
    return get_admin_credentials(db, config) is not None


def verify_credentials(db, config: Mapping, username: str, password: str) -> bool:
    """Constant-effort check: a hash comparison always runs, even for unknown users."""
    credentials = get_admin_credentials(db, config)
    if credentials is None:
        check_password_hash(_dummy_hash(), password or "")
        return False
    expected_user, pw_hash = credentials
    try:
        password_ok = check_password_hash(pw_hash, password or "")
    except ValueError:  # malformed hash in configuration
        return False
    user_ok = hmac.compare_digest((username or "").encode("utf-8"), expected_user.encode("utf-8"))
    return bool(password_ok and user_ok)


def create_admin(db, username: str, password: str) -> None:
    username = (username or "").strip()
    if not 3 <= len(username) <= 40:
        raise ValueError("Username must be between 3 and 40 characters.")
    db.admin.write({"username": username, "password_hash": hash_password(password)})


class LoginThrottle:
    """In-memory limiter: too many failures from one address lock logins for a while."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 600):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str, now: float) -> int:
        with self._lock:
            recent = [t for t in self._failures.get(key, []) if now - t < self.window]
            self._failures[key] = recent
            if len(recent) >= self.max_attempts:
                return max(1, int(recent[0] + self.window - now))
            return 0

    def record_failure(self, key: str, now: float) -> None:
        with self._lock:
            self._failures.setdefault(key, []).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
