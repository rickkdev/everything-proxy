#!/usr/bin/env python3
"""Verify idempotent local message updates with synthetic metadata."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import threading
import tempfile
import time

from local_store import LocalStore, MessageUpdate


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    later = now + timedelta(days=30)
    with tempfile.NamedTemporaryFile(suffix=".sqlite") as file:
        store = LocalStore(file.name)
        store.set_policy("policy-v1", now.isoformat())
        store.set_rule_version("rules-v1")
        base = MessageUpdate(
            account_id="synthetic-account",
            provider_message_id="synthetic-message-1",
            provider_thread_id="synthetic-thread-1",
            source_hash="source-v1",
            received_at=now.isoformat(),
            retention_until=later.isoformat(),
            in_scope=True,
            relevance="include",
            reason_code="direct_request",
            rule_version="rules-v1",
            policy_hash="policy-v1",
        )
        assert store.apply_update(base) is True
        initial = store.snapshot()
        thread = next(row for row in initial["threads"] if row["provider_thread_id"] == "synthetic-thread-1")
        message = next(row for row in initial["messages"] if row["provider_message_id"] == "synthetic-message-1")
        assert thread["context_revision"] == 1
        assert message["source_revision"] == 1

        assert store.apply_update(base) is False
        assert len(store.snapshot()["messages"]) == 1

        revised = MessageUpdate(**{**base.__dict__, "source_hash": "source-v2"})
        assert store.apply_update(revised) is True
        changed = store.snapshot()
        thread = next(row for row in changed["threads"] if row["provider_thread_id"] == "synthetic-thread-1")
        message = next(row for row in changed["messages"] if row["provider_message_id"] == "synthetic-message-1")
        assert thread["context_revision"] == 2
        assert message["source_revision"] == 2

        moved = MessageUpdate(**{**revised.__dict__, "provider_thread_id": "synthetic-thread-2"})
        assert store.apply_update(moved) is True
        moved_snapshot = store.snapshot()
        assert all(row["provider_thread_id"] != "synthetic-thread-1" for row in moved_snapshot["threads"])
        thread = next(row for row in moved_snapshot["threads"] if row["provider_thread_id"] == "synthetic-thread-2")
        message = next(row for row in moved_snapshot["messages"] if row["provider_message_id"] == "synthetic-message-1")
        assert thread["context_revision"] == 2
        assert message["source_revision"] == 3

        assert store.set_policy("policy-v2", now.isoformat()) is True
        assert store.snapshot()["filter_decisions"] == []
        try:
            store.apply_update(moved)
        except ValueError as error:
            assert str(error) == "stale or missing policy version"
        else:
            raise AssertionError("stale policy result was accepted")
        assert store.set_policy("policy-v2", now.isoformat()) is False
        current_policy = MessageUpdate(**{**moved.__dict__, "policy_hash": "policy-v2"})
        assert store.apply_update(current_policy) is False

        assert store.set_policy("policy-v3", now.isoformat()) is True
        entered = threading.Event()
        proceed = threading.Event()
        outcome: list[str] = []

        def apply_stale_result() -> None:
            concurrent = LocalStore(file.name)
            entered.set()
            try:
                assert proceed.wait(timeout=2)
                concurrent.apply_update(current_policy)
            except ValueError as error:
                outcome.append(str(error))
            finally:
                concurrent.close()

        store.db.execute("BEGIN IMMEDIATE")
        worker = threading.Thread(target=apply_stale_result)
        worker.start()
        assert entered.wait(timeout=2)
        proceed.set()
        time.sleep(0.1)
        store.db.execute("COMMIT")
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert outcome == ["stale or missing policy version"]
        current_policy = MessageUpdate(**{**current_policy.__dict__, "policy_hash": "policy-v3"})
        assert store.apply_update(current_policy) is False
        assert store.set_rule_version("rules-v2") is True
        try:
            store.apply_update(current_policy)
        except ValueError as error:
            assert str(error) == "stale or missing rule version"
        else:
            raise AssertionError("stale rule result was accepted")
        current_rules = MessageUpdate(**{**current_policy.__dict__, "rule_version": "rules-v2"})
        assert store.apply_update(current_rules) is False

        expired = MessageUpdate(**{**current_rules.__dict__, "provider_message_id": "synthetic-expired", "retention_until": now.isoformat()})
        assert store.apply_update(expired) is True
        assert store.cleanup_expired(now.isoformat()) == 1
        final = store.snapshot()
        assert len(final["messages"]) == 1
        thread = next(row for row in final["threads"] if row["provider_thread_id"] == "synthetic-thread-2")
        assert thread["context_revision"] == 4
        store.close()
    print(json.dumps({"concurrent_policy_change": "serialized before stale result check", "policy_change": "invalidated and stale result rejected", "replay": "idempotent", "retention": "expired source removed", "rule_change": "invalidated and stale result rejected", "source_change": "revisioned"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
