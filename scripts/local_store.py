"""Persist local message metadata and deterministic filter decisions."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import uuid
from collections.abc import Iterator


@dataclass(frozen=True)
class MessageUpdate:
    account_id: str
    provider_message_id: str
    provider_thread_id: str
    source_hash: str
    received_at: str
    retention_until: str
    in_scope: bool
    relevance: str
    reason_code: str
    rule_version: str
    policy_hash: str


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


@contextmanager
def _write_transaction(db: sqlite3.Connection) -> Iterator[None]:
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


class LocalStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            database_path = Path(path).expanduser()
            database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if os.name != "nt":
                if database_path.parent.stat().st_mode & 0o077:
                    raise PermissionError("database directory must be accessible only to the current user")
        self.db = sqlite3.connect(
            ":memory:" if path == ":memory:" else str(database_path), timeout=5
        )
        if path != ":memory:" and os.name != "nt":
            os.chmod(database_path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                provider_thread_id TEXT NOT NULL,
                context_revision INTEGER NOT NULL,
                UNIQUE(account_id, provider_thread_id)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                provider_message_id TEXT NOT NULL,
                thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                source_hash TEXT NOT NULL,
                source_revision INTEGER NOT NULL,
                received_at TEXT NOT NULL,
                retention_until TEXT NOT NULL,
                in_scope INTEGER NOT NULL CHECK(in_scope IN (0, 1)),
                UNIQUE(account_id, provider_message_id)
            );
            CREATE TABLE IF NOT EXISTS filter_decisions (
                message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                source_revision INTEGER NOT NULL,
                relevance TEXT NOT NULL CHECK(relevance IN ('include', 'deprioritize', 'skip', 'inspect')),
                reason_code TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                PRIMARY KEY(message_id, source_revision, rule_version)
            );
            CREATE TABLE IF NOT EXISTS policy_versions (
                id TEXT PRIMARY KEY,
                policy_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS active_policy (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                policy_id TEXT NOT NULL REFERENCES policy_versions(id)
            );
            CREATE TABLE IF NOT EXISTS active_rule_version (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                version TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def apply_update(self, update: MessageUpdate) -> bool:
        received_at = _timestamp(update.received_at).isoformat()
        retention_until = _timestamp(update.retention_until).isoformat()
        if not all((update.account_id, update.provider_message_id, update.provider_thread_id, update.source_hash)):
            raise ValueError("account, provider IDs, and source hash are required")
        if update.relevance not in {"include", "deprioritize", "skip", "inspect"}:
            raise ValueError("invalid relevance")
        with _write_transaction(self.db):
            active_policy = self.db.execute(
                "SELECT policy_versions.policy_hash FROM active_policy JOIN policy_versions ON policy_versions.id = active_policy.policy_id WHERE singleton = 1"
            ).fetchone()
            active_rule = self.db.execute(
                "SELECT version FROM active_rule_version WHERE singleton = 1"
            ).fetchone()
            if active_policy is None or active_policy["policy_hash"] != update.policy_hash:
                raise ValueError("stale or missing policy version")
            if active_rule is None or active_rule["version"] != update.rule_version:
                raise ValueError("stale or missing rule version")
            thread = self.db.execute(
                "SELECT id, context_revision FROM threads WHERE account_id = ? AND provider_thread_id = ?",
                (update.account_id, update.provider_thread_id),
            ).fetchone()
            if thread is None:
                thread_id = uuid.uuid4().hex
                self.db.execute(
                    "INSERT INTO threads VALUES (?, ?, ?, 1)",
                    (thread_id, update.account_id, update.provider_thread_id),
                )
                thread_revision = 1
            else:
                thread_id = thread["id"]
                thread_revision = thread["context_revision"]

            message = self.db.execute(
                "SELECT id, thread_id, source_hash, source_revision, in_scope FROM messages WHERE account_id = ? AND provider_message_id = ?",
                (update.account_id, update.provider_message_id),
            ).fetchone()
            changed = message is None
            if message is None:
                message_id = uuid.uuid4().hex
                source_revision = 1
                self.db.execute(
                    "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        message_id,
                        update.account_id,
                        update.provider_message_id,
                        thread_id,
                        update.source_hash,
                        source_revision,
                        received_at,
                        retention_until,
                        int(update.in_scope),
                    ),
                )
            else:
                message_id = message["id"]
                moved_threads = message["thread_id"] != thread_id
                changed = (
                    message["source_hash"] != update.source_hash
                    or message["in_scope"] != int(update.in_scope)
                    or moved_threads
                )
                if changed:
                    source_revision = message["source_revision"] + 1
                    if moved_threads:
                        self.db.execute(
                            "UPDATE threads SET context_revision = context_revision + 1 WHERE id = ?",
                            (message["thread_id"],),
                        )
                    self.db.execute(
                        "UPDATE messages SET thread_id = ?, source_hash = ?, source_revision = ?, received_at = ?, retention_until = ?, in_scope = ? WHERE id = ?",
                        (
                            thread_id,
                            update.source_hash,
                            source_revision,
                            received_at,
                            retention_until,
                            int(update.in_scope),
                            message_id,
                        ),
                    )
                    if moved_threads:
                        self.db.execute(
                            "DELETE FROM threads WHERE id = ? AND NOT EXISTS (SELECT 1 FROM messages WHERE thread_id = ?)",
                            (message["thread_id"], message["thread_id"]),
                        )
                else:
                    source_revision = message["source_revision"]
                    self.db.execute(
                        "UPDATE messages SET retention_until = ? WHERE id = ?",
                        (retention_until, message_id),
                    )

            if changed and (thread is not None or message is not None):
                self.db.execute(
                    "UPDATE threads SET context_revision = context_revision + 1 WHERE id = ?",
                    (thread_id,),
                )
                self.db.execute("DELETE FROM filter_decisions WHERE message_id = ?", (message_id,))
            self.db.execute(
                "INSERT OR REPLACE INTO filter_decisions VALUES (?, ?, ?, ?, ?)",
                (message_id, source_revision, update.relevance, update.reason_code, update.rule_version),
            )
            return changed

    def set_policy(self, policy_hash: str, created_at: str) -> bool:
        timestamp = _timestamp(created_at).isoformat()
        if not policy_hash:
            raise ValueError("policy hash is required")
        with _write_transaction(self.db):
            current = self.db.execute(
                "SELECT policy_versions.policy_hash FROM active_policy JOIN policy_versions ON policy_versions.id = active_policy.policy_id WHERE singleton = 1"
            ).fetchone()
            if current is not None and current["policy_hash"] == policy_hash:
                return False
            policy_id = uuid.uuid4().hex
            self.db.execute(
                "INSERT INTO policy_versions VALUES (?, ?, ?)",
                (policy_id, policy_hash, timestamp),
            )
            self.db.execute(
                "INSERT INTO active_policy VALUES (1, ?) ON CONFLICT(singleton) DO UPDATE SET policy_id = excluded.policy_id",
                (policy_id,),
            )
            self.db.execute("DELETE FROM filter_decisions")
        return True

    def set_rule_version(self, version: str) -> bool:
        if not version:
            raise ValueError("rule version is required")
        with _write_transaction(self.db):
            current = self.db.execute(
                "SELECT version FROM active_rule_version WHERE singleton = 1"
            ).fetchone()
            if current is not None and current["version"] == version:
                return False
            self.db.execute(
                "INSERT INTO active_rule_version VALUES (1, ?) ON CONFLICT(singleton) DO UPDATE SET version = excluded.version",
                (version,),
            )
            self.db.execute("DELETE FROM filter_decisions")
        return True

    def cleanup_expired(self, now: str) -> int:
        cutoff = _timestamp(now).isoformat()
        with self.db:
            expired = self.db.execute(
                "SELECT id, thread_id FROM messages WHERE retention_until <= ?",
                (cutoff,),
            ).fetchall()
            affected_threads = {row["thread_id"] for row in expired}
            for row in expired:
                self.db.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            for thread_id in affected_threads:
                self.db.execute(
                    "UPDATE threads SET context_revision = context_revision + 1 WHERE id = ?",
                    (thread_id,),
                )
                self.db.execute(
                    "DELETE FROM threads WHERE id = ? AND NOT EXISTS (SELECT 1 FROM messages WHERE thread_id = ?)",
                    (thread_id, thread_id),
                )
            return len(expired)

    def snapshot(self) -> dict[str, list[dict[str, object]]]:
        return {
            "threads": [dict(row) for row in self.db.execute("SELECT * FROM threads ORDER BY id")],
            "messages": [dict(row) for row in self.db.execute("SELECT * FROM messages ORDER BY id")],
            "filter_decisions": [
                dict(row) for row in self.db.execute("SELECT * FROM filter_decisions ORDER BY message_id")
            ],
        }
