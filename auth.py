from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps

from flask import abort, flash, redirect, request, session, url_for

from database import get_db


def current_user():
    if "user_id" not in session:
        return None
    row = get_db().execute(
        "SELECT id, username, email, is_admin FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    if row is None:
        session.clear()
    return row


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
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
    return int(datetime.now(tz=timezone.utc).timestamp())
