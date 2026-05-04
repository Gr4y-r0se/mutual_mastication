from __future__ import annotations

import secrets
import time

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
from email_service import send_password_reset

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/ping", methods=["GET"])
def ping():
    return "pong", 200, {"ContentType": "text/plain"}


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
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
            errors.append(
                "Username must be 3-32 characters: letters, numbers, underscores."
            )
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

        password_hash = generate_password_hash(
            password, method="pbkdf2:sha256", salt_length=16
        )
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
            flash(
                "Account temporarily locked due to failed attempts. Try again later.",
                "error",
            )
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
    votes = (
        get_db()
        .execute(
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
        )
        .fetchall()
    )
    return render_template("profile.html", user=user, votes=votes)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user():
        return redirect(url_for("polls.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        db = get_db()
        user = db.execute(
            "SELECT id, email FROM users WHERE email = ?", (email,)
        ).fetchone()

        if user:
            token = secrets.token_urlsafe(32)
            expires_at = int(time.time()) + 3600
            db.execute(
                "DELETE FROM password_reset_tokens WHERE user_id = ?", (user["id"],)
            )
            db.execute(
                "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
                (user["id"], token, expires_at),
            )
            db.commit()
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            send_password_reset(user["email"], reset_url)

        # Always show the same message to prevent email enumeration
        flash("If that email is registered, a reset link has been sent.", "success")
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user():
        return redirect(url_for("polls.index"))

    db = get_db()
    now = int(time.time())
    record = db.execute(
        "SELECT id, user_id FROM password_reset_tokens "
        "WHERE token = ? AND used = 0 AND expires_at > ?",
        (token, now),
    ).fetchone()

    if record is None:
        flash("This reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        errors = []
        if len(password) < MIN_PASSWORD_LENGTH or len(password) > 256:
            errors.append(f"Password must be {MIN_PASSWORD_LENGTH}-256 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("reset_password.html", token=token)

        password_hash = generate_password_hash(
            password, method="pbkdf2:sha256", salt_length=16
        )
        db.execute(
            "UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL "
            "WHERE id = ?",
            (password_hash, record["user_id"]),
        )
        db.execute(
            "UPDATE password_reset_tokens SET used = 1 WHERE id = ?", (record["id"],)
        )
        db.commit()
        flash("Password updated. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""

        user = current_user()
        db = get_db()
        row = db.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
        ).fetchone()

        errors = []
        if not check_password_hash(row["password_hash"], current_password):
            errors.append("Current password is incorrect.")
        if len(new_password) < MIN_PASSWORD_LENGTH or len(new_password) > 256:
            errors.append(f"New password must be {MIN_PASSWORD_LENGTH}-256 characters.")
        if new_password != confirm:
            errors.append("New passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("change_password.html")

        password_hash = generate_password_hash(
            new_password, method="pbkdf2:sha256", salt_length=16
        )
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user["id"]),
        )
        db.commit()
        flash("Password changed successfully.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("change_password.html")
