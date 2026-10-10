"""CSRF protection, security headers and admin session checks."""
from __future__ import annotations

import hmac
import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, redirect, request, session, url_for

from . import web

CSRF_SESSION_KEY = "_csrf_token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def _validate_csrf() -> None:
    expected = session.get(CSRF_SESSION_KEY, "")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(400, description="Your session expired or the form was invalid. Reload the page and try again.")


def is_admin() -> bool:
    if not session.get("is_admin"):
        return False
    limit = current_app.config["ADMIN_SESSION_MINUTES"] * 60
    if web.current_time() - float(session.get("admin_login_at", 0)) > limit:
        session.pop("is_admin", None)
        session.pop("admin_user", None)
        return False
    return True


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return redirect(url_for("admin.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapper


def is_safe_redirect(target: str | None) -> bool:
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc


def init_app(app) -> None:
    @app.before_request
    def protect_against_csrf():
        if request.method in UNSAFE_METHODS:
            _validate_csrf()

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'",
        )
        if current_app.config["IS_PRODUCTION"]:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["is_admin"] = is_admin
