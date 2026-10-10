import pytest

from conftest import get_csrf
from helpers import make_question, seed_questions, standard_bank
from quiz_app.services import question_service, settings_service
from quiz_app.validators import validate_question, validate_settings


def form(**over):
    data = {
        "category": "Networking", "difficulty": "medium", "text": "Which layer routes packets?",
        "option_0": "Transport", "option_1": "Network", "option_2": "Session", "option_3": "",
        "option_4": "", "option_5": "", "correct_index": "1", "explanation": "The network layer handles routing.",
    }
    data.update(over)
    return data


def post(client, url, data):
    return client.post(url, data={"csrf_token": get_csrf(client, "/admin/"), **data})


def test_add_question_end_to_end(admin_client, app):
    response = post(admin_client, "/admin/questions/new", form())
    assert response.status_code == 302
    questions = question_service.list_questions(app.extensions["quiz_db"])
    added = next(q for q in questions if q["category"] == "Networking")
    assert added["options"] == ["Transport", "Network", "Session"] and added["correct_index"] == 1
    assert len(added["id"]) == 32


def test_blank_options_are_dropped_and_correct_index_remapped():
    cleaned, errors = validate_question({**form(), "options": ["", "A", "", "B"], "correct_index": "3"})
    assert not errors and cleaned["options"] == ["A", "B"] and cleaned["correct_index"] == 1


@pytest.mark.parametrize(
    "override,field",
    [
        ({"text": "hi"}, "text"),
        ({"category": ""}, "category"),
        ({"category": "Bad<>"}, "category"),
        ({"difficulty": "impossible"}, "difficulty"),
        ({"explanation": ""}, "explanation"),
        ({"option_1": "", "option_2": ""}, "options"),
        ({"option_1": "Transport"}, "options"),
        ({"correct_index": "3"}, "correct_index"),
        ({"correct_index": ""}, "correct_index"),
        ({"option_0": "x" * 301}, "options"),
    ],
)
def test_invalid_questions_are_rejected(admin_client, app, override, field):
    before = len(question_service.list_questions(app.extensions["quiz_db"]))
    response = post(admin_client, "/admin/questions/new", form(**override))
    assert response.status_code == 422
    assert f"{field}-error" in response.get_data(as_text=True)
    assert len(question_service.list_questions(app.extensions["quiz_db"])) == before


def test_duplicate_question_text_in_category_is_rejected(admin_client):
    assert post(admin_client, "/admin/questions/new", form()).status_code == 302
    response = post(admin_client, "/admin/questions/new", form(text="  WHICH layer routes   packets? "))
    assert response.status_code == 422 and "already exists" in response.get_data(as_text=True)
    assert post(admin_client, "/admin/questions/new", form(category="Other Topic")).status_code == 302


def test_edit_question(admin_client, app):
    db = app.extensions["quiz_db"]
    target = question_service.list_questions(db)[0]
    page = admin_client.get(f"/admin/questions/{target['id']}/edit")
    assert page.status_code == 200 and target["text"].split()[0] in page.get_data(as_text=True)
    response = post(admin_client, f"/admin/questions/{target['id']}/edit", form(category=target["category"]))
    assert response.status_code == 302
    updated = question_service.get_question(db, target["id"])
    assert updated["text"] == "Which layer routes packets?" and updated["created_at"] == target["created_at"]
    assert updated["updated_at"] >= target["updated_at"]


def test_edit_with_errors_keeps_data(admin_client, app):
    target = question_service.list_questions(app.extensions["quiz_db"])[0]
    response = post(admin_client, f"/admin/questions/{target['id']}/edit", form(text="no", category=target["category"]))
    assert response.status_code == 422
    assert target["text"] == question_service.get_question(app.extensions["quiz_db"], target["id"])["text"]


def test_delete_question(admin_client, app):
    db = app.extensions["quiz_db"]
    target = question_service.list_questions(db)[0]
    assert post(admin_client, f"/admin/questions/{target['id']}/delete", {}).status_code == 302
    with pytest.raises(question_service.NotFoundError):
        question_service.get_question(db, target["id"])
    assert post(admin_client, f"/admin/questions/{target['id']}/delete", {}).status_code == 404


def test_unknown_or_malformed_ids_give_404(admin_client):
    assert admin_client.get("/admin/questions/does-not-exist/edit").status_code == 404
    assert admin_client.get("/admin/questions/bad%20id/edit").status_code == 404


def test_search_and_category_filters(admin_client, app):
    seed_questions(app.extensions["quiz_db"], [
        make_question(1, "Python", text="What is a decorator?"), make_question(2, "Python", difficulty="hard", text="Explain the GIL"),
        make_question(3, "SQL", text="What does JOIN do?"),
    ])
    page = admin_client.get("/admin/questions?q=decorator").get_data(as_text=True)
    assert "What is a decorator?" in page and "Explain the GIL" not in page
    page = admin_client.get("/admin/questions?category=SQL").get_data(as_text=True)
    assert "What does JOIN do?" in page and "decorator" not in page
    page = admin_client.get("/admin/questions?difficulty=hard").get_data(as_text=True)
    assert "Explain the GIL" in page and "JOIN" not in page
    assert "No questions match" in admin_client.get("/admin/questions?q=zzzzzz").get_data(as_text=True)


