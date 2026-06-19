"""Database layer for the Harbour View Gospel Chapel website.

Supports two backends, chosen automatically:
  * Postgres  — when DATABASE_URL is a postgres:// / postgresql:// URL (psycopg2)
  * SQLite    — otherwise, at DATABASE_PATH (zero-dependency, local dev)

Uploaded sermon files and photos are stored as binary IN the database (a `media`
table), so they survive redeploys on hosts with an ephemeral filesystem and can
be browsed through the gallery without a separate disk.
"""

import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, date

from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "hvgc.db"))

if USE_PG:
    import psycopg2
    import psycopg2.extras

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

-- Binary store for uploaded images and documents.
CREATE TABLE IF NOT EXISTS media (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content_type TEXT NOT NULL,
    filename     TEXT,
    data         BLOB NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    slug           TEXT NOT NULL UNIQUE,
    summary        TEXT,
    body           TEXT,
    image_media_id INTEGER REFERENCES media(id) ON DELETE SET NULL,
    published      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gallery (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id   INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    caption    TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS presentations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT,
    url           TEXT,                 -- external link (Google Slides, YouTube, etc.)
    file_media_id INTEGER REFERENCES media(id) ON DELETE SET NULL,
    file_name     TEXT,                 -- original name for the download
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    event_date  TEXT NOT NULL,
    event_time  TEXT,
    location    TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT,
    body       TEXT NOT NULL,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "church_name": "Harbour View Gospel Chapel",
    "tagline": "An anchor for the soul",
    "hero_verse": "“We have this hope as an anchor for the soul, firm and secure.” — Hebrews 6:19",
    "hero_subtitle": "A welcoming family of believers on the harbour — come and find hope in Jesus Christ.",
    "livestream_url": "",
    "livestream_heading": "This week's live service",
    "welcome_heading": "Welcome home",
    "welcome_body": ("Harbour View Gospel Chapel is a place where everyone is welcome. "
                     "Whether you are exploring faith for the first time or have walked with "
                     "Christ for years, there is a seat for you here. Join us as we worship, "
                     "grow in God's Word, and serve our community together."),
    "service_times": ("Sunday Worship — 9:00 AM & 6:00 PM\n"
                      "Wednesday Bible Study — 7:00 PM\n"
                      "Youth Fellowship — Friday 6:30 PM"),
    "address": "1 Harbour View Road, Seaside",
    "contact_email": "hello@harbourviewchapel.org",
    "contact_phone": "(000) 000-0000",
    "lineup_url": "https://hvgc-lineup.onrender.com/login",
    "footer_note": "© Harbour View Gospel Chapel",
    "giving_heading": "Give",
    "giving_body": ("“Each of you should give what you have decided in your heart to give, "
                    "not reluctantly or under compulsion, for God loves a cheerful giver.” "
                    "(2 Corinthians 9:7)\n\nYour generosity supports the ministry, outreach "
                    "and upkeep of the chapel. Thank you for partnering with us."),
    "giving_url": "",
    "giving_button": "Give online",
    "contact_heading": "Get in touch",
    "contact_body": "Have a question, a prayer request, or want to plan a visit? Send us a message and we'll reply soon.",
}


# --------------------------------------------------------------------- Postgres
def _translate(sql):
    return sql.replace("?", "%s")


class _PGConn:
    def __init__(self, raw):
        self.raw = raw

    @staticmethod
    def _bind(params):
        # bytea: psycopg2 needs binary values wrapped.
        out = []
        for p in params:
            if isinstance(p, (bytes, bytearray, memoryview)):
                out.append(psycopg2.Binary(p))
            else:
                out.append(p)
        return out

    def execute(self, sql, params=()):
        cur = self.raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(_translate(sql), self._bind(params))
        return cur

    def executemany(self, sql, seq):
        cur = self.raw.cursor()
        cur.executemany(_translate(sql), [self._bind(p) for p in seq])
        cur.close()

    def executescript(self, sql):
        cur = self.raw.cursor()
        cur.execute(sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
                       .replace("BLOB", "BYTEA"))
        cur.close()

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def get_db():
    if USE_PG:
        return _PGConn(psycopg2.connect(DATABASE_URL))
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def execute_returning_id(conn, sql, params=()):
    if USE_PG:
        cur = conn.execute(sql.rstrip().rstrip(";") + " RETURNING id", params)
        return cur.fetchone()["id"]
    return conn.execute(sql, params).lastrowid


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


_INIT_LOCK_KEY = 514317


def _connect_with_retry(attempts=15, delay=2):
    last = None
    for i in range(attempts):
        try:
            return get_db()
        except Exception as e:
            last = e
            if i < attempts - 1:
                print(f"[db] not ready ({e}); retry in {delay}s", flush=True)
                time.sleep(delay)
    raise last


def init_db():
    conn = _connect_with_retry()
    locked = False
    try:
        if USE_PG:
            conn.execute("SELECT pg_advisory_lock(?)", (_INIT_LOCK_KEY,))
            locked = True
        conn.executescript(SCHEMA)
        conn.commit()
        _seed(conn)
    finally:
        if locked:
            try:
                conn.execute("SELECT pg_advisory_unlock(?)", (_INIT_LOCK_KEY,))
                conn.commit()
            except Exception:
                pass
        conn.close()


def _seed(conn):
    for k, v in DEFAULT_SETTINGS.items():
        if conn.execute("SELECT 1 FROM settings WHERE key = ?", (k,)).fetchone() is None:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()

    if conn.execute("SELECT 1 FROM users WHERE username = ?", ("admin",)).fetchone() is None:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("admin", generate_password_hash("admin123", method="pbkdf2:sha256")),
        )
        conn.commit()

    if conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"] == 0:
        today = date.today()
        nxt_sun = today + timedelta(days=(6 - today.weekday()) % 7 or 7)
        conn.executemany(
            "INSERT INTO events (title, description, event_date, event_time, location, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("Sunday Worship Service", "Join us for worship, teaching and fellowship.",
                 nxt_sun.isoformat(), "09:00", "Main Auditorium", now_iso()),
                ("Community Prayer Breakfast", "All welcome — breakfast provided.",
                 (nxt_sun + timedelta(days=6)).isoformat(), "08:00", "Fellowship Hall", now_iso()),
            ],
        )
        conn.commit()

    if conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"] == 0:
        conn.execute(
            "INSERT INTO posts (title, slug, summary, body, published, created_at)"
            " VALUES (?, ?, ?, ?, 1, ?)",
            (
                "Welcome to our new website",
                "welcome-to-our-new-website",
                "We're so glad you found us. Here's what's happening at the chapel.",
                ("We're delighted to launch our new website! Here you'll find our weekly "
                 "live stream, sermons and presentations, news from the chapel, and a "
                 "gallery of life together as a church family.\n\n"
                 "Come and join us this Sunday — there's a warm welcome waiting for you."),
                now_iso(),
            ),
        )
        conn.commit()


def get_settings(conn):
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
