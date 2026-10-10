"""Participant-facing routes: landing, setup, quiz, results, leaderboard."""
from __future__ import annotations

import math

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from .. import web
from ..constants import ANY_DIFFICULTY, DIFFICULTIES
from ..security import is_admin
from ..services import leaderboard_service, question_service, quiz_service, settings_service
from ..services.quiz_service import QuizError
from ..validators import clean_filter, is_valid_id, validate_quiz_request

bp = Blueprint("public", __name__)


# ------------------------------------------------------------------- helpers
def _remember_result(result_id: str) -> None:
    ids = [i for i in session.get("result_ids", []) if isinstance(i, str)]
    ids.append(result_id)
    session["result_ids"] = ids[-25:]


def _current_attempt():
    """Return ``(attempt, finished_result)`` for this browser session.

    If the quiz ran past its deadline (plus grace) it is closed on the server
    with the answers saved in time and the finished result is returned instead.
    """
    attempt_id = session.get("attempt_id")
    if not attempt_id or not is_valid_id(attempt_id):
        session.pop("attempt_id", None)
        return None, None
    db, now = web.get_db(), web.current_time()
    result = quiz_service.finalize_expired(db, attempt_id, now=now, grace=web.grace_seconds())
    if result:
        session.pop("attempt_id", None)
        _remember_result(result["id"])
        return None, result
    attempt = quiz_service.get_attempt(db, attempt_id)
    if attempt is None or attempt["participant_id"] != session.get("participant_id"):
        session.pop("attempt_id", None)
        return None, None
    return attempt, None


def _json_error(message: str, code: str, status: int, **extra):
    return jsonify(ok=False, error=message, code=code, **extra), status


def _setup_context(form: dict, errors: dict | None = None):
    db = web.get_db()
    settings = settings_service.get_settings(db)
    questions = question_service.list_questions(db)
    return {
        "settings": settings,
        "categories": question_service.category_summary(questions),
        "availability": question_service.availability(questions),
        "form": form,
        "errors": errors or {},
        "durations": {n: settings_service.compute_duration_seconds(settings, n) for n in settings["length_options"]},
        "difficulties": DIFFICULTIES,
    }


# -------------------------------------------------------------------- pages
@bp.get("/")
def index():
    db = web.get_db()
    settings = settings_service.get_settings(db)
    questions = question_service.list_questions(db)
    attempt, _ = _current_attempt()
    return render_template(
        "index.html",
        settings=settings,
        categories=question_service.category_summary(questions),
        total=len(questions),
        active_attempt=attempt,
        duration_seconds=settings_service.compute_duration_seconds(settings, settings["default_question_count"]),
    )


@bp.get("/health")
def health():
    return jsonify(status="ok")


@bp.get("/quiz/setup")
def setup():
    attempt, result = _current_attempt()
    if result:
        flash("Your previous quiz ran out of time and was submitted automatically.", "warning")
        return redirect(url_for("public.result", result_id=result["id"]))
    names = question_service.category_names(question_service.list_questions(web.get_db()))
    category = clean_filter(request.args.get("category"), names) or ""
    settings = settings_service.get_settings(web.get_db())
    form = {
        "name": session.get("participant_name", ""),
        "category": category,
        "difficulty": ANY_DIFFICULTY,
        "count": str(settings["default_question_count"]),
    }
    context = _setup_context(form)
    context["active_attempt"] = attempt
    return render_template("setup.html", **context)


@bp.post("/quiz/start")
def start():
    db = web.get_db()
    settings = settings_service.get_settings(db)
    names = question_service.category_names(question_service.list_questions(db))
    cleaned, errors = validate_quiz_request(request.form, settings, names)

    existing, finished = _current_attempt()
    if finished:
        flash("Your previous quiz ran out of time and was submitted automatically.", "warning")
        return redirect(url_for("public.result", result_id=finished["id"]))
    if existing:
        flash("You already have a quiz in progress. Finish it before starting a new one.", "warning")
        return redirect(url_for("public.quiz"))

    if not errors:
        try:
            attempt = quiz_service.start_attempt(
                db,
                participant_id=session.get("participant_id"),
                name=cleaned["name"],
                category=cleaned["category"],
                difficulty=cleaned["difficulty"],
                count=cleaned["count"],
                settings=settings,
                now=web.current_time(),
                stale_seconds=int(current_app.config["STALE_ATTEMPT_SECONDS"]),
            )
        except QuizError as exc:
            errors["category"] = exc.message
        else:
            session["participant_id"] = attempt["participant_id"]
            session["participant_name"] = cleaned["name"]
            session["attempt_id"] = attempt["id"]
            if attempt["notice"]:
                flash(attempt["notice"], "info")
            return redirect(url_for("public.quiz"))

    form = {
        "name": cleaned.get("name", ""),
        "category": cleaned.get("category") or "",
        "difficulty": cleaned.get("difficulty") or ANY_DIFFICULTY,
        "count": str(cleaned.get("count") or request.form.get("count", "")),
    }
    return render_template("setup.html", **_setup_context(form, errors), active_attempt=None), 422


