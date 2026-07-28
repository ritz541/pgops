"""SQLite schema + connection for PGOps."""
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", "data/pgops.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL,            -- e.g. '203'
    room_type TEXT NOT NULL,         -- single / double / triple
    UNIQUE(number)
);

CREATE TABLE IF NOT EXISTS beds (
    id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    label TEXT NOT NULL,             -- 'A', 'B'
    rent INTEGER NOT NULL,           -- monthly, INR
    deposit INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',  -- available / held / occupied
    hold_expires_at TEXT,            -- ISO ts; hold auto-expires
    UNIQUE(room_id, label)
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    name TEXT,
    phone TEXT,
    email TEXT,
    telegram_address TEXT,           -- caspian sender address on telegram
    role TEXT NOT NULL DEFAULT 'prospect',  -- prospect / tenant / owner / former
    bed_id INTEGER REFERENCES beds(id),
    join_date TEXT,                  -- ISO date; rent anniversary
    deposit_paid INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,   -- caspian conv id
    person_id INTEGER REFERENCES people(id),
    channel TEXT NOT NULL               -- telegram / email
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,             -- doubles as sequential invoice number
    person_id INTEGER NOT NULL REFERENCES people(id),
    kind TEXT NOT NULL,                 -- booking (rent+deposit) / rent
    amount INTEGER NOT NULL,
    period TEXT,                        -- e.g. '2026-08' for rent
    status TEXT NOT NULL DEFAULT 'due', -- due / claimed / partial / paid / rejected
    amount_received INTEGER DEFAULT 0,
    pdf_path TEXT,
    due_date TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    claimed_at TEXT DEFAULT (datetime('now')),
    screenshot_path TEXT,
    amount_claimed INTEGER,
    owner_decision TEXT,                -- approved / rejected / partial
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id),
    kind TEXT NOT NULL,                 -- id_proof / payment_screenshot
    path TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id),
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open', -- open / fixed / closed
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS events_log (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def get_db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
