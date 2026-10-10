"""Server-side input validation.

Every validator returns ``(cleaned, errors)`` where ``errors`` maps a field name
to a human-readable message. Nothing here trusts the browser.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .constants import ANY_DIFFICULTY, DIFFICULTIES, MAX_OPTIONS, MIN_OPTIONS

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_NAME_EXTRA = set(" .'-_")
_CATEGORY_EXTRA = set(" &-.+#()'/,")


def is_valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(ID_RE.fullmatch(value))


def clean_text(value: Any, *, multiline: bool = False) -> str:
    """Normalise unicode, drop control characters and tidy whitespace."""
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(ch for ch in value if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    if multiline:
        lines = [line.rstrip() for line in value.split("\n")]
        return "\n".join(lines).strip("\n").strip()
    return " ".join(value.split())


def _chars_ok(text: str, extra: set[str]) -> bool:
    return all(
        ch.isalnum() or unicodedata.category(ch).startswith("M") or ch in extra for ch in text
    )


def parse_int(value: Any, lo: int, hi: int) -> int:
    """Parse an integer in [lo, hi]; raises ValueError with a readable message."""
    if isinstance(value, bool):
        raise ValueError("must be a whole number")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("must be a whole number")
    try:
        number = int(str(value).strip()) if not isinstance(value, (int, float)) else int(value)
    except (TypeError, ValueError):
        raise ValueError("must be a whole number") from None
    if number < lo or number > hi:
        raise ValueError(f"must be between {lo} and {hi}")
    return number


def parse_decimal(value: Any, lo: float, hi: float, places: int = 2) -> float:
    if isinstance(value, bool):
        raise ValueError("must be a number")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError("must be a number") from None
    if not number.is_finite():
        raise ValueError("must be a number")
    if number < Decimal(str(lo)) or number > Decimal(str(hi)):
        raise ValueError(f"must be between {lo:g} and {hi:g}")
    if number != number.quantize(Decimal(1).scaleb(-places)):
        raise ValueError(f"use at most {places} decimal places")
    return float(number)


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "yes"}
    return False


# --------------------------------------------------------------------- names
def validate_participant_name(raw: Any) -> tuple[str, str | None]:
    name = clean_text(raw)
    if len(name) < 2 or len(name) > 50:
        return name, "Enter a name between 2 and 50 characters."
    if not _chars_ok(name, _NAME_EXTRA):
        return name, "Use letters, numbers, spaces, apostrophes, hyphens and full stops only."
    return name, None


def validate_category_name(raw: Any) -> tuple[str, str | None]:
    category = clean_text(raw)
    if len(category) < 2 or len(category) > 40:
        return category, "Category must be between 2 and 40 characters."
    if not _chars_ok(category, _CATEGORY_EXTRA):
        return category, "Category contains characters that are not allowed."
    return category, None


# ------------------------------------------------------------- quiz request
def validate_quiz_request(
    data: Mapping[str, Any], settings: Mapping[str, Any], categories: list[str]
) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    cleaned: dict[str, Any] = {}

    name, err = validate_participant_name(data.get("name", ""))
    cleaned["name"] = name
    if err:
        errors["name"] = err

    category = clean_text(data.get("category", ""))
    if category in ("", "all"):
        cleaned["category"] = None
    elif category in categories:
        cleaned["category"] = category
    else:
        cleaned["category"] = None
        errors["category"] = "Choose one of the listed categories."

    difficulty = clean_text(data.get("difficulty", ANY_DIFFICULTY)).lower() or ANY_DIFFICULTY
    if difficulty == ANY_DIFFICULTY:
        cleaned["difficulty"] = None
    elif difficulty in DIFFICULTIES:
        cleaned["difficulty"] = difficulty
    else:
        cleaned["difficulty"] = None
        errors["difficulty"] = "Choose a valid difficulty."

    try:
        count = parse_int(data.get("count", ""), 1, 100)
        if count not in settings["length_options"]:
            raise ValueError("choose one of the listed quiz lengths")
        cleaned["count"] = count
    except ValueError as exc:
        cleaned["count"] = None
        errors["count"] = f"Quiz length: {exc}."
    return cleaned, errors


# ---------------------------------------------------------------- questions
def validate_question(data: Mapping[str, Any]) -> tuple[dict, dict]:
    """Validate a question submitted from the admin form or loaded from storage.

    ``options`` is a list of raw option strings. Blank entries are dropped and
    ``correct_index`` (an index into the submitted list) is remapped accordingly.
    """
    errors: dict[str, str] = {}
    cleaned: dict[str, Any] = {}

    category, err = validate_category_name(data.get("category", ""))
    cleaned["category"] = category
    if err:
        errors["category"] = err

    difficulty = clean_text(data.get("difficulty", "")).lower()
    cleaned["difficulty"] = difficulty
    if difficulty not in DIFFICULTIES:
        errors["difficulty"] = "Choose easy, medium or hard."

    text = clean_text(data.get("text", ""), multiline=True)
    cleaned["text"] = text
    if len(text) < 5 or len(text) > 1000:
        errors["text"] = "Question text must be between 5 and 1000 characters."

    explanation = clean_text(data.get("explanation", ""), multiline=True)
    cleaned["explanation"] = explanation
    if len(explanation) < 5 or len(explanation) > 1000:
        errors["explanation"] = "Explanation must be between 5 and 1000 characters."

    raw_options = data.get("options", [])
    if not isinstance(raw_options, (list, tuple)):
        raw_options = []
    if len(raw_options) > MAX_OPTIONS:
        errors["options"] = f"Use at most {MAX_OPTIONS} options."
        raw_options = list(raw_options)[:MAX_OPTIONS]

    try:
        raw_correct = parse_int(data.get("correct_index", ""), 0, MAX_OPTIONS - 1)
    except ValueError:
        raw_correct = None

    options: list[str] = []
    correct_index = None
    for position, raw in enumerate(raw_options):
        option = clean_text(raw)
        if not option:
            continue
        if position == raw_correct:
            correct_index = len(options)
        options.append(option)
    cleaned["options"] = options
    cleaned["correct_index"] = correct_index

    if "options" not in errors:
        lowered = [o.lower() for o in options]
        if len(options) < MIN_OPTIONS:
            errors["options"] = f"Provide at least {MIN_OPTIONS} non-empty options."
        elif any(len(o) > 300 for o in options):
            errors["options"] = "Each option must be 300 characters or fewer."
        elif len(set(lowered)) != len(lowered):
            errors["options"] = "Options must be different from each other."
    if correct_index is None and "options" not in errors:
        errors["correct_index"] = "Mark exactly one non-empty option as the correct answer."
    elif correct_index is None:
        errors["correct_index"] = "Mark one of the options as the correct answer."
    return cleaned, errors


# ----------------------------------------------------------------- settings
def validate_settings(data: Mapping[str, Any]) -> tuple[dict, dict]:
    """Validate quiz settings. Only valid fields appear in ``cleaned``."""
    errors: dict[str, str] = {}
    cleaned: dict[str, Any] = {}

    def field(name, label, parser):
        try:
            cleaned[name] = parser(data.get(name))
        except ValueError as exc:
            errors[name] = f"{label} {exc}."

    field("duration_minutes", "Duration", lambda v: parse_int(v, 1, 180))
    field("default_question_count", "Default question count", lambda v: parse_int(v, 1, 100))

    def parse_lengths(value):
        if isinstance(value, str):
            parts = [p for p in re.split(r"[,\s]+", value.strip()) if p]
        elif isinstance(value, (list, tuple)):
            parts = list(value)
        else:
            raise ValueError("must be a list of whole numbers")
        numbers = sorted({parse_int(p, 1, 100) for p in parts})
        if not 1 <= len(numbers) <= 8:
            raise ValueError("must contain between 1 and 8 different values")
        return numbers

    field("length_options", "Quiz lengths", parse_lengths)
    field("marks_correct", "Marks for a correct answer", lambda v: parse_decimal(v, 0.01, 100))
    field("marks_incorrect", "Penalty for a wrong answer", lambda v: parse_decimal(v, 0, 100))
    field("marks_unanswered", "Penalty for an unanswered question", lambda v: parse_decimal(v, 0, 100))
    cleaned["negative_marking_enabled"] = to_bool(data.get("negative_marking_enabled"))
    cleaned["penalize_unanswered"] = to_bool(data.get("penalize_unanswered"))

    if (
        "length_options" in cleaned
        and "default_question_count" in cleaned
        and cleaned["default_question_count"] not in cleaned["length_options"]
    ):
        errors["default_question_count"] = "Default question count must be one of the quiz lengths."
    return cleaned, errors


# ------------------------------------------------------------------ filters
def clean_filter(value: Any, allowed: list[str] | tuple[str, ...] | None = None) -> str | None:
    text = clean_text(value)
    if not text or len(text) > 60:
        return None
    if allowed is not None and text not in allowed:
        return None
    return text
