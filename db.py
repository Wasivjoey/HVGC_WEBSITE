"""Database layer for the Harbour View Gospel Chapel website.

SQLite via the standard library — zero external dependencies. Everything a
non-technical editor changes (text, livestream link, blog posts, photos,
presentations) lives here and is edited through the admin panel.
"""

import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "hvgc.db"))

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

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    slug       TEXT NOT NULL UNIQUE,
    summary    TEXT,
    body       TEXT,
    image      TEXT,
    published  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gallery (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    filename   TEXT NOT NULL,
    caption    TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS presentations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    url         TEXT,          -- external link (Google Slides, YouTube, etc.)
    filename    TEXT,          -- or an uploaded file (PDF/PPTX)
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    event_date  TEXT NOT NULL,  -- YYYY-MM-DD
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


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    _seed(conn)
    conn.close()


def _seed(conn):
    # Default settings (only fills in missing keys).
    for k, v in DEFAULT_SETTINGS.items():
        row = conn.execute("SELECT 1 FROM settings WHERE key = ?", (k,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()

    # Seed an admin editor account once.
    if conn.execute("SELECT 1 FROM users WHERE username = ?", ("admin",)).fetchone() is None:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("admin", generate_password_hash("admin123", method="pbkdf2:sha256")),
        )
        conn.commit()

    # Seed a couple of upcoming sample events once.
    if conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"] == 0:
        from datetime import date, timedelta
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

    # Seed a welcome blog post once.
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
