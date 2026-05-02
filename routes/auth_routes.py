from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from auth import _now_epoch, current_user, login_required
from config import (
    DUMMY_PASSWORD_HASH,
    EMAIL_RE,
    LOCKOUT_MINUTES,
    MAX_FAILED_ATTEMPTS,
    MIN_PASSWORD_LENGTH,
    USERNAME_RE,
)
from database import get_db

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/ping", methods=["GET"])
def ping():
    return 'pong', 200, {'ContentType':'text/plain'} 

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
    # Self-registration is only allowed to bootstrap the very first admin account.
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        flash("Account registration is by invitation only.", "error")
        return redirect(url_for("auth.login"))

    if current_user():
        return redirect(url_for("polls.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        errors = []
        if not USERNAME_RE.match(username):
            errors.append("Username must be 3-32 characters: letters, numbers, underscores.")
        if not EMAIL_RE.match(email) or len(email) > 254:
            errors.append("Please provide a valid email address.")
        if len(password) < MIN_PASSWORD_LENGTH or len(password) > 256:
            errors.append(f"Password must be {MIN_PASSWORD_LENGTH}-256 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", username=username, email=email)

        if db.execute(
            "SELECT 1 FROM users WHERE username = ? OR email = ?", (username, email)
        ).fetchone():
            flash("Those credentials are not available.", "error")
            return render_template("register.html", username=username, email=email)

        password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
        db.execute(
            "INSERT INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, 1)",
            (username, email, password_hash),
        )
        db.commit()
        flash("Admin account created. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("polls.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""

        db = get_db()
        user = db.execute(
            "SELECT id, username, password_hash, is_admin, failed_attempts, locked_until "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        now = _now_epoch()

        if user and user["locked_until"] and user["locked_until"] > now:
            flash("Account temporarily locked due to failed attempts. Try again later.", "error")
            return render_template("login.html", username=username)

        if user:
            valid = check_password_hash(user["password_hash"], password)
        else:
            check_password_hash(DUMMY_PASSWORD_HASH, password)
            valid = False

        if not valid:
            if user:
                attempts = user["failed_attempts"] + 1
                locked_until = None
                if attempts >= MAX_FAILED_ATTEMPTS:
                    locked_until = now + LOCKOUT_MINUTES * 60
                    attempts = 0
                db.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                    (attempts, locked_until, user["id"]),
                )
                db.commit()
            flash("Invalid username or password.", "error")
            return render_template("login.html", username=username)

        db.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (user["id"],),
        )
        db.commit()

        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True

        flash(f"Welcome back, {user['username']}.", "success")

        next_url = request.args.get("next", "")
        if (
            next_url
            and next_url.startswith("/")
            and not next_url.startswith("//")
            and "\\" not in next_url
        ):
            return redirect(next_url)
        return redirect(url_for("polls.index"))

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("polls.index"))


@auth_bp.route("/profile")
@login_required
def profile():
    user = current_user()
    votes = get_db().execute(
        """
        SELECT p.id AS poll_id, p.title, p.poll_type,
               p.status, o.label, v.created_at
        FROM votes v
        JOIN polls p        ON p.id = v.poll_id
        JOIN poll_options o ON o.id = v.option_id
        WHERE v.user_id = ?
        ORDER BY v.created_at DESC
        LIMIT 100
        """,
        (user["id"],),
    ).fetchall()
    return render_template("profile.html", user=user, votes=votes)
