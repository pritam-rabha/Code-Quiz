"""Small helpers shared by routes and templates."""
from __future__ import annotations

import time

from flask import current_app


def current_time() -> float:
    """Server clock. Routes call this via the module so tests can patch it."""
    return time.time()


def get_db():
    return current_app.extensions["quiz_db"]


def grace_seconds() -> int:
    return int(current_app.config["SUBMIT_GRACE_SECONDS"])
