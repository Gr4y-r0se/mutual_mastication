"""AWS SES email delivery: HTML template builder and application-level send functions."""
from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


def _client():
    return boto3.client("ses", region_name=os.environ.get("SES_REGION", "eu-west-1"))


def _from_address() -> str:
    return os.environ.get("SES_FROM_ADDRESS", "")


def _app_url() -> str:
    return os.environ.get("APP_URL", "http://localhost:9999").rstrip("/")


def _all_emails(db) -> list[str]:
    return [r["email"] for r in db.execute("SELECT email FROM users").fetchall()]


# ── HTML email template ────────────────────────────────────────────────────────

def _email_html(title: str, body_html: str, cta_text: str = "", cta_url: str = "") -> str:
    """Build a full HTML email document in the club's brand style.

    Renders a dark header, burgundy title band, white body, an optional CTA button,
    and a footer disclaimer. Uses string concatenation rather than f-strings to avoid
    conflicts with CSS curly braces.
    """
    cta_block = ""
    if cta_text and cta_url:
        cta_block = (
            '<tr><td style="padding:0 32px 28px;">'
            '<a href="' + cta_url + '" '
            'style="display:inline-block;background:#8a1d1d;color:#ffffff;'
            'font-family:Georgia,\'Times New Roman\',serif;font-size:15px;'
            'font-weight:bold;text-decoration:none;padding:12px 28px;'
            'border-radius:6px;">'
            + cta_text +
            '</a></td></tr>'
        )

    return (
        '<!doctype html>'
        '<html lang="en">'
        '<head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>' + title + '</title>'
        '</head>'
        '<body style="margin:0;padding:0;background:#ede5da;'
        'font-family:Georgia,\'Times New Roman\',serif;">'

        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%"'
        ' style="background:#ede5da;padding:32px 16px;">'
        '<tr><td align="center">'

        '<table role="presentation" cellpadding="0" cellspacing="0"'
        ' style="max-width:560px;width:100%;">'

        # Header
        '<tr><td style="background:#2a1a14;border-radius:10px 10px 0 0;padding:22px 32px;">'
        '<p style="margin:0;font-size:20px;font-weight:bold;color:#faf6f1;'
        'letter-spacing:0.02em;">🥩 The Meat Ensemble</p>'
        '<p style="margin:5px 0 0;font-size:11px;color:rgba(250,246,241,0.5);'
        'text-transform:uppercase;letter-spacing:0.08em;">A monthly steak club</p>'
        '</td></tr>'

        # Title band
        '<tr><td style="background:#5e1212;padding:18px 32px;">'
        '<h1 style="margin:0;font-size:19px;color:#faf6f1;'
        'font-family:Georgia,\'Times New Roman\',serif;font-weight:normal;'
        'letter-spacing:0.01em;">' + title + '</h1>'
        '</td></tr>'

        # Body
        '<tr><td style="background:#ffffff;padding:28px 32px 8px;'
        'font-size:15px;color:#2a1a14;line-height:1.65;">'
        + body_html +
        '</td></tr>'

        # CTA (optional)
        + cta_block +

        # Footer
        '<tr><td style="background:#ffffff;border-radius:0 0 10px 10px;'
        'padding:16px 32px 28px;border-top:1px solid #e2d5c8;">'
        '<p style="margin:0;font-size:12px;color:#6b5a52;line-height:1.6;">'
        "You're receiving this because you're a member of The Meat Ensemble.<br>"
        'Questions? Contact your group admin.'
        '</p></td></tr>'

        '</table>'  # inner
        '</td></tr>'
        '</table>'  # outer
        '</body></html>'
    )


# ── Send helper ────────────────────────────────────────────────────────────────

def _send(to: list[str], subject: str, text: str, html: str = "") -> bool:
    """Send an email via SES with plain-text and optional HTML bodies.

    Returns ``True`` on success, ``False`` if SES isn't configured (missing sender
    or empty recipient list) or if SES raises an error.
    """
    sender = _from_address()
    if not sender or not to:
        logger.warning("SES not configured or no recipients — skipping email")
        return False
    try:
        body: dict = {"Text": {"Data": text, "Charset": "UTF-8"}}
        if html:
            body["Html"] = {"Data": html, "Charset": "UTF-8"}
        _client().send_email(
            Source=sender,
            Destination={"ToAddresses": to},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": body,
            },
        )
        return True
    except (ClientError, BotoCoreError) as exc:
        logger.error("SES send_email failed: %s", exc)
        return False


# ── Email functions ────────────────────────────────────────────────────────────

def send_poll_created(poll: dict, db) -> bool:
    """Notify all members that a new poll has been opened."""
    url = f"{_app_url()}/poll/{poll['id']}"
    end = poll.get("end_date") or "no end date set"
    title = f"New poll: {poll['title']}"

    # Plain text
    body_text = (
        f"A new poll has been created on The Meat Ensemble.\n\n"
        f"  {poll['title']}\n"
    )
    if poll.get("description"):
        body_text += f"\n  {poll['description']}\n"
    body_text += f"\n  Closes: {end}\n\nCast your vote: {url}\n"

    # HTML
    desc_block = (
        f'<p style="margin:0 0 12px;color:#6b5a52;">{poll["description"]}</p>'
        if poll.get("description") else ""
    )
    body_html = (
        '<p style="margin:0 0 16px;">A new poll has been opened — head over and cast your vote.</p>'
        '<table role="presentation" cellpadding="0" cellspacing="0"'
        ' style="background:#faf6f1;border:1px solid #e2d5c8;border-radius:8px;'
        'padding:16px 20px;margin:0 0 20px;width:100%;">'
        '<tr><td>'
        f'<p style="margin:0 0 6px;font-size:17px;font-weight:bold;color:#2a1a14;">{poll["title"]}</p>'
        + desc_block +
        f'<p style="margin:0;font-size:13px;color:#6b5a52;">Closes: {end}</p>'
        '</td></tr>'
        '</table>'
    )

    html = _email_html(title, body_html, cta_text="Cast your vote", cta_url=url)
    return _send(_all_emails(db), title, body_text, html)


