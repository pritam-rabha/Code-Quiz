"""Application configuration, driven entirely by environment variables.

Secrets are never hardcoded. In production (APP_ENV=production) the app refuses
to start without a strong SECRET_KEY.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:  # Optional: load a local .env file during development.
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover - python-dotenv is optional
    pass

log = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or unsafe."""


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def build_config(overrides: dict | None = None) -> dict:
    """Return the Flask configuration mapping."""
    overrides = dict(overrides or {})
    app_env = os.environ.get("APP_ENV", "development").strip().lower()
    production = app_env == "production"

    config = {
        "APP_ENV": app_env,
        "IS_PRODUCTION": production,
        "TESTING": False,
        "SECRET_KEY": os.environ.get("SECRET_KEY", "").strip(),
        "DATA_DIR": os.environ.get("DATA_DIR", str(BASE_DIR / "data")),
        "SAMPLE_QUESTIONS_PATH": str(BASE_DIR / "sample_data" / "questions.json"),
        "ADMIN_USERNAME": os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin",
        "ADMIN_PASSWORD_HASH": os.environ.get("ADMIN_PASSWORD_HASH", "").strip(),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": _env_bool("SESSION_COOKIE_SECURE", production),
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=12),
        "ADMIN_SESSION_MINUTES": _env_int("ADMIN_SESSION_MINUTES", 120),
        "MAX_CONTENT_LENGTH": 256 * 1024,
        "SUBMIT_GRACE_SECONDS": _env_int("SUBMIT_GRACE_SECONDS", 5),
        "LOGIN_MAX_ATTEMPTS": _env_int("LOGIN_MAX_ATTEMPTS", 5),
        "LOGIN_LOCK_SECONDS": _env_int("LOGIN_LOCK_SECONDS", 600),
        "TRUSTED_PROXIES": _env_int("TRUSTED_PROXIES", 1 if production else 0),
        "STALE_ATTEMPT_SECONDS": 24 * 3600,
        "SECRET_KEY_IS_EPHEMERAL": False,
    }
    config.update(overrides)

    if not config["SECRET_KEY"]:
        if config["IS_PRODUCTION"]:
            raise ConfigError(
                "SECRET_KEY is not set. Set a long random SECRET_KEY environment "
                "variable (for example: python -c \"import secrets; "
                "print(secrets.token_urlsafe(48))\")."
            )
        config["SECRET_KEY"] = secrets.token_hex(32)
        config["SECRET_KEY_IS_EPHEMERAL"] = True
        log.warning(
            "SECRET_KEY is not set; using a random key for this process. "
            "Sessions will reset on restart. Set SECRET_KEY in .env."
        )
    if config["IS_PRODUCTION"] and len(config["SECRET_KEY"]) < 32:
        raise ConfigError("SECRET_KEY must be at least 32 characters in production.")
    return config
