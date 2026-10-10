"""Aggregate numbers for the admin dashboard."""
from __future__ import annotations

from . import question_service


def dashboard_stats(db) -> dict:
    questions = question_service.list_questions(db)
    results = [r for r in db.results.read()["results"] if isinstance(r, dict) and "score" in r]
    participants = db.participants.read()["participants"]
    active = db.attempts.read()["attempts"]

    percentages = [
        r["score"] / r["max_score"] * 100 for r in results if r.get("max_score")
    ]
    recent = sorted(results, key=lambda r: r.get("submitted_at", ""), reverse=True)[:8]
    return {
        "question_count": len(questions),
        "categories": question_service.category_summary(questions),
        "result_count": len(results),
        "participant_count": len(participants),
        "active_attempts": len(active),
        "average_percentage": round(sum(percentages) / len(percentages), 1) if percentages else None,
        "recent": recent,
    }
