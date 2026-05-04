"""Integration tests for poll viewing and voting routes."""

from __future__ import annotations

import database as _db_mod
from tests.conftest import (
    get_db_value,
    get_option_ids,
    login,
    make_poll,
    make_user,
    text,
)

# ── / (poll list) ──────────────────────────────────────────────────────────────


class TestIndex:
    def test_loads_unauthenticated(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_shows_poll_titles_to_unauthenticated_user(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        make_poll(app, u["id"], title="November dinner")
        resp = client.get("/")
        assert "november dinner" in text(resp)

    def test_open_polls_appear_before_closed(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        make_poll(app, u["id"], title="Closed poll", status="closed")
        make_poll(app, u["id"], title="Open poll", status="open")
        resp = client.get("/")
        page = text(resp)
        assert page.index("open poll") < page.index("closed poll")

    def test_ping_endpoint(self, client):
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert b"pong" in resp.data


# ── /poll/<id> ─────────────────────────────────────────────────────────────────


class TestViewPoll:
    def test_redirects_to_login_when_unauthenticated(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        poll_id = make_poll(app, u["id"])
        resp = client.get(f"/poll/{poll_id}")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_404_for_missing_poll(self, client, app):
        make_user(app, username="alice")
        login(client, "alice")
        resp = client.get("/poll/99999")
        assert resp.status_code == 404

    def test_restaurant_poll_shows_options(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        poll_id = make_poll(app, u["id"], options=("Hawksmoor", "Gaucho"))
        resp = client.get(f"/poll/{poll_id}")
        assert resp.status_code == 200
        assert "hawksmoor" in text(resp)
        assert "gaucho" in text(resp)

    def test_date_poll_renders_calendar(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        poll_id = make_poll(
            app, u["id"], poll_type="date", options=("2025-11-15", "2025-11-22")
        )
        resp = client.get(f"/poll/{poll_id}")
        assert resp.status_code == 200
        assert "november" in text(resp)

    def test_closed_poll_shows_results(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        poll_id = make_poll(
            app, u["id"], status="closed", options=("Hawksmoor", "Gaucho")
        )
        resp = client.get(f"/poll/{poll_id}")
        assert "final results" in text(resp)

    def test_admin_actions_visible_to_admin(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        poll_id = make_poll(app, u["id"])
        resp = client.get(f"/poll/{poll_id}")
        assert "admin actions" in text(resp)

    def test_admin_actions_hidden_from_member(self, client, app):
        admin = make_user(app, username="admin", is_admin=1)
        make_user(app, username="member", email="member@example.com")
        poll_id = make_poll(app, admin["id"])
        login(client, "member")
        resp = client.get(f"/poll/{poll_id}")
        assert "admin actions" not in text(resp)


# ── /poll/<id>/vote ────────────────────────────────────────────────────────────


class TestVote:
    def _setup(self, app, client, vote_mode="single", options=("Hawksmoor", "Gaucho")):
        u = make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        poll_id = make_poll(app, u["id"], vote_mode=vote_mode, options=options)
        opt_ids = get_option_ids(app, poll_id)
        return u["id"], poll_id, opt_ids

    def test_requires_login(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        poll_id = make_poll(app, u["id"])
        opt_ids = get_option_ids(app, poll_id)
        resp = client.post(f"/poll/{poll_id}/vote", data={"option_id": opt_ids[0]})
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_single_vote_recorded(self, client, app):
        uid, poll_id, opt_ids = self._setup(app, client)
        resp = client.post(
            f"/poll/{poll_id}/vote",
            data={"option_id": opt_ids[0]},
            follow_redirects=True,
        )
        assert "vote has been recorded" in text(resp)
        row = get_db_value(
            app, "SELECT COUNT(*) AS n FROM votes WHERE poll_id = ?", (poll_id,)
        )
        assert row["n"] == 1

    def test_approval_vote_records_multiple(self, client, app):
        uid, poll_id, opt_ids = self._setup(
            app, client, vote_mode="approval", options=("A", "B", "C")
        )
        client.post(
            f"/poll/{poll_id}/vote", data={"option_ids": [opt_ids[0], opt_ids[2]]}
        )
        row = get_db_value(
            app, "SELECT COUNT(*) AS n FROM votes WHERE poll_id = ?", (poll_id,)
        )
        assert row["n"] == 2

    def test_second_vote_replaces_first(self, client, app):
        uid, poll_id, opt_ids = self._setup(app, client)
        client.post(f"/poll/{poll_id}/vote", data={"option_id": opt_ids[0]})
        client.post(f"/poll/{poll_id}/vote", data={"option_id": opt_ids[1]})
        with app.app_context():
            rows = (
                _db_mod.get_db()
                .execute("SELECT option_id FROM votes WHERE poll_id = ?", (poll_id,))
                .fetchall()
            )
        assert len(rows) == 1
        assert rows[0]["option_id"] == opt_ids[1]

    def test_submitting_nothing_clears_vote(self, client, app):
        uid, poll_id, opt_ids = self._setup(app, client)
        client.post(f"/poll/{poll_id}/vote", data={"option_id": opt_ids[0]})
        client.post(f"/poll/{poll_id}/vote", data={})  # clear
        row = get_db_value(
            app, "SELECT COUNT(*) AS n FROM votes WHERE poll_id = ?", (poll_id,)
        )
        assert row["n"] == 0

    def test_voting_on_closed_poll_shows_error(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        poll_id = make_poll(app, u["id"], status="closed")
        opt_ids = get_option_ids(app, poll_id)
        resp = client.post(
            f"/poll/{poll_id}/vote",
            data={"option_id": opt_ids[0]},
            follow_redirects=True,
        )
        assert "closed" in text(resp)

    def test_invalid_option_id_returns_400(self, client, app):
        uid, poll_id, opt_ids = self._setup(app, client)
        resp = client.post(f"/poll/{poll_id}/vote", data={"option_id": 99999})
        assert resp.status_code == 400

    def test_non_integer_option_id_returns_400(self, client, app):
        uid, poll_id, opt_ids = self._setup(app, client)
        resp = client.post(f"/poll/{poll_id}/vote", data={"option_id": "abc"})
        assert resp.status_code == 400

    def test_option_from_other_poll_rejected(self, client, app):
        u = make_user(app, username="admin", is_admin=1)
        login(client, "admin")
        poll1 = make_poll(app, u["id"], title="Poll 1")
        poll2 = make_poll(app, u["id"], title="Poll 2")
        poll2_opts = get_option_ids(app, poll2)
        # Try to vote on poll1 using an option_id from poll2
        resp = client.post(f"/poll/{poll1}/vote", data={"option_id": poll2_opts[0]})
        assert resp.status_code == 400
