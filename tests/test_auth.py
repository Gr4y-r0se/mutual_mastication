"""Integration tests for authentication routes (/register, /login, /logout,
/profile, /forgot-password, /reset-password, /change-password).
"""

from __future__ import annotations

import time

import pytest

import database as _db_mod
from tests.conftest import DEFAULT_PASSWORD, get_db_value, login, make_user, text

# ── /register ──────────────────────────────────────────────────────────────────


class TestRegister:
    def test_first_admin_created_successfully(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "alice",
                "email": "alice@example.com",
                "password": DEFAULT_PASSWORD,
                "confirm_password": DEFAULT_PASSWORD,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "log in" in text(resp)

    def test_blocked_when_users_already_exist(self, client, app):
        make_user(app)
        resp = client.post(
            "/register",
            data={
                "username": "bob",
                "email": "bob@example.com",
                "password": DEFAULT_PASSWORD,
                "confirm_password": DEFAULT_PASSWORD,
            },
            follow_redirects=True,
        )
        assert "invitation only" in text(resp)

    def test_password_too_short(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "alice",
                "email": "alice@example.com",
                "password": "short",
                "confirm_password": "short",
            },
            follow_redirects=True,
        )
        assert "10" in text(resp)

    def test_password_mismatch(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "alice",
                "email": "alice@example.com",
                "password": DEFAULT_PASSWORD,
                "confirm_password": DEFAULT_PASSWORD + "x",
            },
            follow_redirects=True,
        )
        assert "do not match" in text(resp)

    def test_invalid_username_rejected(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "a!",
                "email": "alice@example.com",
                "password": DEFAULT_PASSWORD,
                "confirm_password": DEFAULT_PASSWORD,
            },
            follow_redirects=True,
        )
        assert "username" in text(resp)

    def test_duplicate_username_rejected(self, client, app):
        # First registration succeeds
        client.post(
            "/register",
            data={
                "username": "alice",
                "email": "alice@example.com",
                "password": DEFAULT_PASSWORD,
                "confirm_password": DEFAULT_PASSWORD,
            },
        )
        # Subsequent registration is blocked (users already exist)
        resp = client.post(
            "/register",
            data={
                "username": "alice",
                "email": "other@example.com",
                "password": DEFAULT_PASSWORD,
                "confirm_password": DEFAULT_PASSWORD,
            },
            follow_redirects=True,
        )
        assert "invitation only" in text(resp)


# ── /login ─────────────────────────────────────────────────────────────────────


class TestLogin:
    def test_valid_credentials_succeed(self, client, app):
        make_user(app, username="alice", email="alice@example.com")
        resp = login(client, "alice")
        assert "welcome" in text(resp)

    def test_wrong_password_rejected(self, client, app):
        make_user(app, username="alice")
        resp = client.post(
            "/login",
            data={"username": "alice", "password": "badpassword"},
            follow_redirects=True,
        )
        assert "invalid" in text(resp)

    def test_unknown_username_shows_same_error(self, client):
        resp = client.post(
            "/login",
            data={"username": "nobody", "password": DEFAULT_PASSWORD},
            follow_redirects=True,
        )
        assert "invalid" in text(resp)

    def test_session_set_on_success(self, client, app):
        make_user(app, username="alice")
        with client:
            login(client, "alice")
            from flask import session

            assert "user_id" in session

    def test_next_param_honoured_for_relative_path(self, client, app):
        make_user(app, username="alice")
        resp = client.post(
            "/login?next=/profile",
            data={"username": "alice", "password": DEFAULT_PASSWORD},
        )
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_open_redirect_blocked(self, client, app):
        make_user(app, username="alice")
        resp = client.post(
            "/login?next=//evil.com",
            data={"username": "alice", "password": DEFAULT_PASSWORD},
        )
        location = resp.headers.get("Location", "")
        assert "evil.com" not in location

    def test_backslash_redirect_blocked(self, client, app):
        make_user(app, username="alice")
        resp = client.post(
            r"/login?next=\evil.com",
            data={"username": "alice", "password": DEFAULT_PASSWORD},
        )
        location = resp.headers.get("Location", "")
        assert "evil.com" not in location

    def test_account_locked_after_max_failures(self, client, app):
        make_user(app, username="alice")
        for _ in range(5):
            client.post("/login", data={"username": "alice", "password": "wrong"})
        resp = client.post(
            "/login",
            data={"username": "alice", "password": "wrong"},
            follow_redirects=True,
        )
        assert "locked" in text(resp)

    def test_locked_account_rejects_correct_password(self, client, app):
        u = make_user(app, username="alice")
        with app.app_context():
            _db_mod.get_db().execute(
                "UPDATE users SET locked_until = ? WHERE id = ?",
                (int(time.time()) + 3600, u["id"]),
            )
            _db_mod.get_db().commit()
        resp = login(client, "alice")
        assert "locked" in text(resp)

    def test_failed_attempts_reset_on_success(self, client, app):
        u = make_user(app, username="alice")
        # Two failed attempts
        client.post("/login", data={"username": "alice", "password": "bad"})
        client.post("/login", data={"username": "alice", "password": "bad"})
        login(client, "alice")
        row = get_db_value(
            app, "SELECT failed_attempts FROM users WHERE id = ?", (u["id"],)
        )
        assert row["failed_attempts"] == 0


