#!/usr/bin/env python3
"""Hourly poll notification script — run via systemd timer.

Sends 24-hour warnings for polls closing soon, auto-closes expired polls,
and sends closure notifications. Multiple polls triggering at the same time
are batched into a single email.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import get_db
from email_service import send_polls_closing_soon, send_polls_closed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run() -> None:
    with app.app_context():
        db = get_db()
        now = datetime.utcnow()
        soon = now + timedelta(hours=24)
        now_s = now.strftime("%Y-%m-%d %H:%M:%S")
        soon_s = soon.strftime("%Y-%m-%d %H:%M:%S")

        # Polls closing within 24 hours — send warning if not already sent
        closing = db.execute(
            "SELECT id, title, description, end_date FROM polls "
            "WHERE status = 'open' AND end_date IS NOT NULL "
            "AND end_date <= ? AND end_date > ? AND notified_24h = 0",
            (soon_s, now_s),
        ).fetchall()
        if closing:
            send_polls_closing_soon(list(closing), db)
            ids = [p["id"] for p in closing]
            db.execute(
                f"UPDATE polls SET notified_24h = 1 WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
            db.commit()
            logger.info("24h warning sent for %d poll(s)", len(closing))

        # Polls past their end_date — auto-close and notify
        expired = db.execute(
            "SELECT id, title, description, end_date FROM polls "
            "WHERE status = 'open' AND end_date IS NOT NULL AND end_date <= ?",
            (now_s,),
        ).fetchall()
        if expired:
            send_polls_closed(list(expired), db)
            ids = [p["id"] for p in expired]
            db.execute(
                f"UPDATE polls SET status = 'closed' WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
            db.commit()
            logger.info("Auto-closed %d poll(s)", len(expired))


if __name__ == "__main__":
    run()
