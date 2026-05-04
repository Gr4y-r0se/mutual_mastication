"""Admin-only routes: dashboard, poll/user management, and restaurant moderation."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from auth import admin_required, current_user
from config import EMAIL_RE, MIN_PASSWORD_LENGTH, USERNAME_RE
from database import get_db
from email_service import send_poll_created

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@admin_required
def dashboard():
    db = get_db()
    users = db.execute(
        "SELECT id, username, email, is_admin, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    polls = db.execute(
        "SELECT id, title, poll_type, vote_mode, status, end_date, created_at "
        "FROM polls ORDER BY created_at DESC"
    ).fetchall()
    pending_count = db.execute(
        "SELECT COUNT(*) FROM restaurants WHERE status = 'pending'"
    ).fetchone()[0]
    return render_template(
        "admin.html", users=users, polls=polls, pending_count=pending_count
    )


@admin_bp.route("/admin/poll/new", methods=["GET", "POST"])
@admin_required
def new_poll():
    db = get_db()
    approved_restaurants = db.execute(
        "SELECT id, name, cuisine FROM restaurants WHERE status = 'approved' ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        poll_type = request.form.get("poll_type") or ""
        vote_mode = request.form.get("vote_mode") or ""
        end_date_raw = (request.form.get("end_date") or "").strip()

        errors = []
        if not (1 <= len(title) <= 200):
            errors.append("Title must be 1-200 characters.")
        if len(description) > 1000:
            errors.append("Description must be at most 1000 characters.")
        if poll_type not in ("date", "restaurant"):
            errors.append("Poll type must be 'date' or 'restaurant'.")
        if vote_mode not in ("single", "approval"):
            errors.append("Vote mode must be 'single' or 'approval'.")

        end_date = None
        if end_date_raw:
            try:
                # datetime-local gives "YYYY-MM-DDTHH:MM"
                end_date = datetime.strptime(end_date_raw, "%Y-%m-%dT%H:%M").strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                errors.append("Invalid end date format.")

        if poll_type == "restaurant":
            try:
                selected_ids = [int(i) for i in request.form.getlist("restaurant_ids")]
            except ValueError:
                abort(400)
            if selected_ids:
                placeholders = ",".join("?" * len(selected_ids))
                valid = db.execute(
                    f"SELECT id, name FROM restaurants "
                    f"WHERE status = 'approved' AND id IN ({placeholders})",
                    selected_ids,
                ).fetchall()
                options = [r["name"] for r in valid]
            else:
                options = []
        else:
            options_raw = request.form.get("options") or ""
            options = [
                line.strip()[:200] for line in options_raw.splitlines() if line.strip()
            ]
            seen: set = set()
            options = [o for o in options if not (o in seen or seen.add(o))]

        if len(options) < 2:
            errors.append("Provide at least two distinct options.")
        if len(options) > 50:
            errors.append("Maximum of 50 options.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin_new_poll.html",
                title=title,
                description=description,
                poll_type=poll_type,
                vote_mode=vote_mode,
                end_date=end_date_raw,
                approved_restaurants=approved_restaurants,
            )

        cursor = db.execute(
            "INSERT INTO polls (title, description, poll_type, vote_mode, created_by, end_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, poll_type, vote_mode, current_user()["id"], end_date),
        )
        poll_id = cursor.lastrowid
        for label in options:
            db.execute(
                "INSERT INTO poll_options (poll_id, label) VALUES (?, ?)",
                (poll_id, label),
            )
        db.commit()

        send_poll_created(
            {"id": poll_id, "title": title, "description": description, "end_date": end_date},
            db,
        )

        flash("Poll created.", "success")
        return redirect(url_for("polls.view_poll", poll_id=poll_id))

    return render_template(
        "admin_new_poll.html", approved_restaurants=approved_restaurants
    )


@admin_bp.route("/admin/poll/<int:poll_id>/close", methods=["POST"])
@admin_required
def close_poll(poll_id):
    db = get_db()
    result = db.execute(
        "UPDATE polls SET status = 'closed' WHERE id = ? AND status = 'open'",
        (poll_id,),
    )
    db.commit()
    flash(
        "Poll closed." if result.rowcount else "Poll not found or already closed.",
        "success" if result.rowcount else "error",
    )
    return redirect(url_for("polls.view_poll", poll_id=poll_id))


@admin_bp.route("/admin/poll/<int:poll_id>/reopen", methods=["POST"])
@admin_required
def reopen_poll(poll_id):
    db = get_db()
    result = db.execute(
        "UPDATE polls SET status = 'open' WHERE id = ? AND status = 'closed'",
        (poll_id,),
    )
    db.commit()
    flash(
        "Poll reopened." if result.rowcount else "Poll not found or already open.",
        "success" if result.rowcount else "error",
    )
    return redirect(url_for("polls.view_poll", poll_id=poll_id))


@admin_bp.route("/admin/poll/<int:poll_id>/delete", methods=["POST"])
@admin_required
def delete_poll(poll_id):
    db = get_db()
    db.execute("DELETE FROM polls WHERE id = ?", (poll_id,))
    db.commit()
    flash("Poll deleted.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/user/new", methods=["GET", "POST"])
@admin_required
def new_user():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        is_admin = 1 if request.form.get("is_admin") else 0

        errors = []
        if not USERNAME_RE.match(username):
            errors.append(
                "Username must be 3-32 characters: letters, numbers, underscores."
            )
        if not EMAIL_RE.match(email) or len(email) > 254:
            errors.append("Please provide a valid email address.")
        if len(password) < MIN_PASSWORD_LENGTH or len(password) > 256:
            errors.append(f"Password must be {MIN_PASSWORD_LENGTH}-256 characters.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin_new_user.html", username=username, email=email, is_admin=is_admin
            )

        db = get_db()
        if db.execute(
            "SELECT 1 FROM users WHERE username = ? OR email = ?", (username, email)
        ).fetchone():
            flash("Those credentials are not available.", "error")
            return render_template(
                "admin_new_user.html", username=username, email=email, is_admin=is_admin
            )

        password_hash = generate_password_hash(
            password, method="pbkdf2:sha256", salt_length=16
        )
        db.execute(
            "INSERT INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, is_admin),
        )
        db.commit()
        flash(f"User '{username}' created.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin_new_user.html")


@admin_bp.route("/admin/user/<int:user_id>/admin", methods=["POST"])
@admin_required
def toggle_admin(user_id):
    actor = current_user()
    if user_id == actor["id"]:
        flash("You cannot change your own admin status.", "error")
        return redirect(url_for("admin.dashboard"))
    db = get_db()
    target = db.execute(
        "SELECT id, is_admin FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if target is None:
        abort(404)
    db.execute(
        "UPDATE users SET is_admin = ? WHERE id = ?",
        (0 if target["is_admin"] else 1, user_id),
    )
    db.commit()
    flash("User admin status updated.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/user/<int:user_id>/unlock", methods=["POST"])
@admin_required
def unlock_user(user_id):
    db = get_db()
    db.execute(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
        (user_id,),
    )
    db.commit()
    flash("User unlocked.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    actor = current_user()
    if user_id == actor["id"]:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.dashboard"))
    db = get_db()
    poll_count = db.execute(
        "SELECT COUNT(*) FROM polls WHERE created_by = ?", (user_id,)
    ).fetchone()[0]
    if poll_count > 0:
        flash("Cannot delete a user who has created polls.", "error")
        return redirect(url_for("admin.dashboard"))
    restaurant_count = db.execute(
        "SELECT COUNT(*) FROM restaurants WHERE suggested_by = ?", (user_id,)
    ).fetchone()[0]
    if restaurant_count > 0:
        flash("Cannot delete a user who has suggested restaurants.", "error")
        return redirect(url_for("admin.dashboard"))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("User deleted.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/restaurants")
@admin_required
def restaurants():
    db = get_db()
    pending = db.execute(
        """
        SELECT r.id, r.name, r.cuisine, r.description, r.address,
               u.username AS suggested_by, r.created_at
        FROM restaurants r JOIN users u ON u.id = r.suggested_by
        WHERE r.status = 'pending'
        ORDER BY r.created_at ASC
        """
    ).fetchall()
    approved = db.execute(
        """
        SELECT r.id, r.name, r.cuisine, r.description, r.address,
               u.username AS suggested_by, r.created_at
        FROM restaurants r JOIN users u ON u.id = r.suggested_by
        WHERE r.status = 'approved'
        ORDER BY r.name
        """
    ).fetchall()
    return render_template("admin_restaurants.html", pending=pending, approved=approved)


@admin_bp.route("/admin/restaurant/<int:restaurant_id>/approve", methods=["POST"])
@admin_required
def approve_restaurant(restaurant_id):
    db = get_db()
    result = db.execute(
        "UPDATE restaurants SET status = 'approved' WHERE id = ? AND status = 'pending'",
        (restaurant_id,),
    )
    db.commit()
    flash(
        "Restaurant approved."
        if result.rowcount
        else "Not found or already processed.",
        "success" if result.rowcount else "error",
    )
    return redirect(url_for("admin.restaurants"))


@admin_bp.route("/admin/restaurant/<int:restaurant_id>/reject", methods=["POST"])
@admin_required
def reject_restaurant(restaurant_id):
    db = get_db()
    result = db.execute(
        "UPDATE restaurants SET status = 'rejected' WHERE id = ? AND status = 'pending'",
        (restaurant_id,),
    )
    db.commit()
    flash(
        "Restaurant rejected."
        if result.rowcount
        else "Not found or already processed.",
        "success" if result.rowcount else "error",
    )
    return redirect(url_for("admin.restaurants"))
