"""Leaderboard ranking and result lookups.

Ranking rule (documented in the README):
  1. higher score first
  2. higher accuracy first
Participants with the same score AND accuracy share a rank (standard
competition ranking: 1, 2, 2, 4). Within a tied group, faster completion and
then the earlier submission is listed first; this affects display order only.
"""
from __future__ import annotations

from typing import Iterable

PUBLIC_FIELDS = (
    "id",
    "participant_name",
    "score",
    "max_score",
    "accuracy",
    "category",
    "difficulty",
    "total_questions",
    "correct",
    "time_taken_seconds",
    "submitted_at",
)


def _tie_key(result: dict) -> tuple:
    return (result["score"], result["accuracy"])


def rank_results(results: Iterable[dict]) -> list[dict]:
    ordered = sorted(
        results,
        key=lambda r: (-r["score"], -r["accuracy"], r["time_taken_seconds"], r["submitted_at"], r["id"]),
    )
    ranked, previous_key, previous_rank = [], None, 0
    for position, result in enumerate(ordered, start=1):
        key = _tie_key(result)
        rank = previous_rank if key == previous_key else position
        previous_key, previous_rank = key, rank
        row = {field: result.get(field) for field in PUBLIC_FIELDS}
        row["rank"] = rank
        ranked.append(row)
    return ranked


def _matches(result: dict, category: str | None, difficulty: str | None) -> bool:
    if category and result.get("category") != category:
        return False
    if difficulty and result.get("difficulty") != difficulty:
        return False
    return True


def get_leaderboard(db, category=None, difficulty=None, page: int = 1, per_page: int = 25) -> dict:
    results = [r for r in db.results.read()["results"] if _valid_result(r) and _matches(r, category, difficulty)]
    ranked = rank_results(results)
    total = len(ranked)
    pages = max(1, -(-total // per_page))
    page = min(max(1, page), pages)
    start = (page - 1) * per_page
    return {
        "rows": ranked[start : start + per_page],
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": per_page,
    }


def _valid_result(result) -> bool:
    try:
        return (
            isinstance(result, dict)
            and isinstance(result["id"], str)
            and isinstance(result["score"], (int, float))
            and isinstance(result["accuracy"], (int, float))
            and isinstance(result["time_taken_seconds"], (int, float))
            and isinstance(result["submitted_at"], str)
        )
    except KeyError:
        return False


def get_result(db, result_id: str) -> dict | None:
    for result in db.results.read()["results"]:
        if _valid_result(result) and result["id"] == result_id:
            return result
    return None


def rank_of(db, result: dict) -> tuple[int, int]:
    """Return (rank, participants) among results with the same category and difficulty."""
    pool = [
        r
        for r in db.results.read()["results"]
        if _valid_result(r)
        and r.get("category") == result["category"]
        and r.get("difficulty") == result["difficulty"]
    ]
    for row in rank_results(pool):
        if row["id"] == result["id"]:
            return row["rank"], len(pool)
    return 1, len(pool)


def delete_result(db, result_id: str) -> bool:
    def mutate(data):
        before = len(data["results"])
        data["results"] = [r for r in data["results"] if not (isinstance(r, dict) and r.get("id") == result_id)]
        return len(data["results"]) != before

    return db.results.update(mutate)
