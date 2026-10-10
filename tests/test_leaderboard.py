import pytest

from helpers import NOW, begin, correct_answers, seed_questions, standard_bank
from quiz_app.services import leaderboard_service, quiz_service


def result(i, score, accuracy, seconds=60, when=None, category="Category A", difficulty="any", name=None):
    return {
        "id": f"r{i}", "participant_name": name or f"P{i}", "score": score, "max_score": 20,
        "accuracy": accuracy, "category": category, "difficulty": difficulty, "total_questions": 5,
        "correct": 3, "time_taken_seconds": seconds, "submitted_at": when or f"2026-01-0{i}T10:00:00+00:00",
    }


def ranks(rows):
    return [(r["id"], r["rank"]) for r in rows]


def test_higher_score_ranks_first():
    rows = leaderboard_service.rank_results([result(1, 5, 40), result(2, 15, 80), result(3, 10, 60)])
    assert ranks(rows) == [("r2", 1), ("r3", 2), ("r1", 3)]


def test_ties_share_a_rank_and_next_rank_skips():
    rows = leaderboard_service.rank_results(
        [result(1, 10, 60), result(2, 10, 60), result(3, 20, 100), result(4, 4, 40)]
    )
    assert [r["rank"] for r in rows] == [1, 2, 2, 4]


def test_equal_score_is_broken_by_accuracy():
    rows = leaderboard_service.rank_results([result(1, 8, 60), result(2, 8, 80)])
    assert ranks(rows) == [("r2", 1), ("r1", 2)]


def test_tied_rows_are_listed_by_faster_time_then_date():
    rows = leaderboard_service.rank_results(
        [result(1, 10, 60, seconds=90), result(2, 10, 60, seconds=30), result(3, 10, 60, seconds=30, when="2025-12-01T00:00:00+00:00")]
    )
    assert [r["id"] for r in rows] == ["r3", "r2", "r1"]
    assert {r["rank"] for r in rows} == {1}


def test_ranking_is_deterministic_regardless_of_input_order():
    data = [result(i, 10 - (i % 3), 50) for i in range(1, 7)]
    assert ranks(leaderboard_service.rank_results(data)) == ranks(leaderboard_service.rank_results(list(reversed(data))))


def test_negative_scores_rank_below_positive():
    rows = leaderboard_service.rank_results([result(1, -3, 0), result(2, 0, 0)])
    assert ranks(rows) == [("r2", 1), ("r1", 2)]


def test_leaderboard_rows_expose_only_public_fields():
    row = leaderboard_service.rank_results([dict(result(1, 5, 40), details=["secret"], participant_id="pid")])[0]
    assert "details" not in row and "participant_id" not in row
    assert {"rank", "participant_name", "score", "accuracy", "submitted_at"} <= set(row)


def test_filters_and_pagination(db):
    db.results.write({"version": 1, "results": [result(i, i, 10 * i, category="Category A" if i % 2 else "Category B") for i in range(1, 8)]})
    only_a = leaderboard_service.get_leaderboard(db, category="Category A")
    assert only_a["total"] == 4 and {r["category"] for r in only_a["rows"]} == {"Category A"}
    page2 = leaderboard_service.get_leaderboard(db, page=2, per_page=3)
    assert page2["pages"] == 3 and [r["rank"] for r in page2["rows"]] == [4, 5, 6]
    assert leaderboard_service.get_leaderboard(db, page=99, per_page=3)["page"] == 3
    assert leaderboard_service.get_leaderboard(db, page=-5, per_page=3)["page"] == 1


def test_malformed_results_are_skipped(db):
    db.results.write({"version": 1, "results": [result(1, 5, 50), {"id": "bad"}, "junk", dict(result(2, 5, 50), score="high")]})
    assert [r["id"] for r in leaderboard_service.get_leaderboard(db)["rows"]] == ["r1"]


def test_saved_results_feed_the_leaderboard(db):
    seed_questions(db, standard_bank(8))
    a = begin(db, name="Alpha", now=NOW)
    quiz_service.submit_attempt(db, a["id"], correct_answers(a), now=NOW + 10)
    b = begin(db, name="Beta", now=NOW)
    quiz_service.submit_attempt(db, b["id"], {}, now=NOW + 10)
    rows = leaderboard_service.get_leaderboard(db)["rows"]
    assert [(r["participant_name"], r["rank"]) for r in rows] == [("Alpha", 1), ("Beta", 2)]
    assert rows[0]["accuracy"] == 100.0 and rows[0]["submitted_at"]


def test_rank_of_and_delete(db):
    db.results.write({"version": 1, "results": [result(1, 5, 50), result(2, 9, 80)]})
    assert leaderboard_service.rank_of(db, result(1, 5, 50)) == (2, 2)
    assert leaderboard_service.delete_result(db, "r2") is True
    assert leaderboard_service.delete_result(db, "r2") is False
    assert leaderboard_service.rank_of(db, result(1, 5, 50)) == (1, 1)


def test_leaderboard_page_renders_rows_and_filters(client, app):
    app.extensions["quiz_db"].results.write({"version": 1, "results": [result(1, 12, 75, name="Meera <b>"), result(2, 12, 75, name="Ravi")]})
    page = client.get("/leaderboard?category=Category+A&difficulty=bogus").get_data(as_text=True)
    assert "Meera &lt;b&gt;" in page and "Ravi" in page and "Meera <b>" not in page


def test_leaderboard_empty_state(client):
    assert "No results yet" in client.get("/leaderboard").get_data(as_text=True)


@pytest.mark.parametrize("query", ["page=abc", "page=-3", "category=" + "x" * 500, "difficulty=%00"])
def test_leaderboard_tolerates_bad_query_strings(client, query):
    assert client.get("/leaderboard?" + query).status_code == 200
