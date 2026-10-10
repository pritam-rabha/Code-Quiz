"""Shared helpers for tests."""
import json
import re

from quiz_app.services import quiz_service

NOW = 1_800_000_000.0


def make_question(i, category="Category A", difficulty="easy", correct=0, **extra):
    base = {
        "id": f"t-{i:03d}",
        "category": category,
        "difficulty": difficulty,
        "text": f"Test question number {i}?",
        "options": ["Option one", "Option two", "Option three", "Option four"],
        "correct_index": correct,
        "explanation": f"Explanation for question {i}.",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(extra)
    return base


def seed_questions(db, questions):
    db.questions.write({"version": 1, "questions": list(questions)})


def standard_bank(per_category=6):
    """Two categories, mixed difficulty."""
    items, n = [], 0
    for category in ("Category A", "Category B"):
        for k in range(per_category):
            n += 1
            items.append(make_question(n, category, ("easy", "medium", "hard")[k % 3], correct=k % 4))
    return items


def begin(db, *, count=5, category=None, difficulty=None, now=NOW, name="Test Person", participant_id=None, settings=None, rng=None):
    return quiz_service.start_attempt(
        db,
        participant_id=participant_id,
        name=name,
        category=category,
        difficulty=difficulty,
        count=count,
        settings=settings,
        now=now,
        rng=rng,
    )


def correct_answers(attempt):
    return {q["id"]: q["correct_index"] for q in attempt["questions"]}


def parse_quiz_data(html):
    return json.loads(re.search(r'id="quiz-data">(.*?)</script>', html, re.S).group(1))


def start_via_web(client, token, **overrides):
    form = {"csrf_token": token, "name": "Asha Verma", "category": "", "difficulty": "any", "count": "5"}
    form.update(overrides)
    return client.post("/quiz/start", data=form)
