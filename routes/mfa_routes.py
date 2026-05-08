"""
MFA Blueprint — admin-only TOTP enrolment and login challenge.

Routes:
  GET/POST  /mfa/setup    — enrol (admin only, enforced by admin_required)
  GET/POST  /mfa/verify   — TOTP challenge after successful password login
  POST      /mfa/disable  — remove MFA (admin only, requires current TOTP code)

Register in app.py:
  from routes.mfa_routes import mfa_bp
  app.register_blueprint(mfa_bp)
"""

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash,
)
from mfa import (
    generate_totp_secret, generate_qr_png_b64, verify_totp,
    enable_mfa, disable_mfa, get_mfa_state,
    start_mfa_challenge, complete_mfa_challenge, pending_mfa_user_id,
    _SETUP_SECRET_KEY,
)
from auth import admin_required, current_user
from config import DATABASE

mfa_bp = Blueprint("mfa", __name__, url_prefix="/mfa")


@mfa_bp.route("/setup", methods=["GET", "POST"])
@admin_required
def setup():
    user = current_user()

    if request.method == "GET":
        secret = generate_totp_secret()
        session[_SETUP_SECRET_KEY] = secret
        qr_b64 = generate_qr_png_b64(secret, user["username"])
        return render_template("mfa/setup.html", qr_b64=qr_b64, secret=secret)

    code = request.form.get("code", "").strip()
    secret = session.get(_SETUP_SECRET_KEY)

    if not secret:
        flash("Session expired — please start setup again.", "error")
        return redirect(url_for("mfa.setup"))

    if not verify_totp(secret, code):
        flash("Invalid code — check your device clock and try again.", "error")
        qr_b64 = generate_qr_png_b64(secret, user["username"])
        return render_template("mfa/setup.html", qr_b64=qr_b64, secret=secret)

    enable_mfa(DATABASE, user["id"], secret)
    session.pop(_SETUP_SECRET_KEY, None)
    flash("Two-factor authentication is now enabled on your account.", "success")
    return redirect(url_for("polls.index"))


@mfa_bp.route("/verify", methods=["GET", "POST"])
def verify():
    user_id = pending_mfa_user_id()
    if user_id is None:
        return redirect(url_for("polls.index"))

    if request.method == "GET":
        return render_template("mfa/verify.html")

    code = request.form.get("code", "").strip()
    state = get_mfa_state(DATABASE, user_id)

    if not state["enabled"] or not state["secret"]:
        complete_mfa_challenge()
        return redirect(request.args.get("next") or url_for("polls.index"))

    if not verify_totp(state["secret"], code):
        flash("Invalid code — please try again.", "error")
        return render_template("mfa/verify.html")

    complete_mfa_challenge()
    return redirect(request.args.get("next") or url_for("polls.index"))


@mfa_bp.route("/disable", methods=["POST"])
@admin_required
def disable():
    user = current_user()
    code = request.form.get("code", "").strip()
    state = get_mfa_state(DATABASE, user["id"])

    if state["enabled"] and not verify_totp(state["secret"], code):
        flash("Invalid code — MFA was not disabled.", "error")
        return redirect(url_for("polls.index"))

    disable_mfa(DATABASE, user["id"])
    flash("Two-factor authentication has been removed from your account.", "success")
    return redirect(url_for("polls.index"))
