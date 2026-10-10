"""Question bank: loading, filtering and CRUD."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from ..constants import DIFFICULTIES
from ..validators import clean_text, is_valid_id, validate_question

log = logging.getLogger(__name__)


class NotFoundError(LookupError):
    """Raised when a question does not exist."""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(text: str) -> str:
    return " ".join(clean_text(text, multiline=True).lower().split())


def list_questions(db) -> list[dict]:
    """Return all valid questions. Malformed or duplicate-id entries are skipped."""
    questions, seen = [], set()
    for item in db.questions.read()["questions"]:
        if not isinstance(item, dict):
            continue
        qid = item.get("id")
        if not is_valid_id(qid) or qid in seen:
            log.warning("Skipping question with missing or duplicate id: %r", qid)
            continue
        cleaned, errors = validate_question(item)
        if errors:
            log.warning("Skipping invalid question %s: %s", qid, sorted(errors))
            continue
        cleaned["id"] = qid
        cleaned["created_at"] = str(item.get("created_at", ""))
        cleaned["updated_at"] = str(item.get("updated_at", ""))
        questions.append(cleaned)
        seen.add(qid)
    return questions


def get_question(db, question_id: str) -> dict:
    for question in list_questions(db):
        if question["id"] == question_id:
            return question
    raise NotFoundError(question_id)


def filter_questions(questions, category=None, difficulty=None, search=None) -> list[dict]:
    needle = clean_text(search).lower() if search else ""
    result = []
    for q in questions:
        if category and q["category"] != category:
            continue
        if difficulty and q["difficulty"] != difficulty:
            continue
        if needle:
            haystack = " ".join([q["text"], q["category"], q["explanation"], *q["options"]]).lower()
            if needle not in haystack:
                continue
        result.append(q)
    return result


def category_names(questions) -> list[str]:
    return sorted({q["category"] for q in questions}, key=str.lower)


def category_summary(questions) -> list[dict]:
    summary: dict[str, dict] = {}
    for q in questions:
        row = summary.setdefault(
            q["category"], {"name": q["category"], "total": 0, **{d: 0 for d in DIFFICULTIES}}
        )
        row["total"] += 1
        row[q["difficulty"]] += 1
    return sorted(summary.values(), key=lambda r: r["name"].lower())


def availability(questions) -> dict:
    """{category or '': {'any': n, 'easy': n, ...}} for the setup page hints."""
    table = {"": {"any": 0, **{d: 0 for d in DIFFICULTIES}}}
    for q in questions:
        row = table.setdefault(q["category"], {"any": 0, **{d: 0 for d in DIFFICULTIES}})
        for target in (row, table[""]):
            target["any"] += 1
            target[q["difficulty"]] += 1
    return table


def find_duplicate(questions, text: str, category: str, exclude_id: str | None = None):
    key = normalize_text(text)
    for q in questions:
        if q["id"] != exclude_id and q["category"] == category and normalize_text(q["text"]) == key:
            return q
    return None


def create_question(db, cleaned: dict) -> dict:
    def mutate(data):
        existing = {q.get("id") for q in data["questions"] if isinstance(q, dict)}
        qid = uuid.uuid4().hex
        while qid in existing:  # pragma: no cover - astronomically unlikely
            qid = uuid.uuid4().hex
        now = _iso_now()
        record = {"id": qid, **cleaned, "created_at": now, "updated_at": now}
        data["questions"].append(record)
        return record

    return db.questions.update(mutate)


def update_question(db, question_id: str, cleaned: dict) -> dict:
    def mutate(data):
        for index, item in enumerate(data["questions"]):
            if isinstance(item, dict) and item.get("id") == question_id:
                record = {
                    "id": question_id,
                    **cleaned,
                    "created_at": item.get("created_at", _iso_now()),
                    "updated_at": _iso_now(),
                }
                data["questions"][index] = record
                return record
        raise NotFoundError(question_id)

    return db.questions.update(mutate)


def delete_question(db, question_id: str) -> None:
    def mutate(data):
        before = len(data["questions"])
        data["questions"] = [
            q for q in data["questions"] if not (isinstance(q, dict) and q.get("id") == question_id)
        ]
        if len(data["questions"]) == before:
            raise NotFoundError(question_id)

    db.questions.update(mutate)
