"""
The Meat Ensemble - Monthly Steak Club

Security posture:
  - Passwords hashed with PBKDF2-SHA256 via Werkzeug
  - CSRF protection on every state-changing endpoint (Flask-WTF)
  - All SQL is parameterised - no string-built queries
  - Session cookies: HttpOnly, SameSite=Lax, Secure (when SECURE_COOKIES=1)
  - Account lockout after repeated failed login attempts
  - Constant-ish-time password verification (dummy hash on missing user)
  - Open-redirect protection on the post-login `next` parameter
  - Strict security headers + CSP
  - Body size cap, per-field length validation, and allow-list input checks
"""
from __future__ import annotations

import os
from datetime import timedelta

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from config import _load_secret_key
from database import init_db
from routes import register_blueprints


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=_load_secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SECURE_COOKIES", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        WTF_CSRF_TIME_LIMIT=3600,
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    CSRFProtect(app)
    register_blueprints(app)
    with app.app_context():
        init_db()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9999, debug=False)
