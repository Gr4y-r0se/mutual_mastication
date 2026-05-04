"""Integration tests for restaurant listing and suggestion routes."""

from __future__ import annotations

import database as _db_mod
from tests.conftest import get_db_value, login, make_user, text


def _add_restaurant(app, uid, name="Hawksmoor", status="approved"):
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


# ── /restaurants ───────────────────────────────────────────────────────────────


class TestListRestaurants:
    def test_redirects_when_not_logged_in(self, client):
        resp = client.get("/restaurants")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_shows_approved_restaurants(self, client, app):
        u = make_user(app, username="alice")
        login(client, "alice")
        _add_restaurant(app, u["id"], name="Hawksmoor", status="approved")
        assert "hawksmoor" in text(client.get("/restaurants"))

    def test_hides_pending_restaurants(self, client, app):
        u = make_user(app, username="alice")
        login(client, "alice")
        _add_restaurant(app, u["id"], name="Secret Steak", status="pending")
        assert "secret steak" not in text(client.get("/restaurants"))

    def test_hides_rejected_restaurants(self, client, app):
        u = make_user(app, username="alice")
        login(client, "alice")
        _add_restaurant(app, u["id"], name="Rejected Place", status="rejected")
        assert "rejected place" not in text(client.get("/restaurants"))

    def test_shows_own_suggestions_table(self, client, app):
        u = make_user(app, username="alice")
        login(client, "alice")
        _add_restaurant(app, u["id"], name="My Suggestion", status="pending")
        resp = client.get("/restaurants")
        assert "my suggestion" in text(resp)

    def test_does_not_show_others_pending_suggestions(self, client, app):
        admin = make_user(app, username="admin", is_admin=1)
        u = make_user(app, username="alice", email="alice@example.com")
        login(client, "alice")
        _add_restaurant(app, admin["id"], name="Admin's Secret", status="pending")
        assert "admin's secret" not in text(client.get("/restaurants"))


# ── /restaurants/suggest ───────────────────────────────────────────────────────


class TestSuggestRestaurant:
    def test_requires_login(self, client):
        resp = client.post("/restaurants/suggest", data={"name": "Gaucho"})
        assert resp.status_code == 302

    def test_valid_suggestion_created(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.post(
            "/restaurants/suggest",
            data={
                "name": "Gaucho",
                "cuisine": "Argentinian",
                "address": "1 Strand, London",
                "link": "https://gaucho.co.uk",
                "description": "Great steaks",
            },
            follow_redirects=True,
        )
        assert "suggested" in text(resp) or "review" in text(resp)
        row = get_db_value(app, "SELECT status FROM restaurants WHERE name = 'Gaucho'")
        assert row is not None
        assert row["status"] == "pending"

    def test_suggestion_missing_name_rejected(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.post(
            "/restaurants/suggest", data={"name": ""}, follow_redirects=True
        )
        assert "name" in text(resp)
        row = get_db_value(app, "SELECT COUNT(*) AS n FROM restaurants")
        assert row["n"] == 0

    def test_invalid_link_rejected(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.post(
            "/restaurants/suggest",
            data={
                "name": "Gaucho",
                "link": "not-a-url",
            },
            follow_redirects=True,
        )
        assert "http" in text(resp)

    def test_valid_https_link_accepted(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        client.post(
            "/restaurants/suggest",
            data={
                "name": "Gaucho",
                "link": "https://gaucho.co.uk",
            },
        )
        row = get_db_value(app, "SELECT link FROM restaurants WHERE name = 'Gaucho'")
        assert row["link"] == "https://gaucho.co.uk"

    def test_name_too_long_rejected(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.post(
            "/restaurants/suggest", data={"name": "A" * 201}, follow_redirects=True
        )
        assert "200" in text(resp) or "characters" in text(resp)

    def test_cuisine_too_long_rejected(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.post(
            "/restaurants/suggest",
            data={
                "name": "Gaucho",
                "cuisine": "C" * 101,
            },
            follow_redirects=True,
        )
        assert "100" in text(resp) or "characters" in text(resp)

    def test_multiple_members_can_suggest(self, client, app):
        alice = make_user(app, username="alice", email="alice@example.com")
        bob = make_user(app, username="bob", email="bob@example.com")
        login(client, "alice")
        client.post("/restaurants/suggest", data={"name": "Alice's Pick"})
        client.post("/logout")
        login(client, "bob")
        client.post("/restaurants/suggest", data={"name": "Bob's Pick"})
        row = get_db_value(app, "SELECT COUNT(*) AS n FROM restaurants")
        assert row["n"] == 2
