import pytest

from helpers import NOW, begin, correct_answers, parse_quiz_data, seed_questions, standard_bank, start_via_web
from quiz_app.services import quiz_service
from quiz_app.services.quiz_service import QuizError


@pytest.fixture
def attempt(db):
    seed_questions(db, standard_bank(8))
    return begin(db, now=NOW)


@pytest.mark.parametrize("bad", ["x", 3.5, True, -1, 4, 99, [1], {"a": 1}])
def test_invalid_option_values_are_rejected(db, attempt, bad):
    qid = attempt["questions"][0]["id"]
    with pytest.raises(QuizError):
        quiz_service.submit_attempt(db, attempt["id"], {qid: bad}, now=NOW + 5)


def test_unknown_question_id_is_rejected(db, attempt):
    with pytest.raises(QuizError) as info:
        quiz_service.submit_attempt(db, attempt["id"], {"not-in-quiz": 0}, now=NOW + 5)
    assert info.value.code == "invalid_question"


def test_payload_must_be_an_object(db, attempt):
    with pytest.raises(QuizError):
        quiz_service.submit_attempt(db, attempt["id"], [1, 2, 3], now=NOW + 5)


def test_rejected_submission_leaves_attempt_active(db, attempt):
    with pytest.raises(QuizError):
        quiz_service.submit_attempt(db, attempt["id"], {"bogus": 0}, now=NOW + 5)
    assert quiz_service.get_attempt(db, attempt["id"]) is not None
    assert db.results.read()["results"] == []


def test_record_answer_validates_question_and_option(db, attempt):
    with pytest.raises(QuizError):
        quiz_service.record_answer(db, attempt["id"], "../etc/passwd", 0, now=NOW + 1)
    with pytest.raises(QuizError):
        quiz_service.record_answer(db, attempt["id"], attempt["questions"][0]["id"], 7, now=NOW + 1)


def test_record_answer_on_unknown_attempt(db):
    with pytest.raises(QuizError) as info:
        quiz_service.record_answer(db, "a" * 32, "t-001", 0, now=NOW)
    assert info.value.code == "not_active"


# ----------------------------------------------------------------- over HTTP
@pytest.fixture
def web_quiz(client, csrf, app):
    seed_questions(app.extensions["quiz_db"], standard_bank(8))
    token = csrf()
    assert start_via_web(client, token).status_code == 302
    page = client.get("/quiz").get_data(as_text=True)
    return token, parse_quiz_data(page)


def test_post_without_csrf_token_is_rejected(client, web_quiz):
    _, data = web_quiz
    response = client.post("/quiz/submit", json={"answers": {}})
    assert response.status_code == 400 and response.get_json()["ok"] is False


def test_post_with_wrong_csrf_token_is_rejected(client, web_quiz):
    response = client.post("/quiz/submit", json={"answers": {}}, headers={"X-CSRF-Token": "forged"})
    assert response.status_code == 400


def test_client_cannot_inject_score_or_timer_fields(client, app, web_quiz):
    token, data = web_quiz
    payload = {"answers": {}, "score": 9999, "max_score": 1, "remaining_seconds": 99999, "deadline": 1e12, "correct": 5}
    response = client.post("/quiz/submit", json=payload, headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    result = app.extensions["quiz_db"].results.read()["results"][0]
    assert result["score"] == 0 and result["correct"] == 0 and result["unanswered"] == 5


def test_quiz_page_never_contains_answer_key(web_quiz, client):
    page = client.get("/quiz").get_data(as_text=True)
    assert "correct_index" not in page and "Explanation for question" not in page


def test_invalid_json_to_answer_endpoint(client, web_quiz):
    token, _ = web_quiz
    response = client.post("/quiz/answer", data="not json", headers={"X-CSRF-Token": token, "Content-Type": "application/json"})
    assert response.status_code == 400


def test_answer_endpoint_rejects_bad_option(client, web_quiz):
    token, data = web_quiz
    response = client.post("/quiz/answer", json={"question_id": data["questions"][0]["id"], "option_index": 42}, headers={"X-CSRF-Token": token})
    assert response.status_code == 400 and response.get_json()["code"] == "invalid_option"


def test_double_submit_creates_one_result(client, app, web_quiz):
    token, data = web_quiz
    answers = {q["id"]: 0 for q in data["questions"]}
    first = client.post("/quiz/submit", json={"answers": answers}, headers={"X-CSRF-Token": token})
    second = client.post("/quiz/submit", json={"answers": answers}, headers={"X-CSRF-Token": token})
    assert first.status_code == 200
    assert second.status_code in (200, 409)
    assert len(app.extensions["quiz_db"].results.read()["results"]) == 1


def test_other_participants_cannot_open_a_result(app, client, web_quiz):
    token, data = web_quiz
    reply = client.post("/quiz/submit", json={"answers": {}}, headers={"X-CSRF-Token": token})
    url = reply.get_json()["redirect"]
    assert client.get(url).status_code == 200
    assert app.test_client().get(url).status_code == 404


def test_result_ids_are_validated(client):
    assert client.get("/results/..%2Fsecret").status_code == 404
    assert client.get("/results/" + "z" * 100).status_code == 404


def test_second_quiz_cannot_be_started_while_one_is_active(client, csrf, app, web_quiz):
    token, _ = web_quiz
    response = start_via_web(client, token, count="10")
    assert response.status_code == 302 and response.headers["Location"].endswith("/quiz")
    assert len(app.extensions["quiz_db"].attempts.read()["attempts"]) == 1


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"name": "A"}, "name"),
        ({"name": "<script>alert(1)</script>"}, "name"),
        ({"count": "7"}, "count"),
        ({"count": "abc"}, "count"),
        ({"category": "Nope"}, "category"),
        ({"difficulty": "extreme"}, "difficulty"),
    ],
)
def test_invalid_quiz_setup_is_rejected(app, client, csrf, overrides, field):
    seed_questions(app.extensions["quiz_db"], standard_bank(8))
    response = start_via_web(client, csrf(), **overrides)
    assert response.status_code == 422
    assert f'id="{field}' in response.get_data(as_text=True) or "is-invalid" in response.get_data(as_text=True)
    assert app.extensions["quiz_db"].attempts.read()["attempts"] == []


def test_quiz_with_few_questions_starts_with_notice(app, client, csrf):
    seed_questions(app.extensions["quiz_db"], standard_bank(2))
    response = start_via_web(client, csrf(), category="Category A", count="10")
    assert response.status_code == 302
    page = client.get("/quiz").get_data(as_text=True)
    assert "Only 2 questions match" in page and parse_quiz_data(page)["total"] == 2


def test_empty_bank_gives_friendly_error(app, client, csrf):
    seed_questions(app.extensions["quiz_db"], [])
    response = start_via_web(client, csrf())
    assert response.status_code == 422 and "No questions are available" in response.get_data(as_text=True)
