"""Quiz settings: defaults, loading, saving and derived values."""
from __future__ import annotations

import logging
import math

from ..constants import DEFAULT_SETTINGS
from ..validators import validate_settings

log = logging.getLogger(__name__)


def get_settings(db) -> dict:
    """Return validated settings; invalid or missing values fall back to defaults."""
    stored = db.settings.read()
    merged = {key: stored.get(key, default) for key, default in DEFAULT_SETTINGS.items()}
    cleaned, errors = validate_settings(merged)
    if errors:
        log.warning("Ignoring invalid stored settings: %s", sorted(errors))
    result = dict(DEFAULT_SETTINGS)
    result.update(cleaned)
    if result["default_question_count"] not in result["length_options"]:
        result["default_question_count"] = result["length_options"][0]
    return result


def save_settings(db, cleaned: dict) -> dict:
    data = dict(DEFAULT_SETTINGS)
    data.update(cleaned)
    db.settings.write(data)
    return data


def scoring_from_settings(settings: dict) -> dict:
    """Effective marking scheme: penalties are zero unless explicitly enabled."""
    return {
        "marks_correct": float(settings["marks_correct"]),
        "marks_incorrect": float(settings["marks_incorrect"]) if settings["negative_marking_enabled"] else 0.0,
        "marks_unanswered": float(settings["marks_unanswered"]) if settings["penalize_unanswered"] else 0.0,
        "negative_marking_enabled": bool(settings["negative_marking_enabled"]),
        "penalize_unanswered": bool(settings["penalize_unanswered"]),
    }


def compute_duration_seconds(settings: dict, question_count: int) -> int:
    """Time allowed for a quiz; scales with length relative to the default quiz."""
    base = settings["duration_minutes"] * 60
    scaled = base * question_count / settings["default_question_count"]
    return max(30, int(math.floor(scaled + 0.5)))
