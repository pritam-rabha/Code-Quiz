"""Administrator routes: login, dashboard, question management, settings, results."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from .. import web
from ..constants import DIFFICULTIES, MAX_OPTIONS
from ..security import admin_required, is_admin, is_safe_redirect
from ..services import auth_service, leaderboard_service, question_service, settings_service, stats_service
from ..validators import clean_filter, is_valid_id, validate_question, validate_settings

bp = Blueprint("admin", __name__, url_prefix="/admin")
PER_PAGE = 15


# --------------------------------------------------------------- authentication
@bp.route("/login", methods=["GET", "POST"])
def login():
    db = web.get_db()
    config = current_app.config
    if is_admin():
        return redirect(url_for("admin.dashboard"))
    configured = auth_service.admin_configured(db, config)
    next_url = request.values.get("next", "")
    next_url = next_url if is_safe_redirect(next_url) else ""

    if request.method == "POST":
        now = web.current_time()
        throttle = current_app.extensions["login_throttle"]
        key = request.remote_addr or "unknown"
        wait = throttle.retry_after(key, now)
        if wait:
            flash(f"Too many failed sign-in attempts. Try again in {max(1, wait // 60 + 1)} minute(s).", "danger")
            return render_template("admin/login.html", configured=configured, next_url=next_url), 429
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if auth_service.verify_credentials(db, config, username, password):
            throttle.reset(key)
            session.clear()  # new session on privilege change
            session["is_admin"] = True
            session["admin_user"] = username.strip()
            session["admin_login_at"] = now
            flash("Signed in.", "success")
            return redirect(next_url or url_for("admin.dashboard"))
        throttle.record_failure(key, now)
        flash("Incorrect username or password.", "danger")
        return render_template("admin/login.html", configured=configured, next_url=next_url), 401
    return render_template("admin/login.html", configured=configured, next_url=next_url)


@bp.post("/logout")
def logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("admin.login"))


# -------------------------------------------------------------------- dashboard
@bp.get("/")
@admin_required
def dashboard():
    db = web.get_db()
    return render_template(
        "admin/dashboard.html",
        stats=stats_service.dashboard_stats(db),
        settings=settings_service.get_settings(db),
        data_dir=str(db.data_dir),
    )


# -------------------------------------------------------------------- questions
def _form_to_question(form) -> dict:
    return {
        "category": form.get("category", ""),
        "difficulty": form.get("difficulty", ""),
        "text": form.get("text", ""),
        "options": [form.get(f"option_{i}", "") for i in range(MAX_OPTIONS)],
        "correct_index": form.get("correct_index", ""),
        "explanation": form.get("explanation", ""),
    }


def _form_view(raw: dict) -> dict:
    options = list(raw.get("options", []))
    options += [""] * (MAX_OPTIONS - len(options))
    last = max((i for i, o in enumerate(options) if str(o).strip()), default=-1)
    try:
        correct = int(raw.get("correct_index", ""))
    except (TypeError, ValueError):
        correct = None
    return {
        "category": raw.get("category", ""),
        "difficulty": raw.get("difficulty", "easy"),
        "text": raw.get("text", ""),
        "options": options[:MAX_OPTIONS],
        "correct_index": correct,
        "explanation": raw.get("explanation", ""),
        "rows": min(MAX_OPTIONS, max(4, last + 1)),
    }


@bp.get("/questions")
@admin_required
def questions():
    db = web.get_db()
    everything = question_service.list_questions(db)
    names = question_service.category_names(everything)
    search = request.args.get("q", "").strip()[:100]
    category = clean_filter(request.args.get("category"), names)
    difficulty = clean_filter(request.args.get("difficulty"), [*DIFFICULTIES])
    matches = question_service.filter_questions(everything, category, difficulty, search)
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    pages = max(1, -(-len(matches) // PER_PAGE))
    page = min(page, pages)
    return render_template(
        "admin/questions.html",
        questions=matches[(page - 1) * PER_PAGE : page * PER_PAGE],
        total=len(matches),
        all_total=len(everything),
        page=page,
        pages=pages,
        categories=names,
        difficulties=DIFFICULTIES,
        selected={"q": search, "category": category or "", "difficulty": difficulty or ""},
    )


def _render_form(raw, errors, *, question=None, status=200):
    names = question_service.category_names(question_service.list_questions(web.get_db()))
    return (
        render_template(
            "admin/question_form.html",
            form=_form_view(raw),
            errors=errors,
            question=question,
            categories=names,
            difficulties=DIFFICULTIES,
            max_options=MAX_OPTIONS,
        ),
        status,
    )


@bp.route("/questions/new", methods=["GET", "POST"])
@admin_required
def question_new():
    if request.method == "GET":
        return _render_form({"difficulty": "easy", "correct_index": 0}, {})
    raw = _form_to_question(request.form)
    cleaned, errors = validate_question(raw)
    if not errors and question_service.find_duplicate(
        question_service.list_questions(web.get_db()), cleaned["text"], cleaned["category"]
    ):
        errors["text"] = "A question with the same text already exists in this category."
    if errors:
        return _render_form(raw, errors, status=422)
    question_service.create_question(web.get_db(), cleaned)
    flash("Question added.", "success")
    return redirect(url_for("admin.questions"))


@bp.route("/questions/<question_id>/edit", methods=["GET", "POST"])
@admin_required
def question_edit(question_id):
    if not is_valid_id(question_id):
        abort(404)
    db = web.get_db()
    try:
        current = question_service.get_question(db, question_id)
    except question_service.NotFoundError:
        abort(404)
    if request.method == "GET":
        return _render_form(current, {}, question=current)
    raw = _form_to_question(request.form)
    cleaned, errors = validate_question(raw)
    if not errors and question_service.find_duplicate(
        question_service.list_questions(db), cleaned["text"], cleaned["category"], exclude_id=question_id
    ):
        errors["text"] = "A question with the same text already exists in this category."
    if errors:
        return _render_form(raw, errors, question=current, status=422)
    try:
        question_service.update_question(db, question_id, cleaned)
    except question_service.NotFoundError:
        abort(404)
    flash("Question updated.", "success")
    return redirect(url_for("admin.questions"))


@bp.post("/questions/<question_id>/delete")
@admin_required
def question_delete(question_id):
    if not is_valid_id(question_id):
        abort(404)
    try:
        question_service.delete_question(web.get_db(), question_id)
    except question_service.NotFoundError:
        abort(404)
    flash("Question deleted.", "success")
    return redirect(url_for("admin.questions"))


# --------------------------------------------------------------------- settings
@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    db = web.get_db()
    if request.method == "POST":
        cleaned, errors = validate_settings(request.form)
        if errors:
            current = settings_service.get_settings(db)
            current.update(cleaned)
            return render_template("admin/settings.html", settings=current, form=request.form, errors=errors), 422
        settings_service.save_settings(db, cleaned)
        flash("Quiz settings saved.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", settings=settings_service.get_settings(db), form=None, errors={})


# ---------------------------------------------------------------------- results
@bp.get("/results")
@admin_required
def results():
    db = web.get_db()
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    board = leaderboard_service.get_leaderboard(db, page=page, per_page=PER_PAGE)
    return render_template("admin/results.html", board=board)


@bp.post("/results/<result_id>/delete")
@admin_required
def result_delete(result_id):
    if not is_valid_id(result_id):
        abort(404)
    if leaderboard_service.delete_result(web.get_db(), result_id):
        flash("Result removed from the leaderboard.", "success")
    else:
        flash("That result no longer exists.", "warning")
    return redirect(url_for("admin.results"))
