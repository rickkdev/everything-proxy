"""Local SQLite store for the companion. Original text and identities never leave it."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from .paths import database_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    gmail_id TEXT NOT NULL UNIQUE,
    gmail_thread_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    retention_until TEXT NOT NULL,
    sender TEXT NOT NULL,
    sender_address TEXT NOT NULL,
    subject TEXT NOT NULL,
    labels TEXT NOT NULL,
    list_id TEXT,
    participants TEXT NOT NULL DEFAULT '[]',
    language TEXT,
    body TEXT,
    coverage TEXT NOT NULL DEFAULT '{}',
    relevance TEXT NOT NULL CHECK(relevance IN ('include', 'deprioritize', 'skip', 'inspect')),
    reason TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    privacy_hold TEXT,
    model_relevance TEXT,
    state TEXT NOT NULL CHECK(state IN ('pending_body', 'pending_model', 'processed', 'withheld', 'filtered', 'failed')),
    error TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_thread ON messages(gmail_thread_id, received_at);
CREATE INDEX IF NOT EXISTS messages_state ON messages(state);
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('person', 'organization')),
    value TEXT NOT NULL,
    UNIQUE(kind, value)
);
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    gmail_thread_id TEXT NOT NULL,
    template TEXT NOT NULL,
    search_text TEXT NOT NULL,
    evidence TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('proposed', 'approved', 'dismissed', 'superseded')),
    privacy_flags TEXT NOT NULL DEFAULT '[]',
    edited INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS facts_status ON facts(status);
CREATE TABLE IF NOT EXISTS sender_overrides (
    address TEXT PRIMARY KEY,
    action TEXT NOT NULL CHECK(action IN ('include', 'exclude'))
);
CREATE TABLE IF NOT EXISTS digest_checkpoints (
    id TEXT PRIMARY KEY,
    since TEXT NOT NULL,
    until TEXT NOT NULL,
    fact_ids TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS disclosures (
    at TEXT NOT NULL,
    channel TEXT NOT NULL,
    tool TEXT NOT NULL,
    released_count INTEGER NOT NULL,
    withheld_count INTEGER NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or database_path()
    fresh = not target.exists()
    db = sqlite3.connect(str(target), timeout=10, check_same_thread=False, isolation_level=None)
    if os.name != "nt":
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(target) + suffix)
            if candidate.exists():
                os.chmod(candidate, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA busy_timeout = 10000")
    if fresh or not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone():
        db.executescript(SCHEMA)
    return db


@contextmanager
def transaction(db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def get_meta(db: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(db: sqlite3.Connection, key: str, value: object) -> None:
    db.execute(
        "INSERT INTO meta VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value if isinstance(value, str) else json.dumps(value)),
    )
