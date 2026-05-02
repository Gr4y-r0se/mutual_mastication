from __future__ import annotations

import calendar as cal_module
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from auth import current_user, login_required
from database import get_db

poll_bp = Blueprint("polls", __name__)


def _build_calendar_data(options, my_votes, voters_by_option):
    """
    Parse ISO date options (YYYY-MM-DD) into per-month calendar structures.
    Returns a list of month dicts, or None if any option label isn't a valid date.
    """
    date_opts_by_month: dict = {}
    for opt in options:
        try:
            d = datetime.strptime(opt["label"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
        key = (d.year, d.month)
        date_opts_by_month.setdefault(key, []).append(
            {
                "id": opt["id"],
                "day": d.day,
                "label": opt["label"],
                "vote_count": opt["vote_count"],
                "voted": opt["id"] in my_votes,
                "voters": voters_by_option.get(opt["id"], []),
            }
        )

    months = []
    for year, month in sorted(date_opts_by_month.keys()):
        opts_by_day = {o["day"]: o for o in date_opts_by_month[(year, month)]}
        weeks = cal_module.monthcalendar(year, month)  # Monday-first weeks
        months.append(
            {
                "year": year,
                "month": month,
                "month_name": cal_module.month_name[month],
                "weeks": [
                    [
                        {"day": day, "option": opts_by_day.get(day)}
                        if day != 0
                        else None
                        for day in week
                    ]
                    for week in weeks
                ],
            }
        )
    return months


@poll_bp.route("/")
def index():
    db = get_db()
    polls = db.execute(
        """
        SELECT p.id, p.title, p.description, p.poll_type, p.vote_mode,
               p.status, p.created_at, u.username AS creator,
               (SELECT COUNT(*) FROM poll_options o WHERE o.poll_id = p.id)
                   AS option_count
        FROM polls p
        JOIN users u ON u.id = p.created_by
        ORDER BY (p.status = 'open') DESC, p.created_at DESC
        LIMIT 50
        """
    ).fetchall()
    return render_template("index.html", polls=polls)


@poll_bp.route("/poll/<int:poll_id>")
@login_required
def view_poll(poll_id):
    db = get_db()
    poll = db.execute(
        "SELECT p.*, u.username AS creator "
        "FROM polls p JOIN users u ON u.id = p.created_by "
        "WHERE p.id = ?",
        (poll_id,),
    ).fetchone()
    if poll is None:
        abort(404)

    options = db.execute(
        """
        SELECT o.id, o.label,
               (SELECT COUNT(*) FROM votes v WHERE v.option_id = o.id) AS vote_count
        FROM poll_options o
        WHERE o.poll_id = ?
        ORDER BY o.label ASC
        """,
        (poll_id,),
    ).fetchall()

    user = current_user()
    my_votes = {
        row["option_id"]
        for row in db.execute(
            "SELECT option_id FROM votes WHERE poll_id = ? AND user_id = ?",
            (poll_id, user["id"]),
        ).fetchall()
    }
    total_voters = db.execute(
        "SELECT COUNT(DISTINCT user_id) FROM votes WHERE poll_id = ?",
        (poll_id,),
    ).fetchone()[0]

    voters_by_option: dict = {}
    for row in db.execute(
        """
        SELECT v.option_id, u.username
        FROM votes v JOIN users u ON u.id = v.user_id
        WHERE v.poll_id = ?
        """,
        (poll_id,),
    ).fetchall():
        voters_by_option.setdefault(row["option_id"], []).append(row["username"])

    calendar_data = None
    if poll["poll_type"] == "date":
        calendar_data = _build_calendar_data(options, my_votes, voters_by_option)

    return render_template(
        "poll.html",
        poll=poll,
        options=options,
        my_votes=my_votes,
        total_voters=total_voters,
        calendar_data=calendar_data,
        voters_by_option=voters_by_option,
    )


@poll_bp.route("/poll/<int:poll_id>/vote", methods=["POST"])
@login_required
def vote(poll_id):
    db = get_db()
    poll = db.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()
    if poll is None:
        abort(404)
    if poll["status"] != "open":
        flash("This poll is closed.", "error")
        return redirect(url_for("polls.view_poll", poll_id=poll_id))

    user = current_user()

    if poll["vote_mode"] == "single":
        raw = request.form.get("option_id", "").strip()
        try:
            submitted = [int(raw)] if raw else []
        except ValueError:
            abort(400)
    else:
        submitted = []
        for value in request.form.getlist("option_ids"):
            try:
                submitted.append(int(value))
            except ValueError:
                abort(400)

    submitted = list(set(submitted))[:50]

    if submitted:
        placeholders = ",".join("?" * len(submitted))
        valid_ids = {
            row[0]
            for row in db.execute(
                f"SELECT id FROM poll_options WHERE poll_id = ? AND id IN ({placeholders})",
                (poll_id, *submitted),
            ).fetchall()
        }
        if len(valid_ids) != len(submitted):
            abort(400)

    db.execute(
        "DELETE FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user["id"])
    )
    for oid in submitted:
        db.execute(
            "INSERT INTO votes (poll_id, option_id, user_id) VALUES (?, ?, ?)",
            (poll_id, oid, user["id"]),
        )
    db.commit()
    flash("Your vote has been recorded.", "success")
    return redirect(url_for("polls.view_poll", poll_id=poll_id))
