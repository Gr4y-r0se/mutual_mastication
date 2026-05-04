"""Integration tests for admin routes."""
from __future__ import annotations

import database as _db_mod
import pytest
from tests.conftest import DEFAULT_PASSWORD, get_db_value, login, make_poll, make_user, text


def _get_uid(app, username):
    row = get_db_value(app, "SELECT id FROM users WHERE username = ?", (username,))
    return row["id"]


# ── /admin (dashboard) ─────────────────────────────────────────────────────────

class TestDashboard:
    def test_unauthenticated_redirected(self, client):
        resp = client.get("/admin")
        assert resp.status_code == 302

    def test_member_gets_403(self, client, app):
        make_user(app, username="member")
        login(client, "member")
        resp = client.get("/admin")
        assert resp.status_code == 403

    def test_admin_can_access(self, client, app):
        make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        assert client.get("/admin").status_code == 200

    def test_shows_all_members(self, client, app):
        make_user(app, username="admin", is_admin=1)
        make_user(app, username="bob", email="bob@example.com")
        login(client, "admin")
        assert "bob" in text(client.get("/admin"))

    def test_shows_polls(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        make_poll(app, u["id"], title="November dinner")
        assert "november dinner" in text(client.get("/admin"))


# ── /admin/poll/new ────────────────────────────────────────────────────────────

class TestNewPoll:
    def _login_admin(self, client, app):
        make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        return _get_uid(app, "admin")

    def _add_restaurant(self, app, uid, name="Hawksmoor", status="approved"):
        with app.app_context():
            db = _db_mod.get_db()
            cursor = db.execute(
                "INSERT INTO restaurants (name, cuisine, suggested_by, status)"
                " VALUES (?, 'Steakhouse', ?, ?)",
                (name, uid, status),
            )
            rid = cursor.lastrowid
            db.commit()
        return rid

    def test_create_date_poll(self, client, app, monkeypatch):
        monkeypatch.setattr("email_service.send_poll_created", lambda *a, **kw: True)
        uid = self._login_admin(client, app)
        resp = client.post("/admin/poll/new", data={
            "title": "When to meet",
            "description": "",
            "poll_type": "date",
            "vote_mode": "approval",
            "options": "2025-11-15\n2025-11-22",
        }, follow_redirects=True)
        assert resp.status_code == 200
        row = get_db_value(app, "SELECT COUNT(*) AS n FROM polls WHERE title = 'When to meet'")
        assert row["n"] == 1

    def test_create_restaurant_poll(self, client, app, monkeypatch):
        monkeypatch.setattr("email_service.send_poll_created", lambda *a, **kw: True)
        uid = self._login_admin(client, app)
        rid = self._add_restaurant(app, uid)
        resp = client.post("/admin/poll/new", data={
            "title": "Where to eat",
            "description": "",
            "poll_type": "restaurant",
            "vote_mode": "single",
            "restaurant_ids": [rid],
        }, follow_redirects=True)
        assert resp.status_code == 200
        row = get_db_value(app, "SELECT COUNT(*) AS n FROM polls WHERE title = 'Where to eat'")
        assert row["n"] == 1

    def test_too_few_options_rejected(self, client, app, monkeypatch):
        monkeypatch.setattr("email_service.send_poll_created", lambda *a, **kw: True)
        self._login_admin(client, app)
        resp = client.post("/admin/poll/new", data={
            "title": "One option only",
            "poll_type": "date",
            "vote_mode": "approval",
            "options": "2025-11-15",
        }, follow_redirects=True)
        assert "two" in text(resp) or "2" in text(resp)

    def test_duplicate_dates_deduplicated(self, client, app, monkeypatch):
        monkeypatch.setattr("email_service.send_poll_created", lambda *a, **kw: True)
        self._login_admin(client, app)
        client.post("/admin/poll/new", data={
            "title": "Dedup test",
            "poll_type": "date",
            "vote_mode": "approval",
            "options": "2025-11-15\n2025-11-15\n2025-11-22",
        }, follow_redirects=True)
        row = get_db_value(app,
                           "SELECT COUNT(*) AS n FROM poll_options po"
                           " JOIN polls p ON p.id = po.poll_id"
                           " WHERE p.title = 'Dedup test'")
        assert row["n"] == 2

    def test_notify_called_on_creation(self, client, app, monkeypatch):
        called = {}
        def fake_notify(poll, db):
            called["poll"] = poll
            return True
        monkeypatch.setattr("email_service.send_poll_created", fake_notify)
        uid = self._login_admin(client, app)
        client.post("/admin/poll/new", data={
            "title": "Notif test",
            "poll_type": "date",
            "vote_mode": "approval",
            "options": "2025-11-15\n2025-11-22",
        })
        assert called.get("poll", {}).get("title") == "Notif test"

    def test_member_cannot_create_poll(self, client, app):
        make_user(app, username="member")
        login(client, "member")
        resp = client.post("/admin/poll/new", data={"title": "Nope"})
        assert resp.status_code == 403


# ── Poll status actions ────────────────────────────────────────────────────────

class TestPollStatusActions:
    def _setup(self, app, client):
        u = make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        poll_id = make_poll(app, u["id"])
        return poll_id

    def test_close_poll(self, client, app):
        poll_id = self._setup(app, client)
        client.post(f"/admin/poll/{poll_id}/close")
        row = get_db_value(app, "SELECT status FROM polls WHERE id = ?", (poll_id,))
        assert row["status"] == "closed"

    def test_close_already_closed_poll(self, client, app):
        poll_id = self._setup(app, client)
        client.post(f"/admin/poll/{poll_id}/close")
        resp = client.post(f"/admin/poll/{poll_id}/close", follow_redirects=True)
        assert "already closed" in text(resp)

    def test_reopen_poll(self, client, app):
        poll_id = self._setup(app, client)
        client.post(f"/admin/poll/{poll_id}/close")
        client.post(f"/admin/poll/{poll_id}/reopen")
        row = get_db_value(app, "SELECT status FROM polls WHERE id = ?", (poll_id,))
        assert row["status"] == "open"

    def test_delete_poll(self, client, app):
        poll_id = self._setup(app, client)
        client.post(f"/admin/poll/{poll_id}/delete")
        row = get_db_value(app, "SELECT id FROM polls WHERE id = ?", (poll_id,))
        assert row is None

    def test_delete_poll_cascades_votes(self, client, app):
        poll_id = self._setup(app, client)
        uid = _get_uid(app, "admin")
        with app.app_context():
            db = _db_mod.get_db()
            opt_id = db.execute(
                "SELECT id FROM poll_options WHERE poll_id = ? LIMIT 1", (poll_id,)
            ).fetchone()["id"]
            db.execute("INSERT INTO votes (poll_id, option_id, user_id) VALUES (?, ?, ?)",
                       (poll_id, opt_id, uid))
            db.commit()
        client.post(f"/admin/poll/{poll_id}/delete")
        row = get_db_value(app, "SELECT COUNT(*) AS n FROM votes WHERE poll_id = ?", (poll_id,))
        assert row["n"] == 0


# ── /admin/user/new ────────────────────────────────────────────────────────────

class TestNewUser:
    def _login_admin(self, client, app):
        make_user(app, username="admin", is_admin=1)
        login(client, "admin")

    def test_create_member(self, client, app):
        self._login_admin(client, app)
        client.post("/admin/user/new", data={
            "username": "bob",
            "email": "bob@example.com",
            "password": DEFAULT_PASSWORD,
        })
        row = get_db_value(app, "SELECT is_admin FROM users WHERE username = 'bob'")
        assert row is not None
        assert row["is_admin"] == 0

    def test_create_admin(self, client, app):
        self._login_admin(client, app)
        client.post("/admin/user/new", data={
            "username": "bob",
            "email": "bob@example.com",
            "password": DEFAULT_PASSWORD,
            "is_admin": "1",
        })
        row = get_db_value(app, "SELECT is_admin FROM users WHERE username = 'bob'")
        assert row["is_admin"] == 1

    def test_duplicate_username_rejected(self, client, app):
        self._login_admin(client, app)
        make_user(app, username="bob", email="bob@example.com")
        resp = client.post("/admin/user/new", data={
            "username": "bob",
            "email": "bob2@example.com",
            "password": DEFAULT_PASSWORD,
        }, follow_redirects=True)
        assert "not available" in text(resp)

    def test_short_password_rejected(self, client, app):
        self._login_admin(client, app)
        resp = client.post("/admin/user/new", data={
            "username": "bob",
            "email": "bob@example.com",
            "password": "short",
        }, follow_redirects=True)
        assert "10" in text(resp)


# ── User management ────────────────────────────────────────────────────────────

class TestUserManagement:
    def _login_admin(self, client, app):
        make_user(app, username="admin", is_admin=1)
        login(client, "admin")

    def test_toggle_admin_promotes_member(self, client, app):
        self._login_admin(client, app)
        bob = make_user(app, username="bob", email="bob@example.com")
        client.post(f"/admin/user/{bob['id']}/admin")
        row = get_db_value(app, "SELECT is_admin FROM users WHERE id = ?", (bob["id"],))
        assert row["is_admin"] == 1

    def test_toggle_admin_demotes_admin(self, client, app):
        self._login_admin(client, app)
        bob = make_user(app, username="bob", email="bob@example.com", is_admin=1)
        client.post(f"/admin/user/{bob['id']}/admin")
        row = get_db_value(app, "SELECT is_admin FROM users WHERE id = ?", (bob["id"],))
        assert row["is_admin"] == 0

    def test_cannot_toggle_own_admin_status(self, client, app):
        self._login_admin(client, app)
        uid = _get_uid(app, "admin")
        resp = client.post(f"/admin/user/{uid}/admin", follow_redirects=True)
        assert "cannot change your own" in text(resp)

    def test_unlock_clears_lockout(self, client, app):
        self._login_admin(client, app)
        bob = make_user(app, username="bob", email="bob@example.com")
        with app.app_context():
            db = _db_mod.get_db()
            db.execute("UPDATE users SET locked_until = 9999999999, failed_attempts = 5 WHERE id = ?",
                       (bob["id"],))
            db.commit()
        client.post(f"/admin/user/{bob['id']}/unlock")
        row = get_db_value(app,
                           "SELECT locked_until, failed_attempts FROM users WHERE id = ?",
                           (bob["id"],))
        assert row["locked_until"] is None
        assert row["failed_attempts"] == 0

    def test_delete_user_removes_account(self, client, app):
        self._login_admin(client, app)
        bob = make_user(app, username="bob", email="bob@example.com")
        client.post(f"/admin/user/{bob['id']}/delete")
        row = get_db_value(app, "SELECT id FROM users WHERE id = ?", (bob["id"],))
        assert row is None

    def test_cannot_delete_own_account(self, client, app):
        self._login_admin(client, app)
        uid = _get_uid(app, "admin")
        resp = client.post(f"/admin/user/{uid}/delete", follow_redirects=True)
        assert "cannot delete your own" in text(resp)

    def test_cannot_delete_user_with_polls(self, client, app):
        self._login_admin(client, app)
        bob = make_user(app, username="bob", email="bob@example.com")
        make_poll(app, bob["id"])
        resp = client.post(f"/admin/user/{bob['id']}/delete", follow_redirects=True)
        assert "created polls" in text(resp)

    def test_cannot_delete_user_with_restaurant_suggestions(self, client, app):
        self._login_admin(client, app)
        bob = make_user(app, username="bob", email="bob@example.com")
        with app.app_context():
            _db_mod.get_db().execute(
                "INSERT INTO restaurants (name, suggested_by) VALUES ('Gaucho', ?)",
                (bob["id"],)
            )
            _db_mod.get_db().commit()
        resp = client.post(f"/admin/user/{bob['id']}/delete", follow_redirects=True)
        assert "suggested restaurants" in text(resp)


# ── Restaurant moderation ──────────────────────────────────────────────────────

class TestRestaurantModeration:
    def _login_admin(self, client, app):
        make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        return _get_uid(app, "admin")

    def _add_pending(self, app, uid):
        with app.app_context():
            db = _db_mod.get_db()
            cursor = db.execute(
                "INSERT INTO restaurants (name, suggested_by, status) VALUES ('Hawksmoor', ?, 'pending')",
                (uid,)
            )
            rid = cursor.lastrowid
            db.commit()
        return rid

    def test_approve_restaurant(self, client, app):
        uid = self._login_admin(client, app)
        rid = self._add_pending(app, uid)
        client.post(f"/admin/restaurant/{rid}/approve")
        row = get_db_value(app, "SELECT status FROM restaurants WHERE id = ?", (rid,))
        assert row["status"] == "approved"

    def test_reject_restaurant(self, client, app):
        uid = self._login_admin(client, app)
        rid = self._add_pending(app, uid)
        client.post(f"/admin/restaurant/{rid}/reject")
        row = get_db_value(app, "SELECT status FROM restaurants WHERE id = ?", (rid,))
        assert row["status"] == "rejected"

    def test_approve_already_approved_shows_error(self, client, app):
        uid = self._login_admin(client, app)
        rid = self._add_pending(app, uid)
        client.post(f"/admin/restaurant/{rid}/approve")
        resp = client.post(f"/admin/restaurant/{rid}/approve", follow_redirects=True)
        assert "already processed" in text(resp)

    def test_member_cannot_approve(self, client, app):
        make_user(app, username="admin", is_admin=1)
        bob = make_user(app, username="bob", email="bob@example.com")
        login(client, "bob")
        uid = _get_uid(app, "admin")
        rid = self._add_pending(app, uid)
        resp = client.post(f"/admin/restaurant/{rid}/approve")
        assert resp.status_code == 403
