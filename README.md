# 🥩 The Meat Ensemble

A small, secure Flask web app for running a monthly steak club. Members vote on
**dates** and **restaurants**; admins manage polls, members, and the restaurant
catalogue.

## Features

### Polls
- **Date polls** — members see a calendar view for the relevant month(s), click
  to mark the dates that work for them, and see how many others have picked each
  date at a glance
- **Restaurant polls** — options are drawn from the admin-approved restaurant
  catalogue; displayed as large clickable cards with vote bars
- Two voting modes per poll:
  - **Approval** — tick every option that works (recommended for dates)
  - **Single choice** — one favourite (recommended for restaurants)
- Hovering over a date cell or a restaurant's vote count shows a tooltip of who has voted for it
- Members can update their vote any time until the poll is closed
- Admins can create, close, reopen, and delete polls

### Restaurant catalogue
- The catalogue page leads with a card grid of all approved restaurants, each
  showing name, cuisine, address, notes, and an optional website link
- Any logged-in member can suggest a restaurant (name, cuisine, address, website
  link, notes); the suggestion form sits below the approved list
- Admins review suggestions and approve or reject them
- Approved restaurants become selectable options when creating a restaurant poll

### Users
- Self-registration is **disabled** — the first account (which becomes admin) is
  created via `/register`; all subsequent members are added by an admin
- Admins can add members, grant or revoke admin privileges, unlock locked
  accounts, and delete members

### Email notifications
Emails are sent via **AWS SES** and delivered as both plain text and a branded
HTML version that matches the site's visual design (dark header, cream body,
burgundy call-to-action buttons, Georgia serif font throughout).

| Trigger | Recipients |
|---|---|
| New poll created | All members |
| Poll closing within 24 hours | All members |
| Poll closed | All members |
| Password reset requested | The requesting member only |

