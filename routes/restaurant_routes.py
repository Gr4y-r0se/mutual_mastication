"""Restaurant routes: listing approved restaurants and submitting suggestions."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from auth import current_user, login_required
from database import get_db

restaurant_bp = Blueprint("restaurants", __name__)


@restaurant_bp.route("/restaurants")
@login_required
def list_restaurants():
    db = get_db()
    approved = db.execute("""
        SELECT r.name, r.cuisine, r.description, r.address, r.link,
               u.username AS suggested_by, r.created_at
        FROM restaurants r JOIN users u ON u.id = r.suggested_by
        WHERE r.status = 'approved'
        ORDER BY r.name
        """).fetchall()
    my_suggestions = db.execute(
        """
        SELECT id, name, cuisine, status, created_at
        FROM restaurants
        WHERE suggested_by = ?
        ORDER BY created_at DESC
        """,
        (current_user()["id"],),
    ).fetchall()
    return render_template(
        "restaurants.html", approved=approved, my_suggestions=my_suggestions
    )


@restaurant_bp.route("/restaurants/suggest", methods=["POST"])
@login_required
def suggest_restaurant():
    name = (request.form.get("name") or "").strip()
    cuisine = (request.form.get("cuisine") or "").strip()
    description = (request.form.get("description") or "").strip()
    address = (request.form.get("address") or "").strip()
    link = (request.form.get("link") or "").strip()

    errors = []
    if not (1 <= len(name) <= 200):
        errors.append("Restaurant name must be 1-200 characters.")
    if len(cuisine) > 100:
        errors.append("Cuisine must be at most 100 characters.")
    if len(description) > 500:
        errors.append("Description must be at most 500 characters.")
    if len(address) > 300:
        errors.append("Address must be at most 300 characters.")
    if link and not (link.startswith("http://") or link.startswith("https://")):
        errors.append("Link must start with http:// or https://")
    if len(link) > 500:
        errors.append("Link must be at most 500 characters.")

    for e in errors:
        flash(e, "error")
    if errors:
        return redirect(url_for("restaurants.list_restaurants"))

    db = get_db()
    db.execute(
        "INSERT INTO restaurants (name, cuisine, description, address, link, suggested_by) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, cuisine, description, address, link, current_user()["id"]),
    )
    db.commit()
    flash("Restaurant suggested! An admin will review it shortly.", "success")
    return redirect(url_for("restaurants.list_restaurants"))
