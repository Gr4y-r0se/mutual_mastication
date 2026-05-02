# 🥩 The Meat Ensemble

A small, secure Flask app for running a monthly steak club: members vote on
**dates** and **restaurants**, and admins manage polls and members.

## Features

- Account registration and login with hashed passwords
- Two voting modes per poll
  - **Approval** — tick every option that works (best for dates)
  - **Single choice** — one favourite (best for restaurants)
- Members can change their vote until the poll is closed
- Admin tools: create / close / reopen / delete polls, promote or demote
  members, unlock locked accounts
- The very first registered user is auto-promoted to admin

## Running it

```bash
cd meat_ensemble
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000/. Register the first account — that user
becomes the admin and can start creating polls.

## Production deployment

Don't run `python app.py` in production. Instead:

```bash
pip install gunicorn
SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
SECURE_COOKIES=1 \
gunicorn --bind 127.0.0.1:8000 --workers 3 app:app
```

Put it behind a reverse proxy (nginx, Caddy) terminating HTTPS. The app
already trusts a single layer of `X-Forwarded-*` headers via `ProxyFix`.

Environment variables:

- `SECRET_KEY` — required in production. If unset, a key is generated and
  persisted to `.secret_key` (mode 0600) on first run.
- `SECURE_COOKIES=1` — set this when serving over HTTPS so the session
  cookie carries the `Secure` flag.

## Security posture

| Concern | Mitigation |
|---|---|
| Password storage | `werkzeug.security.generate_password_hash` (PBKDF2-SHA256, per-user salt) |
| SQL injection | Every query uses parameterised `?` placeholders, including the `IN (…)` list |
| CSRF | `Flask-WTF`'s `CSRFProtect` is enabled globally; every form includes a `csrf_token` |
| XSS | Jinja2 autoescape is on for all `.html` templates; user input is never rendered with the `\|safe` filter |
| Session hijacking | Cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` when `SECURE_COOKIES=1` |
| Session fixation | `session.clear()` is called before setting `user_id` on login |
| Brute-force login | Per-account lockout after 5 consecutive failures (15-min cooldown) |
| Username enumeration | Login runs a hash check against a dummy hash even when the user is missing, equalising response time |
| Open redirect | The `next` query param is only honoured if it's a relative same-origin path |
| Resource exhaustion | `MAX_CONTENT_LENGTH = 64 KB`; per-field length and count limits |
| Clickjacking | `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'` |
| MIME sniffing | `X-Content-Type-Options: nosniff` |
| Privilege escalation | Admin checks via `@admin_required`; admins cannot toggle their own role; first-user-admin only triggers when the users table is empty |
| Vote integrity | `votes` has a `UNIQUE (poll_id, option_id, user_id)`; submitted option ids are validated against the poll before insert; a user's previous votes are deleted in the same request |

### Things to add for a real deployment

This is a deliberately small codebase. For real-world use you'd want:

- HTTPS with HSTS (handle at the reverse proxy)
- Email verification + password reset flow
- A real rate limiter (e.g. `Flask-Limiter` on `/login` and `/register`)
- 2FA (TOTP) for admin accounts
- Structured audit logging of admin actions
- Backups of `meat_ensemble.db`
- A proper migration tool if the schema grows (`alembic`)

## File layout

```
meat_ensemble/
├── app.py                 # Flask app, routes, auth, schema
├── requirements.txt
├── README.md
└── templates/
    ├── base.html          # Layout, nav, styles
    ├── index.html
    ├── login.html
    ├── register.html
    ├── profile.html
    ├── poll.html
    ├── admin.html
    ├── admin_new_poll.html
    └── error.html
```

The SQLite database (`meat_ensemble.db`) and the `.secret_key` file are
created next to `app.py` on first run.