See [Environment variables](#environment-variables) for the SES configuration
required to enable sending.

### Mobile
- The app detects mobile browsers via `User-Agent` and serves a separate
  mobile-optimised layout: CSS-only hamburger menu, 48 px minimum tap targets,
  16 px inputs (prevents iOS zoom), and horizontally scrollable data tables
- All admin views use the desktop layout regardless of device

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:9999/`. If no accounts exist you will be redirected to
`/register` to create the first admin account.

## Production deployment

### 1 — Run with gunicorn

```bash
pip install gunicorn
mkdir -p /run/meat_ensemble

SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
SECURE_COOKIES=1 \
gunicorn \
  --workers 4 \
  --bind unix:/run/meat_ensemble/app.sock \
  --forwarded-allow-ips '*' \
  app:app
```

### 2 — Set up nginx

An nginx config is included at [`nginx.conf`](nginx.conf). Copy it to
`/etc/nginx/sites-available/meat_ensemble`, fill in your domain and the
absolute path to the project, then enable it:

```bash
ln -s /etc/nginx/sites-available/meat_ensemble /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

The config handles:
- HTTP → HTTPS redirect with a Let's Encrypt ACME challenge passthrough
- TLS 1.2/1.3 with Mozilla Intermediate cipher suite
- HSTS (`max-age=63072000; includeSubDomains; preload`)
- Per-IP rate limiting on `/login` (10 req/min, burst 5) on top of the app's
  own lockout
- `client_max_body_size 64k` matching the app's `MAX_CONTENT_LENGTH`
- Static files served directly by nginx with far-future cache headers

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | Auto-generated, persisted to `.secret_key` (0600) | Flask session signing key — set explicitly in production |
| `SECURE_COOKIES` | `0` | Set to `1` when serving over HTTPS to add the `Secure` flag to session cookies |
| `SES_REGION` | `eu-west-1` | AWS region for the SES client |
| `SES_FROM_ADDRESS` | *(unset — email disabled)* | Verified SES sender address; emails are silently skipped if unset |
| `APP_URL` | `http://localhost:9999` | Base URL embedded in outbound email links |

## Frontend

All CSS and JavaScript lives in `static/` — no inline styles or scripts in any
template.

### CSS

| File | Purpose |
|---|---|
| `static/css/base.css` | Design tokens (CSS custom properties), shared components: pills, vote cards, calendar, voter tooltip, restaurant grid, flash messages |
| `static/css/desktop.css` | Desktop layout — flex header/nav, 780 px centred `<main>`, standard-sized form controls and buttons |
| `static/css/mobile.css` | Mobile layout — pure-CSS hamburger nav, touch-friendly sizing, `.tbl-scroll` horizontal table wrapper |

**Design tokens**

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#faf6f1` | Page background (cream) |
| `--ink` | `#2a1a14` | Body text (dark brown) |
| `--accent` | `#8a1d1d` | Buttons, links, active states (burgundy) |
| `--accent-dark` | `#5e1212` | Hover/pressed state |
| `--muted` | `#6b5a52` | Secondary text, meta information |
| `--line` | `#e2d5c8` | Borders and dividers |
| `--ok` | `#1d6b3a` | Success states (green) |

Body font: `Georgia, "Times New Roman", serif`

### JavaScript

| File | Purpose |
|---|---|
| `static/js/poll.js` | Poll page — `toggleVote()` for calendar cells, vote-card selection sync, voter hover tooltip |
| `static/js/cal-picker.js` | Admin poll creation — interactive date-picker calendar (`renderCal`, `toggleDate`, `calPrev`, `calNext`, `onTypeChange`) |
| `static/js/mobile.js` | Wraps data tables in `.tbl-scroll` scroll containers on page load |

### Adding page-specific styles or scripts

Both base templates expose `{% block extra_css %}` (in `<head>`) and
`{% block extra_js %}` (before `</body>`):

```html
{% block extra_js %}
  <script src="{{ url_for('static', filename='js/my-page.js') }}"></script>
{% endblock %}
```

## Security posture

| Concern | Mitigation |
|---|---|
| Password storage | PBKDF2-SHA256 via `werkzeug.security`, per-user 16-byte salt |
| SQL injection | Every query uses parameterised `?` placeholders, including variable-length `IN (…)` lists |
| CSRF | `Flask-WTF` `CSRFProtect` enabled globally; every state-changing form includes a `csrf_token` |
| XSS | Jinja2 autoescape active on all templates; user data is never rendered with `\|safe`; dynamic JS values use `\|tojson` rather than bare interpolation into JS strings |
| Session fixation | `session.clear()` called before setting `user_id` on login |
| Session security | Cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` when `SECURE_COOKIES=1` |
| Brute-force login | Per-account lockout after 5 consecutive failures (15-min cooldown); nginx rate limit at the network edge |
| Username enumeration | A dummy hash is always checked when the username is not found, equalising response time |
| Open redirect | `?next=` is only honoured for relative, same-origin paths |
| Clickjacking | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` |
| MIME sniffing | `X-Content-Type-Options: nosniff` |
| HSTS | Set by nginx on HTTPS responses (`max-age=63072000`) |
| Resource exhaustion | `MAX_CONTENT_LENGTH = 64 KB`; per-field length limits on all inputs |
| Privilege escalation | `@admin_required` on every admin route; admins cannot change their own role or delete their own account |
| Vote integrity | `UNIQUE (poll_id, option_id, user_id)` constraint; submitted option IDs validated against the poll before insert; previous votes replaced atomically in the same request |
| Cache poisoning | `Vary: User-Agent` on all responses prevents a cache from serving the mobile layout to a desktop browser or vice versa |

### Known limitations / future work

- Passwords for new members must be shared out-of-band (no automated welcome email)
- No 2FA for admin accounts
- No structured audit log of admin actions
- Schema migrations are handled inline: `CREATE TABLE IF NOT EXISTS` covers new
  tables; column additions use `ALTER TABLE … ADD COLUMN` with a silent no-op if
  the column already exists
- SQLite is the only supported database

## File layout

```
├── app.py                        # App factory + entrypoint
├── config.py                     # Constants, secret-key loader
├── database.py                   # SQLite connection, schema init
├── auth.py                       # current_user(), @login_required, @admin_required
├── email_service.py              # AWS SES email sending (plain text + branded HTML)
├── routes/
│   ├── __init__.py               # Blueprint registration, error handlers, security headers
│   ├── auth_routes.py            # /register  /login  /logout  /profile  /forgot-password  /reset-password
│   ├── poll_routes.py            # /  /poll/<id>  /poll/<id>/vote
│   ├── admin_routes.py           # /admin/*
│   └── restaurant_routes.py      # /restaurants  /restaurants/suggest
├── templates/
│   ├── base.html                 # Desktop layout (links css/base.css + css/desktop.css)
│   ├── base_mobile.html          # Mobile layout (hamburger nav, large tap targets)
│   ├── index.html                # Poll list
│   ├── login.html
│   ├── register.html             # Bootstrap-only (first admin account)
│   ├── profile.html
│   ├── change_password.html
│   ├── forgot_password.html
│   ├── reset_password.html
│   ├── poll.html                 # Calendar view (date polls) or card view (restaurant polls)
│   ├── restaurants.html          # Approved catalogue + suggestion form
│   ├── admin.html                # Dashboard: polls, members
│   ├── admin_new_poll.html       # Calendar picker (date) or checkbox list (restaurant)
│   ├── admin_new_user.html       # Add member form
│   ├── admin_restaurants.html    # Approve / reject suggestions
│   └── error.html
├── static/
│   ├── css/
│   │   ├── base.css              # Design tokens + shared components
│   │   ├── desktop.css           # Desktop layout
│   │   └── mobile.css            # Mobile layout + hamburger nav
│   ├── js/
│   │   ├── poll.js               # Calendar toggle, vote-card sync, voter tooltip
│   │   ├── cal-picker.js         # Admin date-picker calendar
│   │   └── mobile.js             # Table scroll-wrapper initialisation
│   └── favicon.ico
├── terraform/                    # EC2 + SES infrastructure
├── nginx.conf                    # Production nginx reverse-proxy config
└── requirements.txt
```

The SQLite database (`meat_ensemble.db`) and `.secret_key` are created next to
`app.py` on first run and are excluded from version control via `.gitignore`.
