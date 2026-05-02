from __future__ import annotations

import sqlite3

from flask import g

from config import DATABASE


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT UNIQUE NOT NULL,
            email           TEXT UNIQUE NOT NULL,
            password_hash   TEXT NOT NULL,
            is_admin        INTEGER NOT NULL DEFAULT 0,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until    INTEGER,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS polls (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            poll_type   TEXT NOT NULL CHECK (poll_type IN ('date', 'restaurant')),
            vote_mode   TEXT NOT NULL CHECK (vote_mode IN ('single', 'approval')),
            status      TEXT NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open', 'closed')),
            created_by  INTEGER NOT NULL REFERENCES users(id),
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS poll_options (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id   INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            label     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS votes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id    INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            option_id  INTEGER NOT NULL REFERENCES poll_options(id) ON DELETE CASCADE,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (poll_id, option_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS restaurants (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            cuisine      TEXT NOT NULL DEFAULT '',
            description  TEXT NOT NULL DEFAULT '',
            address      TEXT NOT NULL DEFAULT '',
            suggested_by INTEGER NOT NULL REFERENCES users(id),
            status       TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'approved', 'rejected')),
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_votes_poll   ON votes(poll_id);
        CREATE INDEX IF NOT EXISTS idx_options_poll ON poll_options(poll_id);
        """
    )
    db.commit()
