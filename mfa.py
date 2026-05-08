"""
Google Authenticator-compatible TOTP MFA module for mutual_mastication.

Requires:
  pip install pyotp qrcode[pil]

Database migration: call init_db_mfa(DATABASE) once at startup in app.py.
"""

import io
import base64
import sqlite3
import pyotp
import qrcode
from functools import wraps
from flask import session, redirect, url_for, abort

APP_NAME = "MeatEnsemble"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db_mfa(db_path: str) -> None:
    """Add MFA columns to users table if they don't exist yet (idempotent)."""
    conn = _get_db(db_path)
    try:
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        migrations = {
            "totp_secret": "ALTER TABLE users ADD COLUMN totp_secret TEXT",
            "mfa_enabled":
                "ALTER TABLE users ADD COLUMN mfa_enabled INTEGER NOT NULL DEFAULT 0",
        }
        for col, sql in migrations.items():
            if col not in existing:
                conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# TOTP helpers
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=APP_NAME)


def generate_qr_png_b64(secret: str, username: str) -> str:
    """Return a base64-encoded PNG of the QR code for inline <img> embedding."""
    img = qrcode.make(get_totp_uri(secret, username))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """Verify a 6-digit TOTP code with ±30 s clock-skew tolerance."""
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=valid_window)


# ---------------------------------------------------------------------------
# User DB accessors
# ---------------------------------------------------------------------------

def enable_mfa(db_path: str, user_id: int, secret: str) -> None:
    with _get_db(db_path) as conn:
        conn.execute(
            "UPDATE users SET totp_secret = ?, mfa_enabled = 1 WHERE id = ?",
            (secret, user_id),
        )


def disable_mfa(db_path: str, user_id: int) -> None:
    with _get_db(db_path) as conn:
        conn.execute(
            "UPDATE users SET totp_secret = NULL, mfa_enabled = 0 WHERE id = ?",
            (user_id,),
        )


def get_mfa_state(db_path: str, user_id: int) -> dict:
    with _get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return {"enabled": False, "secret": None}
    return {"enabled": bool(row["mfa_enabled"]), "secret": row["totp_secret"]}


# ---------------------------------------------------------------------------
# Flask session helpers
# ---------------------------------------------------------------------------

MFA_PENDING_KEY = "_mfa_pending_user_id"
_SETUP_SECRET_KEY = "_mfa_setup_secret"


def start_mfa_challenge(user_id: int) -> None:
    """Hold the user in MFA-pending state after a successful password check."""
    session[MFA_PENDING_KEY] = user_id
    session.permanent = True


def complete_mfa_challenge() -> None:
    """Promote a pending MFA session to a fully authenticated one."""
    user_id = session.pop(MFA_PENDING_KEY, None)
    if user_id is None:
        abort(403)
    session["user_id"] = user_id


def pending_mfa_user_id() -> int | None:
    return session.get(MFA_PENDING_KEY)
