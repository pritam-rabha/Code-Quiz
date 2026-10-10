import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quiz_app import create_app  # noqa: E402
from quiz_app.services import auth_service  # noqa: E402
from quiz_app.storage import Database  # noqa: E402

ADMIN_USER = "examiner"
ADMIN_PASSWORD = "correct horse battery staple"
SAMPLE = ROOT / "sample_data" / "questions.json"


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "data", SAMPLE)


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-123",
            "DATA_DIR": str(tmp_path / "app-data"),
            "ADMIN_USERNAME": ADMIN_USER,
            "ADMIN_PASSWORD_HASH": auth_service.hash_password(ADMIN_PASSWORD),
        }
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def get_csrf(client, path="/quiz/setup"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


@pytest.fixture
def csrf(client):
    return lambda path="/quiz/setup": get_csrf(client, path)


@pytest.fixture
def admin_client(app):
    client = app.test_client()
    token = get_csrf(client, "/admin/login")
    response = client.post(
        "/admin/login",
        data={"csrf_token": token, "username": ADMIN_USER, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 302
    return client