# ── /logout ────────────────────────────────────────────────────────────────────


class TestLogout:
    def test_clears_session(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        with client:
            client.post("/logout")
            from flask import session

            assert "user_id" not in session

    def test_redirects_after_logout(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.post("/logout")
        assert resp.status_code == 302

    def test_get_not_allowed(self, client):
        resp = client.get("/logout")
        assert resp.status_code == 405


# ── /profile ───────────────────────────────────────────────────────────────────


class TestProfile:
    def test_redirects_when_not_logged_in(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_shows_username(self, client, app):
        make_user(app, username="alice", email="alice@example.com")
        login(client, "alice")
        resp = client.get("/profile")
        assert "alice" in text(resp)

    def test_shows_email(self, client, app):
        make_user(app, username="alice", email="alice@example.com")
        login(client, "alice")
        resp = client.get("/profile")
        assert "alice@example.com" in text(resp)


# ── /forgot-password ───────────────────────────────────────────────────────────


class TestForgotPassword:
    def test_unknown_email_shows_same_message(self, client):
        resp = client.post(
            "/forgot-password",
            data={"email": "nobody@example.com"},
            follow_redirects=True,
        )
        # Must not reveal whether the email exists
        assert "if that email" in text(resp) or "link has been sent" in text(resp)

    def test_known_email_creates_reset_token(self, client, app, monkeypatch):
        monkeypatch.setattr("email_service.send_password_reset", lambda *a, **kw: True)
        make_user(app, username="alice", email="alice@example.com")
        client.post("/forgot-password", data={"email": "alice@example.com"})
        row = get_db_value(app, "SELECT COUNT(*) AS n FROM password_reset_tokens")
        assert row["n"] == 1

    def test_known_email_calls_send_password_reset(self, client, app, monkeypatch):
        called_with = {}

        def fake_send(email, url):
            called_with["email"] = email
            called_with["url"] = url
            return True

        monkeypatch.setattr("email_service.send_password_reset", fake_send)
        make_user(app, username="alice", email="alice@example.com")
        client.post("/forgot-password", data={"email": "alice@example.com"})
        assert called_with.get("email") == "alice@example.com"
        assert "reset-password" in called_with.get("url", "")

    def test_second_request_replaces_token(self, client, app, monkeypatch):
        monkeypatch.setattr("email_service.send_password_reset", lambda *a, **kw: True)
        make_user(app, username="alice", email="alice@example.com")
        client.post("/forgot-password", data={"email": "alice@example.com"})
        client.post("/forgot-password", data={"email": "alice@example.com"})
        row = get_db_value(app, "SELECT COUNT(*) AS n FROM password_reset_tokens")
        assert row["n"] == 1  # old one deleted, new one inserted


# ── /reset-password ────────────────────────────────────────────────────────────


class TestResetPassword:
    def _insert_token(self, app, user_id, token="valid-token-abc", hours=1):
        with app.app_context():
            db = _db_mod.get_db()
            db.execute(
                "INSERT INTO password_reset_tokens (user_id, token, expires_at)"
                " VALUES (?, ?, ?)",
                (user_id, token, int(time.time()) + hours * 3600),
            )
            db.commit()

    def test_invalid_token_redirects(self, client):
        resp = client.get("/reset-password/totally-invalid")
        assert resp.status_code == 302

    def test_expired_token_redirects(self, client, app):
        u = make_user(app, username="alice")
        with app.app_context():
            _db_mod.get_db().execute(
                "INSERT INTO password_reset_tokens (user_id, token, expires_at)"
                " VALUES (?, 'expired-tok', ?)",
                (u["id"], int(time.time()) - 1),
            )
            _db_mod.get_db().commit()
        resp = client.get("/reset-password/expired-tok")
        assert resp.status_code == 302

    def test_valid_token_shows_form(self, client, app):
        u = make_user(app, username="alice")
        self._insert_token(app, u["id"])
        resp = client.get("/reset-password/valid-token-abc")
        assert resp.status_code == 200

    def test_valid_token_changes_password(self, client, app):
        u = make_user(app, username="alice")
        self._insert_token(app, u["id"])
        new_pw = "newpassword999"
        client.post(
            "/reset-password/valid-token-abc",
            data={"password": new_pw, "confirm_password": new_pw},
        )
        resp = client.post(
            "/login",
            data={"username": "alice", "password": new_pw},
            follow_redirects=True,
        )
        assert "welcome" in text(resp)

    def test_token_marked_used_after_reset(self, client, app):
        u = make_user(app, username="alice")
        self._insert_token(app, u["id"])
        new_pw = "newpassword999"
        client.post(
            "/reset-password/valid-token-abc",
            data={"password": new_pw, "confirm_password": new_pw},
        )
        row = get_db_value(
            app,
            "SELECT used FROM password_reset_tokens WHERE token = 'valid-token-abc'",
        )
        assert row["used"] == 1

    def test_used_token_cannot_be_reused(self, client, app):
        u = make_user(app, username="alice")
        self._insert_token(app, u["id"])
        new_pw = "newpassword999"
        client.post(
            "/reset-password/valid-token-abc",
            data={"password": new_pw, "confirm_password": new_pw},
        )
        resp = client.get("/reset-password/valid-token-abc")
        assert resp.status_code == 302  # token now used → redirect

    def test_password_mismatch_shows_error(self, client, app):
        u = make_user(app, username="alice")
        self._insert_token(app, u["id"])
        resp = client.post(
            "/reset-password/valid-token-abc",
            data={
                "password": "newpassword999",
                "confirm_password": "differentpassword",
            },
            follow_redirects=True,
        )
        assert "do not match" in text(resp)


# ── /change-password ───────────────────────────────────────────────────────────


class TestChangePassword:
    def test_redirects_when_not_logged_in(self, client):
        resp = client.get("/change-password")
        assert resp.status_code == 302

    def test_wrong_current_password(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.post(
            "/change-password",
            data={
                "current_password": "wrongpassword",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=True,
        )
        assert "incorrect" in text(resp)

    def test_new_password_too_short(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.post(
            "/change-password",
            data={
                "current_password": DEFAULT_PASSWORD,
                "new_password": "short",
                "confirm_password": "short",
            },
            follow_redirects=True,
        )
        assert "10" in text(resp)

    def test_new_passwords_mismatch(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.post(
            "/change-password",
            data={
                "current_password": DEFAULT_PASSWORD,
                "new_password": "newpassword123",
                "confirm_password": "newpassword999",
            },
            follow_redirects=True,
        )
        assert "do not match" in text(resp)

    def test_successful_change(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        new_pw = "newpassword123"
        resp = client.post(
            "/change-password",
            data={
                "current_password": DEFAULT_PASSWORD,
                "new_password": new_pw,
                "confirm_password": new_pw,
            },
            follow_redirects=True,
        )
        assert "changed" in text(resp)

    def test_new_password_works_on_next_login(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        new_pw = "newpassword123"
        client.post(
            "/change-password",
            data={
                "current_password": DEFAULT_PASSWORD,
                "new_password": new_pw,
                "confirm_password": new_pw,
            },
        )
        client.post("/logout")
        resp = login(client, "alice", password=new_pw)
        assert "welcome" in text(resp)