def test_questions_can_be_categorised_with_a_new_category(admin_client, app):
    post(admin_client, "/admin/questions/new", form(category="Brand New Topic"))
    names = question_service.category_names(question_service.list_questions(app.extensions["quiz_db"]))
    assert "Brand New Topic" in names
    assert "Brand New Topic" in admin_client.get("/quiz/setup").get_data(as_text=True)


def test_question_text_is_escaped_in_pages(admin_client, app):
    seed_questions(app.extensions["quiz_db"], [make_question(1, text="Is <script>alert(1)</script> safe?")])
    assert "<script>alert(1)</script>" not in admin_client.get("/admin/questions").get_data(as_text=True)


def test_dashboard_shows_statistics(admin_client):
    page = admin_client.get("/admin/").get_data(as_text=True)
    assert "Question bank by category" in page and "Python Fundamentals" in page


# -------------------------------------------------------------------- settings
def settings_form(**over):
    data = {
        "duration_minutes": "20", "default_question_count": "10", "length_options": "5, 10, 25",
        "marks_correct": "2", "marks_incorrect": "0.5", "marks_unanswered": "0.25",
        "negative_marking_enabled": "on", "penalize_unanswered": "on",
    }
    data.update(over)
    return {k: v for k, v in data.items() if v is not None}


def test_settings_are_saved_and_used(admin_client, app):
    assert post(admin_client, "/admin/settings", settings_form()).status_code == 302
    saved = settings_service.get_settings(app.extensions["quiz_db"])
    assert saved["duration_minutes"] == 20 and saved["length_options"] == [5, 10, 25]
    assert saved["marks_correct"] == 2.0 and saved["marks_incorrect"] == 0.5 and saved["penalize_unanswered"] is True
    assert settings_service.compute_duration_seconds(saved, 5) == 600
    page = admin_client.get("/quiz/setup").get_data(as_text=True)
    assert 'id="count-25"' in page and 'id="count-15"' not in page


def test_checkboxes_off_disable_penalties(admin_client, app):
    post(admin_client, "/admin/settings", settings_form(negative_marking_enabled=None, penalize_unanswered=None))
    saved = settings_service.get_settings(app.extensions["quiz_db"])
    assert saved["negative_marking_enabled"] is False
    assert settings_service.scoring_from_settings(saved)["marks_incorrect"] == 0.0


@pytest.mark.parametrize(
    "override,field",
    [
        ({"duration_minutes": "0"}, "duration_minutes"), ({"duration_minutes": "500"}, "duration_minutes"),
        ({"duration_minutes": "ten"}, "duration_minutes"), ({"marks_correct": "0"}, "marks_correct"),
        ({"marks_correct": "1.234"}, "marks_correct"), ({"marks_incorrect": "-1"}, "marks_incorrect"),
        ({"marks_incorrect": "nan"}, "marks_incorrect"), ({"length_options": "5, x"}, "length_options"),
        ({"length_options": ""}, "length_options"), ({"default_question_count": "7"}, "default_question_count"),
        ({"length_options": "0, 5"}, "length_options"),
    ],
)
def test_invalid_settings_are_rejected(admin_client, app, override, field):
    response = post(admin_client, "/admin/settings", settings_form(**override))
    assert response.status_code == 422 and "is-invalid" in response.get_data(as_text=True)
    assert settings_service.get_settings(app.extensions["quiz_db"])["duration_minutes"] == 10


def test_validate_settings_reports_field_names():
    _, errors = validate_settings({"duration_minutes": "x"})
    assert "duration_minutes" in errors


def test_corrupt_settings_fall_back_to_defaults(db):
    db.settings.write({"duration_minutes": -5, "marks_correct": "lots", "length_options": [5, 10]})
    s = settings_service.get_settings(db)
    assert s["duration_minutes"] == 10 and s["marks_correct"] == 4.0 and s["length_options"] == [5, 10]


def test_admin_can_remove_a_result(admin_client, app):
    db = app.extensions["quiz_db"]
    db.results.write({"version": 1, "results": [{
        "id": "r1", "participant_name": "Zed", "score": 4, "max_score": 20, "accuracy": 20.0, "category": "X", "difficulty": "any",
        "total_questions": 5, "correct": 1, "time_taken_seconds": 5, "submitted_at": "2026-01-01T00:00:00+00:00"}]})
    assert "Zed" in admin_client.get("/admin/results").get_data(as_text=True)
    assert post(admin_client, "/admin/results/r1/delete", {}).status_code == 302
    assert db.results.read()["results"] == []
