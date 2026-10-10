import pytest

from helpers import make_question
from quiz_app.services import quiz_service, settings_service
from quiz_app.constants import DEFAULT_SETTINGS

QUESTIONS = [make_question(i, "Category A" if i <= 2 else "Category B", correct=i % 4) for i in range(1, 5)]
KEY = {q["id"]: q["correct_index"] for q in QUESTIONS}


def scheme(correct=4, wrong=1, blank=0):
    return {"marks_correct": correct, "marks_incorrect": wrong, "marks_unanswered": blank}


def wrong_choice(q):
    return (q["correct_index"] + 1) % 4


def test_all_correct():
    out = quiz_service.calculate_score(QUESTIONS, dict(KEY), scheme())
    assert (out["score"], out["max_score"], out["accuracy"]) == (16, 16, 100.0)


def test_negative_marking_deducts_for_wrong_answers():
    answers = {QUESTIONS[0]["id"]: KEY["t-001"], QUESTIONS[1]["id"]: wrong_choice(QUESTIONS[1])}
    out = quiz_service.calculate_score(QUESTIONS, answers, scheme())
    assert out["score"] == 4 - 1  # one right, one wrong, two unanswered
    assert (out["correct"], out["incorrect"], out["unanswered"]) == (1, 1, 2)


def test_unanswered_questions_are_not_penalised_by_default():
    out = quiz_service.calculate_score(QUESTIONS, {}, scheme())
    assert out["score"] == 0 and out["unanswered"] == 4


def test_unanswered_penalty_applies_only_when_configured():
    out = quiz_service.calculate_score(QUESTIONS, {}, scheme(blank=0.5))
    assert out["score"] == -2.0


def test_total_can_be_negative():
    answers = {q["id"]: wrong_choice(q) for q in QUESTIONS}
    out = quiz_service.calculate_score(QUESTIONS, answers, scheme())
    assert out["score"] == -4 and out["accuracy"] == 0.0


def test_fractional_marks_are_exact():
    answers = {q["id"]: wrong_choice(q) for q in QUESTIONS[:3]}
    out = quiz_service.calculate_score(QUESTIONS, answers, scheme(correct=1, wrong=0.25))
    assert out["score"] == -0.75
    answers[QUESTIONS[3]["id"]] = KEY[QUESTIONS[3]["id"]]
    assert quiz_service.calculate_score(QUESTIONS, answers, scheme(correct=1, wrong=0.25))["score"] == 0.25


def test_accuracy_is_correct_over_total_questions():
    answers = {QUESTIONS[0]["id"]: KEY["t-001"]}
    assert quiz_service.calculate_score(QUESTIONS, answers, scheme())["accuracy"] == 25.0


def test_category_breakdown():
    answers = {"t-001": KEY["t-001"], "t-002": wrong_choice(QUESTIONS[1]), "t-003": KEY["t-003"]}
    out = quiz_service.calculate_score(QUESTIONS, answers, scheme())
    rows = {r["category"]: r for r in out["by_category"]}
    assert rows["Category A"]["correct"] == 1 and rows["Category A"]["incorrect"] == 1
    assert rows["Category A"]["score"] == 3.0
    assert rows["Category B"]["correct"] == 1 and rows["Category B"]["unanswered"] == 1
    assert rows["Category B"]["score"] == 4.0
    assert sum(r["score"] for r in rows.values()) == out["score"]


def test_details_include_key_and_explanation_for_review():
    out = quiz_service.calculate_score(QUESTIONS, {"t-001": 3}, scheme())
    first = out["details"][0]
    assert first["selected_index"] == 3 and first["correct_index"] == KEY["t-001"]
    assert first["explanation"] and first["outcome"] == "incorrect" and first["marks"] == -1


def test_empty_quiz_scores_zero():
    out = quiz_service.calculate_score([], {}, scheme())
    assert out["score"] == 0 and out["accuracy"] == 0


def test_negative_marking_can_be_disabled_in_settings():
    settings = dict(DEFAULT_SETTINGS, negative_marking_enabled=False, marks_incorrect=2.0)
    assert settings_service.scoring_from_settings(settings)["marks_incorrect"] == 0.0


def test_unanswered_penalty_ignored_unless_enabled_in_settings():
    settings = dict(DEFAULT_SETTINGS, penalize_unanswered=False, marks_unanswered=3.0)
    assert settings_service.scoring_from_settings(settings)["marks_unanswered"] == 0.0
    settings["penalize_unanswered"] = True
    assert settings_service.scoring_from_settings(settings)["marks_unanswered"] == 3.0


@pytest.mark.parametrize("correct,wrong,expected", [(4, 1, 3), (2, 0, 2), (1, 0.5, 0.5), (5, 5, 0)])
def test_one_right_one_wrong(correct, wrong, expected):
    answers = {"t-001": KEY["t-001"], "t-002": wrong_choice(QUESTIONS[1])}
    out = quiz_service.calculate_score(QUESTIONS[:2], answers, scheme(correct, wrong))
    assert out["score"] == expected