@bp.get("/quiz")
def quiz():
    attempt, result = _current_attempt()
    if result:
        flash("Time ran out. Your answers were submitted automatically.", "warning")
        return redirect(url_for("public.result", result_id=result["id"]))
    if attempt is None:
        flash("Start a new quiz to begin.", "info")
        return redirect(url_for("public.setup"))
    view = quiz_service.public_view(attempt, web.current_time())
    return render_template(
        "quiz.html",
        quiz=view,
        quiz_config={
            **view,
            "urls": {"answer": url_for("public.save_answer"), "submit": url_for("public.submit")},
        },
    )


@bp.post("/quiz/answer")
def save_answer():
    payload = request.get_json(silent=True)
    attempt_id = session.get("attempt_id")
    if not isinstance(payload, dict):
        return _json_error("Invalid request.", "invalid_payload", 400)
    if not attempt_id:
        return _json_error("No quiz is in progress.", "not_active", 409, redirect=url_for("public.setup"))
    db, now = web.get_db(), web.current_time()
    try:
        remaining = quiz_service.record_answer(
            db, attempt_id, payload.get("question_id"), payload.get("option_index"),
            now=now, grace=web.grace_seconds(),
        )
    except QuizError as exc:
        extra = {}
        if exc.code == "expired":
            result = quiz_service.finalize_expired(db, attempt_id, now=now, grace=web.grace_seconds())
            if result:
                session.pop("attempt_id", None)
                _remember_result(result["id"])
                extra["redirect"] = url_for("public.result", result_id=result["id"])
        return _json_error(exc.message, exc.code, exc.status, **extra)
    return jsonify(ok=True, remaining_seconds=int(math.ceil(remaining)))


@bp.post("/quiz/submit")
def submit():
    payload = request.get_json(silent=True)
    attempt_id = session.get("attempt_id")
    if not isinstance(payload, dict):
        return _json_error("Invalid request.", "invalid_payload", 400)
    if not attempt_id or not is_valid_id(attempt_id):
        return _json_error("No quiz is in progress.", "not_active", 409, redirect=url_for("public.setup"))
    try:
        result, _created = quiz_service.submit_attempt(
            web.get_db(), attempt_id, payload.get("answers"),
            now=web.current_time(), grace=web.grace_seconds(),
        )
    except QuizError as exc:
        return _json_error(exc.message, exc.code, exc.status)
    session.pop("attempt_id", None)
    _remember_result(result["id"])
    return jsonify(ok=True, redirect=url_for("public.result", result_id=result["id"]))


@bp.get("/results/<result_id>")
def result(result_id):
    if not is_valid_id(result_id):
        abort(404)
    db = web.get_db()
    found = leaderboard_service.get_result(db, result_id)
    owner = found and (
        result_id in session.get("result_ids", [])
        or found.get("participant_id") == session.get("participant_id")
        or is_admin()
    )
    if not owner:
        abort(404)  # 404 rather than 403 so result ids cannot be probed
    rank, total = leaderboard_service.rank_of(db, found)
    return render_template("result.html", result=found, rank=rank, rank_total=total)


@bp.get("/leaderboard")
def leaderboard():
    db = web.get_db()
    names = question_service.category_names(question_service.list_questions(db))
    # Results keep their own category label, so also allow categories that only exist in results.
    result_cats = {r.get("category") for r in db.results.read()["results"] if isinstance(r, dict)}
    all_names = sorted({*names, *(c for c in result_cats if isinstance(c, str))}, key=str.lower)
    category = clean_filter(request.args.get("category"), all_names)
    difficulty = clean_filter(request.args.get("difficulty"), [*DIFFICULTIES])
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    board = leaderboard_service.get_leaderboard(db, category, difficulty, page)
    return render_template(
        "leaderboard.html",
        board=board,
        categories=all_names,
        difficulties=DIFFICULTIES,
        selected={"category": category or "", "difficulty": difficulty or ""},
        mine=set(session.get("result_ids", [])),
    )
