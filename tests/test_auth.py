import json

import pytest

from conftest import ADMIN_PASSWORD, ADMIN_USER, get_csrf
from quiz_app.services import auth_service
from quiz_app.security import is_safe_redirect


def login(client, username=ADMIN_USER, password=ADMIN_PASSWORD, **extra):
    token = get_csrf(client, "/admin/login")
    return client.post("/admin/login", data={"csrf_token": token, "username": username, "password": password, **extra})


def test_correct_credentials_open_the_dashboard(client):
    response = login(client)
    assert response.status_code == 302 and response.headers["Location"].endswith("/admin/")
    assert client.get("/admin/").status_code == 200


def test_wrong_password_is_rejected(client):
    assert login(client, password="wrong password!").status_code == 401
    assert client.get("/admin/").status_code == 302


def test_wrong_username_is_rejected(client):
    assert login(client, username="someone").status_code == 401


def test_admin_pages_redirect_anonymous_visitors(client):
    for path in ["/admin/", "/admin/questions", "/admin/questions/new", "/admin/settings", "/admin/results"]:
        response = client.get(path)
        assert response.status_code == 302 and "/admin/login" in response.headers["Location"], path


def test_anonymous_post_to_admin_is_refused(client):
    token = get_csrf(client, "/admin/login")
    response = client.post("/admin/questions/abc/delete", data={"csrf_token": token})
    assert response.status_code == 302 and "/admin/login" in response.headers["Location"]
    response = client.post("/admin/settings", data={"csrf_token": token})
    assert response.status_code == 302


def test_login_requires_csrf_token(client):
    response = client.post("/admin/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert response.status_code == 400


def test_logout_requires_post_and_csrf(admin_client):
    assert admin_client.get("/admin/logout").status_code == 405
    assert admin_client.post("/admin/logout").status_code == 400
    token = get_csrf(admin_client, "/admin/")
    assert admin_client.post("/admin/logout", data={"csrf_token": token}).status_code == 302
    assert admin_client.get("/admin/").status_code == 302


def test_lockout_after_repeated_failures(client, app):
    for _ in range(app.config["LOGIN_MAX_ATTEMPTS"]):
        assert login(client, password="nope nope nope").status_code == 401
    assert login(client).status_code == 429  # even the right password is refused while locked


def test_lockout_expires(client, app, monkeypatch):
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr("quiz_app.web.current_time", lambda: clock["t"])
    for _ in range(app.config["LOGIN_MAX_ATTEMPTS"]):
        login(client, password="bad bad bad bad")
    assert login(client).status_code == 429
    clock["t"] += app.config["LOGIN_LOCK_SECONDS"] + 1
    assert login(client).status_code == 302


def test_admin_session_expires(admin_client, app, monkeypatch):
    import time

    future = time.time() + app.config["ADMIN_SESSION_MINUTES"] * 60 + 60
    monkeypatch.setattr("quiz_app.web.current_time", lambda: future)
    assert admin_client.get("/admin/").status_code == 302


def test_login_redirects_only_to_local_paths(client):
    response = login(client, next="https://evil.example/steal")
    assert response.headers["Location"].endswith("/admin/")
    assert is_safe_redirect("/admin/questions") and not is_safe_redirect("//evil.example")
    assert not is_safe_redirect("https://evil.example") and not is_safe_redirect("/\\evil")


def test_session_cookie_flags(client):
    response = login(client)
    cookies = " ".join(response.headers.getlist("Set-Cookie"))
    assert "HttpOnly" in cookies and "SameSite=Lax" in cookies


def test_password_is_hashed_never_stored_in_plaintext(db):
    auth_service.create_admin(db, "teacher", "a long secret phrase")
    raw = db.admin.path.read_text(encoding="utf-8")
    stored = json.loads(raw)
    assert "a long secret phrase" not in raw
    assert stored["password_hash"] != "a long secret phrase" and stored["password_hash"].count("$") >= 2
    assert auth_service.verify_credentials(db, {}, "teacher", "a long secret phrase")
    assert not auth_service.verify_credentials(db, {}, "teacher", "A long secret phrase")


def test_environment_hash_takes_priority_over_stored_admin(db):
    auth_service.create_admin(db, "stored", "stored password 1")
    config = {"ADMIN_USERNAME": "envuser", "ADMIN_PASSWORD_HASH": auth_service.hash_password("env password 1234")}
    assert auth_service.verify_credentials(db, config, "envuser", "env password 1234")
    assert not auth_service.verify_credentials(db, config, "stored", "stored password 1")


def test_no_admin_configured_denies_everything(db):
    assert not auth_service.admin_configured(db, {})
    assert not auth_service.verify_credentials(db, {}, "admin", "anything at all")


def test_malformed_hash_in_config_denies_access(db):
    assert not auth_service.verify_credentials(db, {"ADMIN_PASSWORD_HASH": "not-a-hash"}, "admin", "x")


def test_weak_passwords_and_bad_usernames_are_rejected(db):
    with pytest.raises(ValueError):
        auth_service.hash_password("short")
    with pytest.raises(ValueError):
        auth_service.create_admin(db, "ab", "long enough password")


def test_login_page_explains_missing_configuration(tmp_path):
    from quiz_app import create_app

    app = create_app({"TESTING": True, "SECRET_KEY": "k" * 40, "DATA_DIR": str(tmp_path), "ADMIN_PASSWORD_HASH": ""})
    page = app.test_client().get("/admin/login").get_data(as_text=True)
    assert "No administrator account is configured" in page


def test_production_requires_a_strong_secret_key(monkeypatch, tmp_path):
    from config import ConfigError, build_config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ConfigError):
        build_config({"DATA_DIR": str(tmp_path)})
    with pytest.raises(ConfigError):
        build_config({"SECRET_KEY": "short"})
    assert build_config({"SECRET_KEY": "s" * 40})["SESSION_COOKIE_SECURE"] is True


def test_security_headers_present(client):
    headers = client.get("/").headers
    assert headers["X-Frame-Options"] == "DENY" and headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in headers["Content-Security-Policy"]
