import random

import pytest

from helpers import make_question, seed_questions, standard_bank
from quiz_app.services import question_service, quiz_service
from quiz_app.services.quiz_service import QuizError


def test_selection_has_requested_size_and_no_duplicates():
    bank = standard_bank(10)
    chosen, notice = quiz_service.select_questions(bank, None, None, 8, random.Random(1))
    ids = [q["id"] for q in chosen]
    assert len(ids) == 8 and len(set(ids)) == 8
    assert notice is None


def test_selection_is_random_but_reproducible_with_a_seed():
    bank = standard_bank(10)
    first = [q["id"] for q in quiz_service.select_questions(bank, None, None, 6, random.Random(1))[0]]
    again = [q["id"] for q in quiz_service.select_questions(bank, None, None, 6, random.Random(1))[0]]
    other = [q["id"] for q in quiz_service.select_questions(bank, None, None, 6, random.Random(2))[0]]
    assert first == again
    assert first != other


def test_selection_varies_with_the_default_system_random():
    bank = standard_bank(10)
    runs = {tuple(q["id"] for q in quiz_service.select_questions(bank, None, None, 6)[0]) for _ in range(10)}
    assert len(runs) > 1


def test_category_filter():
    chosen, _ = quiz_service.select_questions(standard_bank(), "Category B", None, 4, random.Random(3))
    assert {q["category"] for q in chosen} == {"Category B"}


def test_difficulty_filter():
    chosen, _ = quiz_service.select_questions(standard_bank(), None, "hard", 3, random.Random(3))
    assert chosen and {q["difficulty"] for q in chosen} == {"hard"}


def test_category_and_difficulty_combined():
    chosen, _ = quiz_service.select_questions(standard_bank(), "Category A", "easy", 2, random.Random(3))
    assert {(q["category"], q["difficulty"]) for q in chosen} == {("Category A", "easy")}


def test_insufficient_questions_shortens_quiz_with_notice():
    chosen, notice = quiz_service.select_questions(standard_bank(3), "Category A", None, 10, random.Random(1))
    assert len(chosen) == 3
    assert "Only 3 questions" in notice and "10" in notice


def test_single_available_question_uses_singular_wording():
    chosen, notice = quiz_service.select_questions([make_question(1)], None, None, 5)
    assert len(chosen) == 1 and "Only 1 question " in notice


def test_no_matching_questions_raises_a_clear_error():
    with pytest.raises(QuizError) as info:
        quiz_service.select_questions(standard_bank(), "Missing", None, 5)
    assert info.value.code == "no_questions" and info.value.status == 422


def test_empty_bank_raises_error():
    with pytest.raises(QuizError):
        quiz_service.select_questions([], None, None, 5)


def test_duplicate_text_and_ids_are_collapsed():
    bank = [make_question(1), make_question(2, text="  TEST question number 1?  "), make_question(1)]
    chosen, _ = quiz_service.select_questions(bank, None, None, 3, random.Random(1))
    assert len(chosen) == 1


def test_category_summary_and_availability(db):
    seed_questions(db, standard_bank(6))
    questions = question_service.list_questions(db)
    summary = {row["name"]: row for row in question_service.category_summary(questions)}
    assert summary["Category A"]["total"] == 6
    assert summary["Category A"]["easy"] == summary["Category A"]["medium"] == summary["Category A"]["hard"] == 2
    table = question_service.availability(questions)
    assert table[""]["any"] == 12 and table["Category B"]["hard"] == 2


def test_invalid_stored_questions_are_skipped(db):
    good = make_question(1)
    bad_options = make_question(2, options=["only one"])
    bad_index = make_question(3, correct_index=9)
    no_id = {k: v for k, v in make_question(4).items() if k != "id"}
    seed_questions(db, [good, bad_options, bad_index, no_id, "junk", make_question(1)])
    assert [q["id"] for q in question_service.list_questions(db)] == ["t-001"]
