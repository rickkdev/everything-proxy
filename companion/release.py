"""The single outgoing serializer. UI preview and MCP both call this; nothing else may release data.

A fact leaves only if it is approved locally, its source is still stored and in retention, it was
checked under the current policy, and the exact outgoing text passes the final privacy check with
request-scoped aliases applied.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import sqlite3

from . import db as store
from . import privacy

MAX_RESULTS = 25
MAX_QUERY_CHARS = 200
MAX_DIGEST_DAYS = 31
CATEGORIES = ("security", "change", "decision", "deadline", "request", "summary")
COVERAGE_LIMITS = [
    "Gmail only; attachments, images, OCR, and links are not read.",
    "Only English messages are processed; other languages are withheld locally.",
    "Only facts the user approved locally are returned.",
    "Aliases reduce exposure but do not guarantee anonymity.",
]


class ReleaseError(ValueError):
    """Fixed, content-free error codes for callers."""


class ReleaseSession:
    """Per-client scope for aliases and source references. Refs are sequential, so two fresh
    sessions issuing the same request over the same snapshot serialize identically."""

    def __init__(self) -> None:
        self.aliases = privacy.AliasSession()
        self.refs: dict[str, str] = {}
        self.by_fact: dict[str, str] = {}

    def ref(self, fact_id: str) -> str:
        if fact_id not in self.by_fact:
            ref = f"src_{len(self.refs) + 1}"
            self.by_fact[fact_id] = ref
            self.refs[ref] = fact_id
        return self.by_fact[fact_id]


class ReleaseService:
    def __init__(self, db: sqlite3.Connection, channel: str) -> None:
        self.db = db
        self.channel = channel

    # ----- tools ---------------------------------------------------------------------------

    def get_status(self, session: ReleaseSession) -> dict:
        counts = {row["state"]: row["n"] for row in self.db.execute("SELECT state, COUNT(*) AS n FROM messages GROUP BY state")}
        review = self.db.execute("SELECT COUNT(*) FROM facts WHERE status = 'proposed'").fetchone()[0]
        coverage = json.loads(store.get_meta(self.db, "coverage", "{}") or "{}")
        result = {
            "snapshot": self._snapshot(),
            "sync": {
                "connected": store.get_meta(self.db, "import_complete") == "1",
                "error": store.get_meta(self.db, "sync_error", "") or None,
                "import_window_days": coverage.get("window_days"),
                "import_capped_at": coverage.get("max_messages") if coverage.get("capped") else None,
            },
            "backlog": {
                "waiting_for_body": counts.get("pending_body", 0),
                "waiting_for_local_model": counts.get("pending_model", 0),
                "failed_processing": counts.get("failed", 0),
                "facts_awaiting_local_review": review,
                "withheld_messages": counts.get("withheld", 0),
            },
            "limits": COVERAGE_LIMITS,
        }
        self._log("get_status", 0, 0)
        return result

    def get_digest(self, session: ReleaseSession, since: str | None = None, checkpoint: str | None = None,
                   after_checkpoint: str | None = None) -> dict:
        if sum(value is not None for value in (since, checkpoint, after_checkpoint)) != 1:
            raise ReleaseError("provide exactly one of since, checkpoint, after_checkpoint")
        if checkpoint is not None:
            saved = self._checkpoint(checkpoint)
            rows = self._facts_by_id(json.loads(saved["fact_ids"]))
            checkpoint_id, start, end = saved["id"], saved["since"], saved["until"]
        else:
            if after_checkpoint is not None:
                start = self._checkpoint(after_checkpoint)["created_at"]
                rows = self.db.execute(
                    "SELECT facts.*, messages.received_at FROM facts JOIN messages ON messages.id = facts.message_id"
                    " WHERE facts.status = 'approved' AND facts.reviewed_at > ? ORDER BY messages.received_at DESC, facts.id",
                    (start,),
                ).fetchall()
            else:
                start = self._parse_day(since).isoformat()
                rows = self.db.execute(
                    "SELECT facts.*, messages.received_at FROM facts JOIN messages ON messages.id = facts.message_id"
                    " WHERE facts.status = 'approved' AND messages.received_at >= ? ORDER BY messages.received_at DESC, facts.id",
                    (start,),
                ).fetchall()
            rows = rows[:MAX_RESULTS]
            end = store.get_meta(self.db, "last_sync_at", "") or ""
            ids = [row["id"] for row in rows]
            checkpoint_id = "dg_" + hashlib.sha256(json.dumps([start, end, ids]).encode()).hexdigest()[:16]
            with store.transaction(self.db):
                self.db.execute(
                    "INSERT OR IGNORE INTO digest_checkpoints VALUES (?, ?, ?, ?, ?)",
                    (checkpoint_id, start, end, json.dumps(ids), store.now()),
                )
        released = self._release(session, rows, "get_digest")
        released["checkpoint"] = checkpoint_id
        return released

    def search_facts(self, session: ReleaseSession, query: str, since: str | None = None,
                     until: str | None = None, categories: list[str] | None = None, limit: int = 10) -> dict:
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            raise ReleaseError("query must be 1-200 characters")
        if not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
            raise ReleaseError(f"limit must be 1-{MAX_RESULTS}")
        if categories and any(item not in CATEGORIES for item in categories):
            raise ReleaseError("unknown category")
        terms = [term for term in re.findall(r"\w+", query.casefold()) if len(term) > 2][:8]
        sql = ("SELECT facts.*, messages.received_at FROM facts JOIN messages ON messages.id = facts.message_id"
               " WHERE facts.status = 'approved'")
        params: list[object] = []
        if terms:
            sql += " AND (" + " OR ".join("lower(facts.search_text) LIKE ?" for _ in terms) + ")"
            params += [f"%{term}%" for term in terms]
        if since:
            sql += " AND messages.received_at >= ?"
            params.append(self._parse_day(since).isoformat())
        if until:
            sql += " AND messages.received_at < ?"
            params.append((self._parse_day(until) + timedelta(days=1)).isoformat())
        if categories:
            sql += " AND facts.category IN (" + ",".join("?" for _ in categories) + ")"
            params += categories
        rows = self.db.execute(sql + " ORDER BY messages.received_at DESC, facts.id", params).fetchall()
        rows.sort(key=lambda row: -sum(term in row["search_text"].casefold() for term in terms))
        return self._release(session, rows[:limit], "search_facts")

    def get_source_facts(self, session: ReleaseSession, ref: str) -> dict:
        fact_id = session.refs.get(ref) if isinstance(ref, str) else None
        if fact_id is None:
            raise ReleaseError("unknown reference")
        anchor = self.db.execute("SELECT gmail_thread_id FROM facts WHERE id = ?", (fact_id,)).fetchone()
        if anchor is None:
            return self._release(session, [], "get_source_facts")
        rows = self.db.execute(
            "SELECT facts.*, messages.received_at FROM facts JOIN messages ON messages.id = facts.message_id"
            " WHERE facts.gmail_thread_id = ? AND facts.status = 'approved' ORDER BY messages.received_at DESC, facts.id",
            (anchor["gmail_thread_id"],),
        ).fetchall()
        return self._release(session, rows[:MAX_RESULTS], "get_source_facts")

    # ----- gate ----------------------------------------------------------------------------

    def check_fact(self, row: sqlite3.Row, session: ReleaseSession) -> tuple[str | None, str]:
        """Return (withheld reason or None, rendered text). Used for review too."""
        rendered = session.aliases.render(row["template"])
        if row["status"] != "approved":
            return "not_approved", rendered
        if row["policy_version"] != privacy.POLICY_VERSION:
            return "policy_changed", rendered
        if json.loads(row["privacy_flags"]):
            return "flagged_identifier", rendered
        if privacy.final_check(rendered, session.aliases):
            return "final_privacy_check", rendered
        return None, rendered

    def _release(self, session: ReleaseSession, rows: list[sqlite3.Row], tool: str) -> dict:
        facts = []
        withheld: dict[str, int] = {}
        for row in rows:
            reason, rendered = self.check_fact(row, session)
            if reason:
                withheld[reason] = withheld.get(reason, 0) + 1
                continue
            facts.append({
                "ref": session.ref(row["id"]),
                "category": row["category"],
                "date": row["received_at"][:10],
                "text": rendered,
            })
        self._log(tool, len(facts), sum(withheld.values()))
        return {"snapshot": self._snapshot(), "facts": facts, "withheld": withheld, "truncated": len(rows) >= MAX_RESULTS}

    def _snapshot(self) -> dict:
        pending = self.db.execute(
            "SELECT COUNT(*) FROM messages WHERE state IN ('pending_body', 'pending_model', 'failed')"
        ).fetchone()[0]
        return {
            "policy_version": privacy.POLICY_VERSION,
            "last_sync_at": store.get_meta(self.db, "last_sync_at", "") or None,
            "pending_messages": pending,
        }

    def _facts_by_id(self, ids: list[str]) -> list[sqlite3.Row]:
        rows = []
        for fact_id in ids:
            row = self.db.execute(
                "SELECT facts.*, messages.received_at FROM facts JOIN messages ON messages.id = facts.message_id WHERE facts.id = ?",
                (fact_id,),
            ).fetchone()
            if row is not None:
                rows.append(row)
        return rows

    def _checkpoint(self, checkpoint_id: object) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM digest_checkpoints WHERE id = ?", (checkpoint_id,)).fetchone() \
            if isinstance(checkpoint_id, str) else None
        if row is None:
            raise ReleaseError("unknown checkpoint")
        return row

    @staticmethod
    def _parse_day(value: object) -> datetime:
        try:
            day = date.fromisoformat(str(value)[:10])
        except ValueError as error:
            raise ReleaseError("dates must be YYYY-MM-DD") from error
        floor = datetime.now(timezone.utc).date() - timedelta(days=MAX_DIGEST_DAYS)
        return datetime.combine(max(day, floor), datetime.min.time(), tzinfo=timezone.utc)

    def _log(self, tool: str, released: int, withheld: int) -> None:
        with store.transaction(self.db):
            self.db.execute(
                "INSERT INTO disclosures VALUES (?, ?, ?, ?, ?)", (store.now(), self.channel, tool, released, withheld)
            )
