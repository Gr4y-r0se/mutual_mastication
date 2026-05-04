"""Authentication helpers: session-based current_user lookup and route decorators."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps

from flask import abort, flash, redirect, request, session, url_for

from database import get_db


def current_user():
    """Return the logged-in user row, or ``None`` if the session is anonymous.

    Clears the session if the stored ``user_id`` no longer exists in the database
    (e.g. the account was deleted while the session was still active).
    """
    if "user_id" not in session:
        return None
    row = (
        get_db()
        .execute(
            "SELECT id, username, email, is_admin FROM users WHERE id = ?",
            (session["user_id"],),
        )
        .fetchone()
    )
    if row is None:
        session.clear()
    return row


def login_required(view):
    """Decorator: redirect unauthenticated requests to /login with a ``next`` param."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    """Decorator: redirect anonymous users to /login; abort 403 for non-admins."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.path))
        if not user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def _now_epoch() -> int:
    """Return the current UTC time as a Unix timestamp integer."""
    return int(datetime.now(tz=timezone.utc).timestamp())
