"""Application configuration: constants, compiled regexes, and secret-key loading."""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "meat_ensemble.db"
APP_URL = os.environ.get("APP_URL", "http://localhost:9999").rstrip("/")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 10
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# Pre-computed dummy hash for constant-time login checks on unknown usernames.
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


def _load_secret_key() -> str:
    """Return the Flask secret key.

    Priority: SECRET_KEY env var → .secret_key file → auto-generate and persist.
    Auto-generated keys are written to .secret_key with mode 0o600 so they survive
    process restarts without requiring manual configuration.
    """
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    key_file = BASE_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_hex(32)
    key_file.write_text(key)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key
