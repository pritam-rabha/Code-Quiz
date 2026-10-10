"""End-to-end browser-style flows with a controllable server clock."""
import pytest

from helpers import parse_quiz_data, seed_questions, standard_bank, start_via_web


@pytest.fixture
def clock(monkeypatch):
    state = {"t": 1_900_000_000.0}
    monkeypatch.setattr("quiz_app.web.current_time", lambda: state["t"])
    return state


@pytest.fixture
def started(app, client, csrf, clock):
    seed_questions(app.extensions["quiz_db"], standard_bank(8))
    token = csrf()
    start_via_web(client, token, name="Ishaan Rao", category="Category A", count="5")
    return token, parse_quiz_data(client.get("/quiz").get_data(as_text=True))


def test_timer_counts_down_on_the_server(client, clock, started):
    token, data = started
    assert data["remaining_seconds"] == 300
    clock["t"] += 120
    assert parse_quiz_data(client.get("/quiz").get_data(as_text=True))["remaining_seconds"] == 180


def test_refresh_keeps_saved_answers(client, clock, started):
    token, data = started
    qid = data["questions"][2]["id"]
    reply = client.post("/quiz/answer", json={"question_id": qid, "option_index": 1}, headers={"X-CSRF-Token": token})
    assert reply.get_json() == {"ok": True, "remaining_seconds": 300}
    assert parse_quiz_data(client.get("/quiz").get_data(as_text=True))["answers"] == {qid: 1}


def test_manual_submit_scores_correctly_and_shows_review(client, app, clock, started):
    token, data = started
    db = app.extensions["quiz_db"]
    attempt = db.attempts.read()["attempts"][0]
    answers = {q["id"]: q["correct_index"] for q in attempt["questions"][:3]}
    answers[attempt["questions"][3]["id"]] = (attempt["questions"][3]["correct_index"] + 1) % 4
    clock["t"] += 90
    reply = client.post("/quiz/submit", json={"answers": answers}, headers={"X-CSRF-Token": token})
    page = client.get(reply.get_json()["redirect"]).get_data(as_text=True)
    assert "3 marks" not in page
    result = db.results.read()["results"][0]
    assert (result["correct"], result["incorrect"], result["unanswered"]) == (3, 1, 1)
    assert result["score"] == 3 * 4 - 1 and result["time_taken_seconds"] == 90
    assert "Explanation" in page and "Correct answer" in page and "Results by category" in page


def test_timeout_auto_submit_and_late_answers_are_refused(client, app, clock, started):
    token, data = started
    first = data["questions"][0]["id"]
    client.post("/quiz/answer", json={"question_id": first, "option_index": 0}, headers={"X-CSRF-Token": token})
    clock["t"] += 400
    late = client.post("/quiz/answer", json={"question_id": first, "option_index": 1}, headers={"X-CSRF-Token": token})
    assert late.status_code == 409 and late.get_json()["code"] == "expired" and "redirect" in late.get_json()
    result = app.extensions["quiz_db"].results.read()["results"][0]
    assert result["submission_type"] == "expired" and result["unanswered"] >= 4


def test_visiting_quiz_after_expiry_closes_it(client, app, clock, started):
    clock["t"] += 1000
    response = client.get("/quiz")
    assert response.status_code == 302 and "/results/" in response.headers["Location"]
    assert len(app.extensions["quiz_db"].results.read()["results"]) == 1
    assert app.extensions["quiz_db"].attempts.read()["attempts"] == []


def test_submit_after_deadline_within_grace_counts_payload(client, app, clock, started):
    token, data = started
    attempt = app.extensions["quiz_db"].attempts.read()["attempts"][0]
    answers = {q["id"]: q["correct_index"] for q in attempt["questions"]}
    clock["t"] += 302
    client.post("/quiz/submit", json={"answers": answers}, headers={"X-CSRF-Token": token})
    result = app.extensions["quiz_db"].results.read()["results"][0]
    assert result["submission_type"] == "auto_timeout" and result["correct"] == 5


def test_leaderboard_and_category_results_after_quiz(client, app, clock, started):
    token, data = started
    client.post("/quiz/submit", json={"answers": {}}, headers={"X-CSRF-Token": token})
    board = client.get("/leaderboard").get_data(as_text=True)
    assert "Ishaan Rao" in board and "You" in board
    assert "Ishaan Rao" in client.get("/leaderboard?category=Category+A").get_data(as_text=True)
    assert "Ishaan Rao" not in client.get("/leaderboard?category=Category+B").get_data(as_text=True)


def test_all_categories_quiz_reports_each_category(client, app, csrf, clock):
    seed_questions(app.extensions["quiz_db"], standard_bank(8))
    token = csrf()
    start_via_web(client, token, count="15")
    reply = client.post("/quiz/submit", json={"answers": {}}, headers={"X-CSRF-Token": token})
    result = app.extensions["quiz_db"].results.read()["results"][0]
    assert {c["category"] for c in result["by_category"]} == {"Category A", "Category B"}
    assert "Category B" in client.get(reply.get_json()["redirect"]).get_data(as_text=True)


def test_health_and_error_pages(client):
    assert client.get("/health").get_json() == {"status": "ok"}
    page = client.get("/nope")
    assert page.status_code == 404 and "Page not found" in page.get_data(as_text=True)
    assert client.get("/quiz/submit").status_code == 405
