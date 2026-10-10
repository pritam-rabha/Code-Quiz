"""Quiz engine: random selection, attempts, server-side timing and scoring.

Design notes
* An attempt stores a *snapshot* of its questions (including the answer key) on
  the server only. The browser never receives the answer key or the deadline
  used for validation, and later edits to the question bank do not alter a
  quiz that is already running.
* All time checks use the server clock. ``now`` is injectable for tests.
* Finalising an attempt is idempotent: a second submit returns the stored result.
"""
from __future__ import annotations

import math
import random
import time
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ..constants import DIFFICULTY_LABELS
from ..validators import is_valid_id
from . import question_service, settings_service

ZERO = Decimal("0")


class QuizError(Exception):
    """A user-facing quiz error with an HTTP-ish status and a machine code."""

    def __init__(self, message: str, code: str = "invalid", status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def _now(now: float | None) -> float:
    return time.time() if now is None else float(now)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _money(value: Decimal, places: str = "0.01") -> float:
    return float(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


# ----------------------------------------------------------------- selection
def select_questions(
    questions: list[dict],
    category: str | None,
    difficulty: str | None,
    count: int,
    rng: random.Random | None = None,
) -> tuple[list[dict], str | None]:
    """Randomly pick up to ``count`` distinct questions.

    Returns ``(selected, notice)``. If fewer questions exist than requested the
    quiz is shortened and ``notice`` explains why. Raises ``QuizError`` when no
    question matches at all.
    """
    rng = rng or random.SystemRandom()
    pool = question_service.filter_questions(questions, category, difficulty)

    unique, seen_ids, seen_text = [], set(), set()
    for q in pool:  # never offer the same question twice in one quiz
        text_key = question_service.normalize_text(q["text"])
        if q["id"] in seen_ids or text_key in seen_text:
            continue
        seen_ids.add(q["id"])
        seen_text.add(text_key)
        unique.append(q)

    if not unique:
        raise QuizError(
            "No questions are available for that category and difficulty. Try another selection.",
            code="no_questions",
            status=422,
        )
    size = min(count, len(unique))
    selected = rng.sample(unique, size)
    notice = None
    if size < count:
        notice = (
            f"Only {size} question{'s' if size != 1 else ''} match this selection, "
            f"so the quiz has {size} instead of the {count} requested."
        )
    return selected, notice


# -------------------------------------------------------------------- scoring
def calculate_score(questions: list[dict], answers: dict[str, int], scoring: dict) -> dict:
    """Pure scoring function. ``scoring`` holds marks_correct, marks_incorrect (penalty
    magnitude) and marks_unanswered (penalty magnitude)."""
    mark_correct = Decimal(str(scoring["marks_correct"]))
    penalty_wrong = Decimal(str(scoring["marks_incorrect"]))
    penalty_blank = Decimal(str(scoring["marks_unanswered"]))

    total = ZERO
    details: list[dict] = []
    by_category: dict[str, dict[str, Any]] = {}
    counts = {"correct": 0, "incorrect": 0, "unanswered": 0}

    for q in questions:
        selected = answers.get(q["id"])
        if selected is None:
            outcome, marks = "unanswered", ZERO - penalty_blank
        elif selected == q["correct_index"]:
            outcome, marks = "correct", mark_correct
        else:
            outcome, marks = "incorrect", ZERO - penalty_wrong
        counts[outcome] += 1
        total += marks

        row = by_category.setdefault(
            q["category"],
            {"category": q["category"], "total": 0, "correct": 0, "incorrect": 0, "unanswered": 0, "score": ZERO},
        )
        row["total"] += 1
        row[outcome] += 1
        row["score"] += marks

        details.append(
            {
                "question_id": q["id"],
                "category": q["category"],
                "difficulty": q["difficulty"],
                "text": q["text"],
                "options": list(q["options"]),
                "selected_index": selected,
                "correct_index": q["correct_index"],
                "explanation": q["explanation"],
                "outcome": outcome,
                "marks": _money(marks),
            }
        )

    count = len(questions)
    accuracy = (Decimal(counts["correct"]) * 100 / count) if count else ZERO
    categories = []
    for row in sorted(by_category.values(), key=lambda r: r["category"].lower()):
        row_accuracy = Decimal(row["correct"]) * 100 / row["total"]
        categories.append(
            {**row, "score": _money(row["score"]), "accuracy": _money(row_accuracy, "0.1")}
        )
    return {
        "total_questions": count,
        "correct": counts["correct"],
        "incorrect": counts["incorrect"],
        "unanswered": counts["unanswered"],
        "score": _money(total),
        "max_score": _money(mark_correct * count),
        "accuracy": _money(accuracy, "0.1"),
        "details": details,
        "by_category": categories,
    }


# ------------------------------------------------------------------- attempts
def _ensure_participant(data: dict, participant_id: str | None, name: str, stamp: str) -> dict:
    if participant_id and is_valid_id(participant_id):
        for person in data["participants"]:
            if person.get("id") == participant_id:
                person["name"] = name
                person["last_seen"] = stamp
                person["quizzes_started"] = int(person.get("quizzes_started", 0)) + 1
                return person
    person = {
        "id": uuid.uuid4().hex,
        "name": name,
        "created_at": stamp,
        "last_seen": stamp,
        "quizzes_started": 1,
        "quizzes_completed": 0,
    }
    data["participants"].append(person)
    return person


def start_attempt(
    db,
    *,
    participant_id: str | None,
    name: str,
    category: str | None,
    difficulty: str | None,
    count: int,
    settings: dict | None = None,
    now: float | None = None,
    rng: random.Random | None = None,
    stale_seconds: int = 24 * 3600,
) -> dict:
    now = _now(now)
    settings = settings or settings_service.get_settings(db)
    with db.transaction():
        questions = question_service.list_questions(db)
        chosen, notice = select_questions(questions, category, difficulty, count, rng)
        size = len(chosen)
        duration = settings_service.compute_duration_seconds(settings, size)

        participants = db.participants.read()
        person = _ensure_participant(participants, participant_id, name, iso(now))
        db.participants.write(participants)

        attempt = {
            "id": uuid.uuid4().hex,
            "participant_id": person["id"],
            "participant_name": name,
            "category": category,
            "difficulty": difficulty,
            "requested_count": count,
            "notice": notice,
            "questions": [
                {
                    "id": q["id"],
                    "category": q["category"],
                    "difficulty": q["difficulty"],
                    "text": q["text"],
                    "options": list(q["options"]),
                    "correct_index": q["correct_index"],
                    "explanation": q["explanation"],
                }
                for q in chosen
            ],
            "answers": {},
            "scoring": settings_service.scoring_from_settings(settings),
            "started_at": now,
            "duration_seconds": duration,
            "deadline": now + duration,
        }
        attempts = db.attempts.read()
        attempts["attempts"] = [
            a for a in attempts["attempts"] if a.get("deadline", 0) + stale_seconds > now
        ]
        attempts["attempts"].append(attempt)
        db.attempts.write(attempts)
        return attempt


def get_attempt(db, attempt_id: str) -> dict | None:
    if not is_valid_id(attempt_id):
        return None
    for attempt in db.attempts.read()["attempts"]:
        if attempt.get("id") == attempt_id:
            return attempt
    return None


def remaining_seconds(attempt: dict, now: float | None = None) -> float:
    return max(0.0, attempt["deadline"] - _now(now))


def public_view(attempt: dict, now: float | None = None) -> dict:
    """What the browser may see: no answer key, no explanations, no deadline."""
    return {
        "attempt_id": attempt["id"],
        "category": attempt["category"] or "All categories",
        "difficulty": DIFFICULTY_LABELS.get(attempt["difficulty"] or "any"),
        "duration_seconds": attempt["duration_seconds"],
        "remaining_seconds": int(math.ceil(remaining_seconds(attempt, now))),
        "total": len(attempt["questions"]),
        "answers": dict(attempt["answers"]),
        "questions": [
            {
                "id": q["id"],
                "text": q["text"],
                "options": q["options"],
                "category": q["category"],
                "difficulty": DIFFICULTY_LABELS[q["difficulty"]],
            }
            for q in attempt["questions"]
        ],
    }


def _check_option(question: dict, option_index: Any) -> int | None:
    if option_index is None:
        return None
    if isinstance(option_index, bool) or not isinstance(option_index, int):
        raise QuizError("Invalid answer choice.", code="invalid_option")
    if option_index < 0 or option_index >= len(question["options"]):
        raise QuizError("Invalid answer choice.", code="invalid_option")
    return option_index


def record_answer(
    db, attempt_id: str, question_id: Any, option_index: Any, *, now: float | None = None, grace: int = 5
) -> float:
    """Save a single answer (or clear it with ``None``). Returns seconds remaining."""
    now = _now(now)
    if not is_valid_id(question_id):
        raise QuizError("Unknown question.", code="invalid_question")
    with db.transaction():
        data = db.attempts.read()
        attempt = next((a for a in data["attempts"] if a.get("id") == attempt_id), None)
        if attempt is None:
            raise QuizError("This quiz is no longer active.", code="not_active", status=409)
        if now > attempt["deadline"] + grace:
            raise QuizError("Time is up for this quiz.", code="expired", status=409)
        question = next((q for q in attempt["questions"] if q["id"] == question_id), None)
        if question is None:
            raise QuizError("Unknown question.", code="invalid_question")
        choice = _check_option(question, option_index)
        if choice is None:
            attempt["answers"].pop(question_id, None)
        else:
            attempt["answers"][question_id] = choice
        db.attempts.write(data)
        return max(0.0, attempt["deadline"] - now)


def validate_answer_payload(attempt: dict, payload: Any) -> dict[str, int | None]:
    if not isinstance(payload, dict):
        raise QuizError("Answers must be an object.", code="invalid_payload")
    if len(payload) > len(attempt["questions"]):
        raise QuizError("Too many answers submitted.", code="invalid_payload")
    by_id = {q["id"]: q for q in attempt["questions"]}
    cleaned: dict[str, int | None] = {}
    for qid, value in payload.items():
        question = by_id.get(qid)
        if question is None:
            raise QuizError("Answers include a question that is not part of this quiz.", code="invalid_question")
        cleaned[qid] = _check_option(question, value)
    return cleaned


def _result_for_attempt(db, attempt_id: str) -> dict | None:
    for result in db.results.read()["results"]:
        if result.get("attempt_id") == attempt_id:
            return result
    return None


def _finalize(db, attempt: dict, answers: dict, now: float, reason: str) -> dict:
    graded = calculate_score(attempt["questions"], answers, attempt["scoring"])
    ended = min(now, attempt["deadline"])
    result = {
        "id": uuid.uuid4().hex,
        "attempt_id": attempt["id"],
        "participant_id": attempt["participant_id"],
        "participant_name": attempt["participant_name"],
        "category": attempt["category"] or "All categories",
        "difficulty": attempt["difficulty"] or "any",
        "requested_count": attempt["requested_count"],
        **{k: graded[k] for k in ("total_questions", "correct", "incorrect", "unanswered", "score", "max_score", "accuracy")},
        "time_taken_seconds": int(max(0, round(ended - attempt["started_at"]))),
        "duration_seconds": attempt["duration_seconds"],
        "submission_type": reason,
        "started_at": iso(attempt["started_at"]),
        "submitted_at": iso(now),
        "scoring": attempt["scoring"],
        "by_category": graded["by_category"],
        "details": graded["details"],
    }
    results = db.results.read()
    results["results"].append(result)
    db.results.write(results)  # result first: a crash here leaves a recoverable duplicate-safe state

    remaining = db.attempts.read()
    remaining["attempts"] = [a for a in remaining["attempts"] if a.get("id") != attempt["id"]]
    db.attempts.write(remaining)

    people = db.participants.read()
    for person in people["participants"]:
        if person.get("id") == attempt["participant_id"]:
            person["quizzes_completed"] = int(person.get("quizzes_completed", 0)) + 1
            person["last_seen"] = iso(now)
    db.participants.write(people)
    return result


def submit_attempt(
    db, attempt_id: str, answers: Any = None, *, now: float | None = None, grace: int = 5
) -> tuple[dict, bool]:
    """Finalise an attempt. Returns ``(result, created)``; ``created`` is False when the
    attempt had already been submitted (duplicate submission)."""
    now = _now(now)
    with db.transaction():
        existing = _result_for_attempt(db, attempt_id)
        if existing:
            return existing, False
        attempt = get_attempt(db, attempt_id)
        if attempt is None:
            raise QuizError("This quiz is no longer active.", code="not_active", status=409)

        merged = dict(attempt["answers"])
        if now > attempt["deadline"] + grace:
            reason = "expired"  # late payloads are ignored; only answers saved in time count
        else:
            if answers is not None:
                for qid, choice in validate_answer_payload(attempt, answers).items():
                    if choice is None:
                        merged.pop(qid, None)
                    else:
                        merged[qid] = choice
            reason = "auto_timeout" if now >= attempt["deadline"] else "manual"
        return _finalize(db, attempt, merged, now, reason), True


def finalize_expired(db, attempt_id: str, *, now: float | None = None, grace: int = 5) -> dict | None:
    """If the attempt is past its deadline plus grace, close it with the saved answers."""
    now = _now(now)
    with db.transaction():
        existing = _result_for_attempt(db, attempt_id)
        if existing:
            return existing
        attempt = get_attempt(db, attempt_id)
        if attempt is None or now <= attempt["deadline"] + grace:
            return None
        return _finalize(db, attempt, dict(attempt["answers"]), now, "expired")
