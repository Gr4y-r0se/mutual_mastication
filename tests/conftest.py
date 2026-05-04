"""Shared pytest fixtures and helper functions for The Meat Ensemble test suite.

Database strategy
-----------------
The app uses a module-level ``database.DATABASE`` path that ``get_db()`` reads
at call time.  Each ``app`` fixture monkeypatches that variable to a fresh
temp-file database, so tests are fully isolated without touching the real DB.

CSRF
----
``WTF_CSRF_ENABLED`` is set to ``False`` on the test app after construction;
Flask-WTF reads it at request time, so POST/DELETE requests need no token.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

import database as _db_mod  # imported early so monkeypatch can target the attribute

DEFAULT_PASSWORD = "password1234"


# ── Core fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Flask app wired to a throw-away SQLite file; CSRF disabled."""
    monkeypatch.setattr(_db_mod, "DATABASE", str(tmp_path / "test.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-for-prod")

    # Import after patching so the module-level ``app = create_app()`` in
    # app.py also uses the temp database on first import.
    from app import create_app

    flask_app = create_app()
    flask_app.config.update({"TESTING": True, "WTF_CSRF_ENABLED": False})
    yield flask_app


@pytest.fixture()
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


# ── Database helpers ───────────────────────────────────────────────────────────


def make_user(
    app,
    username="member",
    email="member@example.com",
    password=DEFAULT_PASSWORD,
    is_admin=0,
) -> dict:
    """Insert a user directly into the test DB; returns a dict including ``id``."""
    with app.app_context():
        db = _db_mod.get_db()
        db.execute(
            "INSERT INTO users (username, email, password_hash, is_admin)"
            " VALUES (?, ?, ?, ?)",
            (username, email, generate_password_hash(password), is_admin),
        )
        db.commit()
        uid = db.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()["id"]
    return {
        "id": uid,
        "username": username,
        "email": email,
        "password": password,
        "is_admin": is_admin,
    }


def make_poll(
    app,
    created_by: int,
    title: str = "Dinner poll",
    poll_type: str = "restaurant",
    vote_mode: str = "single",
    options: tuple = ("Hawksmoor", "Gaucho"),
    status: str = "open",
) -> int:
    """Insert a poll with options; returns the poll id."""
    with app.app_context():
        db = _db_mod.get_db()
        cursor = db.execute(
            "INSERT INTO polls (title, poll_type, vote_mode, created_by, status)"
            " VALUES (?, ?, ?, ?, ?)",
            (title, poll_type, vote_mode, created_by, status),
        )
        poll_id = cursor.lastrowid
        for label in options:
            db.execute(
                "INSERT INTO poll_options (poll_id, label) VALUES (?, ?)",
                (poll_id, label),
            )
        db.commit()
    return poll_id


def get_option_ids(app, poll_id: int) -> list[int]:
    """Return ordered list of option IDs for a poll."""
    with app.app_context():
        rows = (
            _db_mod.get_db()
            .execute(
                "SELECT id FROM poll_options WHERE poll_id = ? ORDER BY id", (poll_id,)
            )
            .fetchall()
        )
    return [r["id"] for r in rows]


def get_db_value(app, sql: str, params: tuple = ()):
    """Run a single-row SELECT and return the row (or None) outside any request."""
    with app.app_context():
        return _db_mod.get_db().execute(sql, params).fetchone()


# ── Request helpers ────────────────────────────────────────────────────────────


def login(client, username: str, password: str = DEFAULT_PASSWORD):
    """POST to /login and follow the redirect."""
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def text(resp) -> str:
    """Decode a test-client response to a lowercase string for easy assertions."""
    return resp.get_data(as_text=True).lower()
