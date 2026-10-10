"""Quiz Application factory."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import build_config

from . import security
from .constants import DIFFICULTY_LABELS, SUBMISSION_LABELS
from .services.auth_service import LoginThrottle
from .storage import Database, StorageError


def create_app(test_config: dict | None = None) -> Flask:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Flask(__name__)
    app.config.from_mapping(build_config(test_config))

    if app.config["TRUSTED_PROXIES"]:
        count = app.config["TRUSTED_PROXIES"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=count, x_proto=count, x_host=count)

    data_dir = Path(app.config["DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    app.extensions["quiz_db"] = Database(data_dir, app.config["SAMPLE_QUESTIONS_PATH"])
    app.extensions["login_throttle"] = LoginThrottle(
        app.config["LOGIN_MAX_ATTEMPTS"], app.config["LOGIN_LOCK_SECONDS"]
    )

    security.init_app(app)
    _register_filters(app)

    from .routes.admin import bp as admin_bp
    from .routes.public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    _register_errors(app)
    return app


def _register_filters(app: Flask) -> None:
    @app.template_filter("dt")
    def format_datetime(value):
        try:
            return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M UTC")
        except (TypeError, ValueError):
            return "Unknown"

    @app.template_filter("duration")
    def format_duration(seconds):
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return "-"
        minutes, secs = divmod(max(0, seconds), 60)
        return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"

    @app.template_filter("marks")
    def format_marks(value):
        try:
            return f"{float(value):g}"
        except (TypeError, ValueError):
            return "-"

    @app.template_filter("signed")
    def format_signed(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "-"
        return f"+{number:g}" if number > 0 else f"{number:g}"

    @app.template_filter("letter")
    def option_letter(index):
        return chr(ord("A") + int(index))

    app.jinja_env.globals["DIFFICULTY_LABELS"] = DIFFICULTY_LABELS
    app.jinja_env.globals["SUBMISSION_LABELS"] = SUBMISSION_LABELS


_TITLES = {
    400: "Request could not be processed",
    403: "Access denied",
    404: "Page not found",
    405: "Method not allowed",
    413: "Request too large",
    429: "Too many attempts",
    500: "Something went wrong",
}


def _register_errors(app: Flask) -> None:
    def wants_json() -> bool:
        return (
            request.is_json
            or request.path in ("/quiz/answer", "/quiz/submit")
            or request.accept_mimetypes.best == "application/json"
        )

    def handle(error):
        code = error.code if isinstance(error, HTTPException) else 500
        if code == 500:
            app.logger.exception("Unhandled error", exc_info=error)
            message = "An unexpected error occurred. Please try again."
        else:
            message = getattr(error, "description", None) or _TITLES.get(code, "Error")
        if wants_json():
            return jsonify(ok=False, error=message, code="http_%d" % code), code
        return render_template("error.html", code=code, title=_TITLES.get(code, "Error"), message=message), code

    for code in _TITLES:
        app.register_error_handler(code, handle)
    app.register_error_handler(StorageError, lambda e: handle(e))
