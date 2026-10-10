"""Shared constants."""
from __future__ import annotations

DIFFICULTIES = ("easy", "medium", "hard")
DIFFICULTY_LABELS = {"easy": "Easy", "medium": "Medium", "hard": "Hard", "any": "Any difficulty"}
ANY_DIFFICULTY = "any"

MIN_OPTIONS = 2
MAX_OPTIONS = 6

DEFAULT_SETTINGS = {
    # Time allowed for a quiz with `default_question_count` questions.
    # Other quiz lengths scale proportionally.
    "duration_minutes": 10,
    "default_question_count": 10,
    "length_options": [5, 10, 15, 20],
    "marks_correct": 4.0,
    "negative_marking_enabled": True,
    "marks_incorrect": 1.0,  # penalty magnitude, stored as a positive number
    "penalize_unanswered": False,
    "marks_unanswered": 0.0,  # penalty per unanswered question when enabled
}

SUBMISSION_LABELS = {
    "manual": "Submitted by participant",
    "auto_timeout": "Auto-submitted when time expired",
    "expired": "Closed by the server after time expired",
}
