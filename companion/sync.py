"""Gmail import, incremental history sync, filtering, and local model processing.

Every step is durable and idempotent: messages are keyed by Gmail ID, the history checkpoint
advances only after its work is stored, and model processing state is tracked per message so a
failed or interrupted run resumes instead of losing mail.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3
import threading
import time
import uuid

from filter_rules import MessageMetadata, RuleSet, evaluate_message, evaluate_metadata

from . import db as store
from . import privacy, text
from .gmail import AuthExpired, GmailClient, GmailUnavailable, HistoryExpired
from .model import Extractor, category

WINDOW_DAYS = 30
DEFAULT_MAX_MESSAGES = 100
POLL_SECONDS = 300


def _received_at(message: dict) -> datetime:
    return datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, tz=timezone.utc)


class Gateway:
    def __init__(self, db: sqlite3.Connection, client: GmailClient | None, extractor: Extractor | None,
                 max_messages: int = DEFAULT_MAX_MESSAGES, window_days: int = WINDOW_DAYS) -> None:
        self.db = db
        self.client = client
        self.extractor = extractor
        self.max_messages = max_messages
        self.window_days = window_days
        self.refresh_lock = threading.Lock()
        self.rerun = False
        self.progress = {"phase": "idle", "detail": ""}

    # ----- rules ---------------------------------------------------------------------------

    def rules(self) -> RuleSet:
        rows = self.db.execute("SELECT address, action FROM sender_overrides").fetchall()
        return RuleSet(
            excluded_senders=frozenset(row["address"] for row in rows if row["action"] == "exclude"),
            included_senders=frozenset(row["address"] for row in rows if row["action"] == "include"),
        )

    def _metadata(self, row: sqlite3.Row | dict) -> MessageMetadata:
        tracked = self.db.execute(
            "SELECT 1 FROM facts WHERE gmail_thread_id = ? AND status = 'approved' LIMIT 1",
            (row["gmail_thread_id"],),
        ).fetchone() is not None
        return MessageMetadata(
            sender=row["sender_address"], list_id=row["list_id"], subject=row["subject"],
            labels=frozenset(label.lower() for label in json.loads(row["labels"])),
            tracked_thread=tracked, language=row["language"],
        )

    # ----- sync ----------------------------------------------------------------------------

    def refresh(self) -> dict:
        """One full refresh. Concurrent callers get 'busy' instead of a second job."""
        if not self.refresh_lock.acquire(blocking=False):
            self.rerun = True
            return {"started": False, "reason": "refresh already running; it will run again when done"}
        try:
            self.rerun = True
            while self.rerun:
                self.rerun = False
                if self.client is not None:
                    self._sync()
                self.fetch_bodies()
                self.process()
                self.cleanup()
            return {"started": True}
        finally:
            self.progress = {"phase": "idle", "detail": ""}
            self.refresh_lock.release()

    def _sync(self) -> None:
        try:
            if store.get_meta(self.db, "import_complete") != "1":
                self._initial_import()
            else:
                try:
                    self._incremental()
                except HistoryExpired:
                    self._initial_import(reconcile=True)
            with store.transaction(self.db):
                store.set_meta(self.db, "last_sync_at", store.now())
                store.set_meta(self.db, "sync_error", "")
        except AuthExpired:
            self._sync_error("auth_expired")
        except GmailUnavailable:
            self._sync_error("offline")

    def _sync_error(self, code: str) -> None:
        with store.transaction(self.db):
            store.set_meta(self.db, "sync_error", code)

    def _initial_import(self, reconcile: bool = False) -> None:
        assert self.client is not None
        self.progress = {"phase": "import", "detail": "listing recent messages"}
        history_id = self.client.profile()["historyId"]
        query = f"newer_than:{self.window_days}d -in:drafts -in:chats"
        seen: list[str] = []
        page_token = None
        while len(seen) < self.max_messages:
            page = self.client.list_messages(query, page_token, min(100, self.max_messages - len(seen)))
            seen.extend(item["id"] for item in page.get("messages", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        for index, gmail_id in enumerate(seen):
            self.progress = {"phase": "import", "detail": f"metadata {index + 1}/{len(seen)}"}
            exists = self.db.execute("SELECT 1 FROM messages WHERE gmail_id = ?", (gmail_id,)).fetchone()
            if exists and not reconcile:
                continue
            try:
                self.upsert(self.client.get_message(gmail_id, full=False))
            except LookupError:
                self.remove(gmail_id)
        with store.transaction(self.db):
            if reconcile:
                kept = set(seen)
                for row in self.db.execute("SELECT gmail_id FROM messages").fetchall():
                    if row["gmail_id"] not in kept:
                        self._delete(row["gmail_id"])
            store.set_meta(self.db, "history_id", history_id)
            store.set_meta(self.db, "import_complete", "1")
            store.set_meta(self.db, "coverage", {
                "window_days": self.window_days, "max_messages": self.max_messages,
                "listed": len(seen), "capped": len(seen) >= self.max_messages,
                "since": (datetime.now(timezone.utc) - timedelta(days=self.window_days)).date().isoformat(),
            })

    def _incremental(self) -> None:
        assert self.client is not None
        self.progress = {"phase": "sync", "detail": "reading Gmail history"}
        start = store.get_meta(self.db, "history_id")
        changed: set[str] = set()
        deleted: set[str] = set()
        page_token = None
        latest = start
        while True:
            page = self.client.list_history(start, page_token)
            latest = page.get("historyId", latest)
            for record in page.get("history", []):
                for key in ("messagesAdded", "labelsAdded", "labelsRemoved"):
                    changed.update(item["message"]["id"] for item in record.get(key, []))
                deleted.update(item["message"]["id"] for item in record.get("messagesDeleted", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        for gmail_id in sorted(changed - deleted):
            try:
                self.upsert(self.client.get_message(gmail_id, full=False))
            except LookupError:
                deleted.add(gmail_id)
        for gmail_id in deleted:
            self.remove(gmail_id)
        with store.transaction(self.db):
            store.set_meta(self.db, "history_id", latest)

    def upsert(self, message: dict) -> None:
        """Store metadata and the rule decision. Replays of the same state change nothing."""
        payload = message.get("payload", {})
        header = text.headers(payload)
        received = _received_at(message)
        labels = sorted(message.get("labelIds", []))
        row = {
            "gmail_id": message["id"], "gmail_thread_id": message["threadId"],
            "sender": header.get("from", ""), "sender_address": text.sender_address(header.get("from", "")),
            "subject": header.get("subject", "")[:500], "labels": json.dumps(labels),
            "list_id": header.get("list-id"), "language": None,
            "participants": json.dumps(text.participants(header)),
        }
        decision = evaluate_metadata(self._metadata(row), self.rules())
        in_window = received >= datetime.now(timezone.utc) - timedelta(days=self.window_days)
        with store.transaction(self.db):
            existing = self.db.execute("SELECT * FROM messages WHERE gmail_id = ?", (message["id"],)).fetchone()
            if not in_window and existing is None:
                return
            if existing and existing["labels"] == row["labels"] and existing["reason"] == decision.reason.value:
                return
            state = "pending_body" if decision.fetch_body else "filtered"
            if existing and not decision.fetch_body:
                self.db.execute(
                    "UPDATE facts SET status = 'superseded' WHERE message_id = ? AND status IN ('proposed', 'approved')",
                    (existing["id"],),
                )
            values = (
                row["gmail_thread_id"], received.isoformat(), (received + timedelta(days=self.window_days)).isoformat(),
                row["sender"], row["sender_address"], row["subject"], row["labels"], row["list_id"],
                row["participants"], decision.relevance.value, decision.reason.value, decision.rule_version,
                state, store.now(),
            )
            if existing:
                self.db.execute(
                    "UPDATE messages SET gmail_thread_id=?, received_at=?, retention_until=?, sender=?, sender_address=?,"
                    " subject=?, labels=?, list_id=?, participants=?, relevance=?, reason=?, rule_version=?,"
                    " state=?, updated_at=?, privacy_hold=NULL, model_relevance=NULL, error=NULL WHERE id = ?",
                    (*values, existing["id"]),
                )
            else:
                self.db.execute(
                    "INSERT INTO messages (gmail_thread_id, received_at, retention_until, sender, sender_address,"
                    " subject, labels, list_id, participants, relevance, reason, rule_version, state, updated_at,"
                    " id, gmail_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (*values, uuid.uuid4().hex, message["id"]),
                )

    def remove(self, gmail_id: str) -> None:
        with store.transaction(self.db):
            self._delete(gmail_id)

    def _delete(self, gmail_id: str) -> None:
        # Facts cascade with the message, so nothing derived from it stays eligible.
        self.db.execute("DELETE FROM messages WHERE gmail_id = ?", (gmail_id,))

    # ----- local processing ----------------------------------------------------------------

    def fetch_bodies(self) -> None:
        rows = self.db.execute("SELECT * FROM messages WHERE state = 'pending_body' ORDER BY received_at DESC").fetchall()
        for index, row in enumerate(rows):
            self.progress = {"phase": "fetch", "detail": f"message bodies {index + 1}/{len(rows)}"}
            body = row["body"]
            coverage = json.loads(row["coverage"])
            language = row["language"]
            if body is None:
                if self.client is None:
                    continue
                try:
                    full = self.client.get_message(row["gmail_id"], full=True)
                except LookupError:
                    self.remove(row["gmail_id"])
                    continue
                except (GmailUnavailable, AuthExpired):
                    return
                payload = full.get("payload", {})
                body, coverage = text.body_text(payload)
                language = text.detect_language(f"{row['subject']}\n{body}", text.headers(payload).get("content-language"))
            meta = self._metadata(row)
            decision = evaluate_message(
                MessageMetadata(meta.sender, meta.list_id, meta.subject, meta.labels, meta.tracked_thread, language),
                body, self.rules(),
            )
            if decision.relevance.value not in ("include", "inspect"):
                state = "filtered"
            elif decision.privacy_hold:
                state = "withheld"
            else:
                state = "pending_model"
            with store.transaction(self.db):
                self.db.execute(
                    "UPDATE messages SET body=?, coverage=?, language=?, relevance=?, reason=?, privacy_hold=?,"
                    " state=?, updated_at=? WHERE id = ?",
                    (body, json.dumps(coverage), language, decision.relevance.value, decision.reason.value,
                     decision.privacy_hold.value if decision.privacy_hold else None, state, store.now(), row["id"]),
                )

    def process(self) -> None:
        if self.extractor is None:
            return
        while True:
            pending = self.db.execute(
                "SELECT gmail_thread_id FROM messages WHERE state = 'pending_model' ORDER BY received_at DESC LIMIT 1"
            ).fetchone()
            if pending is None:
                return
            remaining = self.db.execute("SELECT COUNT(DISTINCT gmail_thread_id) FROM messages WHERE state = 'pending_model'").fetchone()[0]
            self.progress = {"phase": "model", "detail": f"{remaining} threads waiting for local extraction"}
            self.process_thread(pending["gmail_thread_id"])

    def process_thread(self, thread_id: str) -> None:
        assert self.extractor is not None
        rows = self.db.execute(
            "SELECT * FROM messages WHERE gmail_thread_id = ? AND body IS NOT NULL"
            " AND state IN ('pending_model', 'processed') ORDER BY received_at",
            (thread_id,),
        ).fetchall()
        pending_ids = [row["id"] for row in rows if row["state"] == "pending_model"]
        thread = [{
            "id": row["id"], "sent_at": row["received_at"], "sender": row["sender"],
            "subject": row["subject"], "body": row["body"],
        } for row in rows]
        try:
            extraction = self.extractor.extract(thread)
        except Exception as error:  # the model runs out of process; any failure keeps mail pending
            with store.transaction(self.db):
                self.db.executemany(
                    "UPDATE messages SET state='failed', error=?, updated_at=? WHERE id = ?",
                    [(type(error).__name__, store.now(), message_id) for message_id in pending_ids],
                )
            return
        participants = [tuple(item) for row in rows for item in json.loads(row["participants"])]
        anchor = rows[-1]
        with store.transaction(self.db):
            if extraction.relevance == "include" and extraction.facts:
                self._store_facts(thread_id, anchor, extraction, participants)
            self.db.executemany(
                "UPDATE messages SET state='processed', model_relevance=?, error=?, updated_at=? WHERE id = ?",
                [(extraction.relevance, ",".join(extraction.rejected) or None, store.now(), message_id)
                 for message_id in pending_ids],
            )

    def _store_facts(self, thread_id: str, anchor: sqlite3.Row, extraction, participants) -> None:
        """Replace the thread's current state without duplicating facts that did not change."""
        current = {
            row["search_text"].casefold(): row
            for row in self.db.execute(
                "SELECT * FROM facts WHERE gmail_thread_id = ? AND status IN ('proposed', 'approved')", (thread_id,)
            )
        }
        kept: set[str] = set()
        for fact in extraction.facts:
            template, flags = privacy.tokenize(self.db, fact.text, participants)
            neutral = privacy.search_text(template)
            if neutral.casefold() in current:
                kept.add(current[neutral.casefold()]["id"])
                continue
            fact_id = uuid.uuid4().hex
            kept.add(fact_id)
            self.db.execute(
                "INSERT INTO facts (id, message_id, gmail_thread_id, template, search_text, evidence, category,"
                " status, privacy_flags, model, prompt_version, policy_version, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?, ?)",
                (fact_id, anchor["id"], thread_id, template, neutral,
                 json.dumps([{"message_id": mid, "quote": quote} for mid, quote in fact.evidence]),
                 category(anchor["reason"], fact.text), json.dumps(flags), self.extractor.name,
                 extraction.prompt_version, privacy.POLICY_VERSION, store.now()),
            )
        for row in current.values():
            if row["id"] not in kept:
                self.db.execute("UPDATE facts SET status = 'superseded' WHERE id = ?", (row["id"],))

    def retry_failed(self) -> int:
        with store.transaction(self.db):
            return self.db.execute("UPDATE messages SET state='pending_model', error=NULL WHERE state='failed'").rowcount

    def set_sender_override(self, address: str, action: str | None) -> None:
        """Local sender correction, then re-evaluate that sender's messages."""
        address = address.strip().casefold()
        with store.transaction(self.db):
            if action is None:
                self.db.execute("DELETE FROM sender_overrides WHERE address = ?", (address,))
            else:
                self.db.execute(
                    "INSERT INTO sender_overrides VALUES (?, ?) ON CONFLICT(address) DO UPDATE SET action = excluded.action",
                    (address, action),
                )
            self.db.execute("UPDATE messages SET reason = '' WHERE sender_address = ?", (address,))
        for row in self.db.execute("SELECT * FROM messages WHERE sender_address = ?", (address,)).fetchall():
            self.upsert({
                "id": row["gmail_id"], "threadId": row["gmail_thread_id"], "labelIds": json.loads(row["labels"]),
                "internalDate": str(int(datetime.fromisoformat(row["received_at"]).timestamp() * 1000)),
                "payload": {"headers": [{"name": "From", "value": row["sender"]},
                                        {"name": "Subject", "value": row["subject"]},
                                        *([{"name": "List-Id", "value": row["list_id"]}] if row["list_id"] else [])]},
            })
            self.db.execute("UPDATE messages SET participants = ? WHERE id = ?", (row["participants"], row["id"]))

    def cleanup(self) -> int:
        """Drop messages past retention unless their thread still has an approved open fact."""
        with store.transaction(self.db):
            return self.db.execute(
                "DELETE FROM messages WHERE retention_until < ? AND gmail_thread_id NOT IN"
                " (SELECT gmail_thread_id FROM facts WHERE status = 'approved')",
                (store.now(),),
            ).rowcount

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            self.refresh()
            stop.wait(POLL_SECONDS)