def send_polls_closing_soon(polls: list, db) -> bool:
    """Notify all members that one or more polls close within the next 24 hours."""
    base = _app_url()
    subject = (
        f"Poll closing soon — {polls[0]['title']}"
        if len(polls) == 1
        else "Polls closing soon — vote before tomorrow"
    )
    title = "Vote before it closes"

    # Plain text
    lines = "\n".join(
        f"  • {p['title']} — closes {p['end_date']} — {base}/poll/{p['id']}"
        for p in polls
    )
    body_text = (
        "The following polls close within the next 24 hours. Make sure you've voted!\n\n"
        f"{lines}\n\n"
        f"Head to {base} to cast your vote.\n"
    )

    # HTML
    rows = "".join(
        '<tr>'
        '<td style="padding:10px 0;border-bottom:1px solid #e2d5c8;">'
        f'<p style="margin:0 0 3px;font-weight:bold;color:#2a1a14;">{p["title"]}</p>'
        f'<p style="margin:0;font-size:13px;color:#6b5a52;">Closes {p["end_date"]}</p>'
        '</td>'
        '<td style="padding:10px 0 10px 16px;border-bottom:1px solid #e2d5c8;'
        'text-align:right;white-space:nowrap;vertical-align:middle;">'
        f'<a href="{base}/poll/{p["id"]}" style="color:#8a1d1d;font-size:13px;">Vote →</a>'
        '</td>'
        '</tr>'
        for p in polls
    )
    body_html = (
        '<p style="margin:0 0 16px;">The following poll'
        + ('s close' if len(polls) > 1 else ' closes')
        + ' within the next 24 hours. Make sure you\'ve had your say.</p>'
        '<table role="presentation" cellpadding="0" cellspacing="0"'
        ' style="width:100%;border-top:1px solid #e2d5c8;margin:0 0 16px;">'
        + rows +
        '</table>'
    )

    html = _email_html(title, body_html, cta_text="Go to polls", cta_url=base)
    return _send(_all_emails(db), subject, body_text, html)


def send_polls_closed(polls: list, db) -> bool:
    """Notify all members that one or more polls have closed and results are available."""
    base = _app_url()
    subject = (
        f"Poll closed — {polls[0]['title']}"
        if len(polls) == 1
        else "Polls closed — see the results"
    )
    title = "The results are in"

    # Plain text
    lines = "\n".join(
        f"  • {p['title']} — {base}/poll/{p['id']}"
        for p in polls
    )
    body_text = (
        "The following polls have now closed. See the results below.\n\n"
        f"{lines}\n\n"
        f"Visit {base} for full details.\n"
    )

    # HTML
    rows = "".join(
        '<tr>'
        '<td style="padding:10px 0;border-bottom:1px solid #e2d5c8;">'
        f'<p style="margin:0;font-weight:bold;color:#2a1a14;">{p["title"]}</p>'
        '</td>'
        '<td style="padding:10px 0 10px 16px;border-bottom:1px solid #e2d5c8;'
        'text-align:right;white-space:nowrap;vertical-align:middle;">'
        f'<a href="{base}/poll/{p["id"]}" style="color:#8a1d1d;font-size:13px;">See results →</a>'
        '</td>'
        '</tr>'
        for p in polls
    )
    body_html = (
        '<p style="margin:0 0 16px;">Voting has closed on the following poll'
        + ('s' if len(polls) > 1 else '')
        + '. Click through to see the final results.</p>'
        '<table role="presentation" cellpadding="0" cellspacing="0"'
        ' style="width:100%;border-top:1px solid #e2d5c8;margin:0 0 16px;">'
        + rows +
        '</table>'
    )

    html = _email_html(title, body_html, cta_text="View all polls", cta_url=base)
    return _send(_all_emails(db), subject, body_text, html)


def send_password_reset(to_email: str, reset_url: str) -> bool:
    """Send a password-reset link to the specified email address (expires in 1 hour)."""
    subject = "Reset your password — The Meat Ensemble"
    title = "Reset your password"

    # Plain text
    body_text = (
        "Someone requested a password reset for your Meat Ensemble account.\n\n"
        f"Reset your password (link expires in 1 hour):\n{reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email.\n"
    )

    # HTML
    body_html = (
        '<p style="margin:0 0 16px;">'
        "Someone requested a password reset for your Meat Ensemble account."
        '</p>'
        '<p style="margin:0 0 24px;font-size:13px;color:#6b5a52;">'
        "This link expires in 1 hour. If you didn't request a reset, "
        "you can safely ignore this email — your password won't change."
        '</p>'
    )

    html = _email_html(title, body_html, cta_text="Reset my password", cta_url=reset_url)
    return _send([to_email], subject, body_text, html)
