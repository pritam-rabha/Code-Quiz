import pytest

from helpers import NOW, begin, correct_answers, seed_questions, standard_bank
from quiz_app.constants import DEFAULT_SETTINGS
from quiz_app.services import quiz_service, settings_service
from quiz_app.services.quiz_service import QuizError

GRACE = 5


@pytest.fixture
def seeded(db):
    seed_questions(db, standard_bank(8))
    return db


def test_duration_scales_with_quiz_length():
    s = dict(DEFAULT_SETTINGS, duration_minutes=10, default_question_count=10)
    assert settings_service.compute_duration_seconds(s, 10) == 600
    assert settings_service.compute_duration_seconds(s, 5) == 300
    assert settings_service.compute_duration_seconds(s, 20) == 1200


def test_duration_has_a_minimum():
    s = dict(DEFAULT_SETTINGS, duration_minutes=1, default_question_count=100)
    assert settings_service.compute_duration_seconds(s, 1) == 30


def test_attempt_deadline_is_set_by_the_server(seeded):
    attempt = begin(seeded, count=5, now=NOW)
    assert attempt["started_at"] == NOW
    assert attempt["deadline"] == NOW + attempt["duration_seconds"] == NOW + 300


def test_public_view_hides_answer_key_and_deadline(seeded):
    view = quiz_service.public_view(begin(seeded, now=NOW), NOW + 10)
    text = str(view)
    assert "correct_index" not in text and "explanation" not in text and "deadline" not in text
    assert view["remaining_seconds"] == 290


def test_remaining_seconds_never_negative(seeded):
    attempt = begin(seeded, now=NOW)
    assert quiz_service.remaining_seconds(attempt, NOW + 10_000) == 0


def test_answer_saved_within_time(seeded):
    attempt = begin(seeded, now=NOW)
    qid = attempt["questions"][0]["id"]
    left = quiz_service.record_answer(seeded, attempt["id"], qid, 2, now=NOW + 30, grace=GRACE)
    assert left == 270
    assert quiz_service.get_attempt(seeded, attempt["id"])["answers"] == {qid: 2}


def test_answer_can_be_cleared(seeded):
    attempt = begin(seeded, now=NOW)
    qid = attempt["questions"][0]["id"]
    quiz_service.record_answer(seeded, attempt["id"], qid, 1, now=NOW + 1, grace=GRACE)
    quiz_service.record_answer(seeded, attempt["id"], qid, None, now=NOW + 2, grace=GRACE)
    assert quiz_service.get_attempt(seeded, attempt["id"])["answers"] == {}


def test_answer_accepted_inside_grace_but_rejected_after(seeded):
    attempt = begin(seeded, now=NOW)
    qid = attempt["questions"][0]["id"]
    quiz_service.record_answer(seeded, attempt["id"], qid, 0, now=NOW + 300 + GRACE, grace=GRACE)
    with pytest.raises(QuizError) as info:
        quiz_service.record_answer(seeded, attempt["id"], qid, 1, now=NOW + 300 + GRACE + 1, grace=GRACE)
    assert info.value.code == "expired" and info.value.status == 409


def test_manual_submission_before_deadline(seeded):
    attempt = begin(seeded, now=NOW)
    result, created = quiz_service.submit_attempt(seeded, attempt["id"], correct_answers(attempt), now=NOW + 100, grace=GRACE)
    assert created and result["submission_type"] == "manual"
    assert result["score"] == result["max_score"] == 20
    assert result["time_taken_seconds"] == 100


def test_submission_at_deadline_is_marked_auto_timeout(seeded):
    attempt = begin(seeded, now=NOW)
    result, _ = quiz_service.submit_attempt(seeded, attempt["id"], correct_answers(attempt), now=NOW + 301, grace=GRACE)
    assert result["submission_type"] == "auto_timeout"
    assert result["time_taken_seconds"] == 300  # capped at the allowed duration


def test_late_submission_ignores_payload_and_uses_saved_answers(seeded):
    attempt = begin(seeded, now=NOW)
    first = attempt["questions"][0]
    quiz_service.record_answer(seeded, attempt["id"], first["id"], first["correct_index"], now=NOW + 5, grace=GRACE)
    result, _ = quiz_service.submit_attempt(seeded, attempt["id"], correct_answers(attempt), now=NOW + 400, grace=GRACE)
    assert result["submission_type"] == "expired"
    assert result["correct"] == 1 and result["unanswered"] == 4


def test_late_submission_with_garbage_payload_does_not_error(seeded):
    attempt = begin(seeded, now=NOW)
    result, _ = quiz_service.submit_attempt(seeded, attempt["id"], "garbage", now=NOW + 999, grace=GRACE)
    assert result["submission_type"] == "expired"


def test_duplicate_submission_returns_same_result_once(seeded):
    attempt = begin(seeded, now=NOW)
    first, created1 = quiz_service.submit_attempt(seeded, attempt["id"], correct_answers(attempt), now=NOW + 10, grace=GRACE)
    second, created2 = quiz_service.submit_attempt(seeded, attempt["id"], {}, now=NOW + 11, grace=GRACE)
    assert created1 and not created2
    assert second["id"] == first["id"] and second["score"] == first["score"]
    assert len(seeded.results.read()["results"]) == 1
    assert seeded.attempts.read()["attempts"] == []


def test_submitting_unknown_attempt_fails(seeded):
    with pytest.raises(QuizError) as info:
        quiz_service.submit_attempt(seeded, "f" * 32, {}, now=NOW, grace=GRACE)
    assert info.value.code == "not_active"


def test_finalize_expired_only_after_deadline_plus_grace(seeded):
    attempt = begin(seeded, now=NOW)
    assert quiz_service.finalize_expired(seeded, attempt["id"], now=NOW + 303, grace=GRACE) is None
    result = quiz_service.finalize_expired(seeded, attempt["id"], now=NOW + 306, grace=GRACE)
    assert result["submission_type"] == "expired"
    assert quiz_service.finalize_expired(seeded, attempt["id"], now=NOW + 400, grace=GRACE)["id"] == result["id"]


def test_attempt_uses_snapshot_so_later_edits_do_not_change_scoring(seeded):
    attempt = begin(seeded, now=NOW)
    answers = correct_answers(attempt)
    seed_questions(seeded, [])  # admin deletes everything mid-quiz
    result, _ = quiz_service.submit_attempt(seeded, attempt["id"], answers, now=NOW + 20, grace=GRACE)
    assert result["score"] == result["max_score"]


def test_settings_snapshot_is_used_for_marking(seeded):
    attempt = begin(seeded, now=NOW)
    seeded.settings.write(dict(DEFAULT_SETTINGS, marks_correct=99.0))
    result, _ = quiz_service.submit_attempt(seeded, attempt["id"], correct_answers(attempt), now=NOW + 20, grace=GRACE)
    assert result["max_score"] == 20


def test_stale_attempts_are_purged_on_start(seeded):
    old = begin(seeded, now=NOW)
    begin(seeded, now=NOW + 3 * 24 * 3600)
    ids = [a["id"] for a in seeded.attempts.read()["attempts"]]
    assert old["id"] not in ids and len(ids) == 1
