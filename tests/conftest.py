import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["SECRET_KEY"] = "test-secret-key"

from backend.app import app


class FakeRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = many or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many

    def close(self):
        return None


class FakeConnection:
    def execute(self, query, params=None):
        normalized = " ".join(query.lower().split())

        if "select count(*) as count from users" in normalized:
            return FakeCursor(one=FakeRow({"count": 1}))
        if "select count(*)" in normalized:
            return FakeCursor(one=FakeRow({"count": 0}))
        if "select sum(amount) as total" in normalized:
            return FakeCursor(one=FakeRow({"total": 0}))
        if "select * from users where id" in normalized:
            return FakeCursor(
                one=FakeRow(
                    {
                        "id": 1,
                        "username": "testuser",
                        "email": "test@test.com",
                        "created_at": datetime(2024, 1, 1, 9, 0, 0),
                    }
                )
            )
        if "select * from users where email" in normalized:
            return FakeCursor(one=None)
        if "select id from users where email" in normalized:
            return FakeCursor(one=None)
        if "select id from user_settings" in normalized:
            return FakeCursor(one=FakeRow({"id": 1}))
        if "select * from user_settings where user_id" in normalized:
            return FakeCursor(
                one=FakeRow(
                    {
                        "user_id": 1,
                        "currency": "₹",
                        "theme": "dark",
                        "language": "en",
                        "font_size": "medium",
                    }
                )
            )
        if "select distinct category" in normalized:
            return FakeCursor(many=[])
        if "select * from expenses where id" in normalized:
            return FakeCursor(one=None)
        if "select receipt_path from expenses" in normalized:
            return FakeCursor(one=None)
        if "select active from recurring_expenses" in normalized:
            return FakeCursor(one=None)
        if "select active from reminders" in normalized:
            return FakeCursor(one=None)
        if "returning id" in normalized:
            return FakeCursor(one=FakeRow({"id": 1}))
        return FakeCursor(one=None, many=[])

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


@pytest.fixture(autouse=True)
def mock_app_db(monkeypatch):
    fake_connection = FakeConnection()
    monkeypatch.setattr("backend.app.get_db_connection", lambda: fake_connection)
    monkeypatch.setattr(
        "backend.app.get_user_settings",
        lambda user_id: {
            "currency": "₹",
            "theme": "dark",
            "language": "en",
            "font_size": "medium",
        },
    )
    return fake_connection


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def authenticated_client(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "testuser"
    yield client
