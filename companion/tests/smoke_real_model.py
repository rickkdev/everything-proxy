"""Real local model + real GLiNER over a synthetic mailbox, then a real MCP stdio round trip.

Run: .venv-eval/bin/python -m companion.tests.smoke_real_model
No Gmail access: the Gmail API is the synthetic fake. Writes only to a temporary data directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

home = tempfile.mkdtemp(prefix="ep-smoke-")
os.environ["EVERYTHING_PROXY_HOME"] = home

from companion import ROOT  # noqa: E402
from companion import db as store  # noqa: E402
from companion.model import BonsaiExtractor  # noqa: E402
from companion.release import ReleaseService, ReleaseSession  # noqa: E402
from companion.sync import Gateway  # noqa: E402
from companion.tests.fakes import FakeGmail, fake_client, gmail_message  # noqa: E402
from companion.tests.test_companion import mailbox  # noqa: E402  (also installs the test detector)
from companion import privacy  # noqa: E402

privacy._detector = None  # use the real rules+GLiNER detector


def main() -> int:
    api: FakeGmail = mailbox()
    api.add(gmail_message("m8", "t1", "Morgan Lee <morgan@northwind.test>", "Re: Launch checklist",
                          "Quick update: we moved the checklist review to Monday, April 20.", days_ago=1), record=False)
    started = time.perf_counter()
    extractor = BonsaiExtractor(port=18239)
    gateway = Gateway(store.connect(), fake_client(api), extractor)
    try:
        gateway.refresh()
    finally:
        extractor.stop()
    elapsed = time.perf_counter() - started
    db = gateway.db
    rows = db.execute("SELECT gmail_id, relevance, reason, privacy_hold, model_relevance, state, error FROM messages ORDER BY gmail_id").fetchall()
    fact_rows = db.execute("SELECT * FROM facts").fetchall()
    report = {
        "elapsed_seconds": round(elapsed, 1),
        "messages": [dict(row) for row in rows],
        "facts": [{"status": row["status"], "category": row["category"], "flags": json.loads(row["privacy_flags"]),
                   "outgoing_if_approved": privacy.AliasSession().render(row["template"])} for row in fact_rows],
    }
    for row in fact_rows:
        if not json.loads(row["privacy_flags"]):
            db.execute("UPDATE facts SET status = 'approved', reviewed_at = ? WHERE id = ?", (store.now(), row["id"]))
    preview = ReleaseService(db, "preview").get_digest(ReleaseSession(), since="2000-01-01")

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_digest", "arguments": {"since": "2000-01-01"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_raw_email", "arguments": {}}},
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "companion", "mcp"], cwd=ROOT, input="".join(json.dumps(item) + "\n" for item in requests),
        capture_output=True, text=True, timeout=300, env=os.environ,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    mcp_digest = responses[2]["result"]["structuredContent"]
    report["mcp_stdout_lines_all_json"] = len(responses) == 4
    report["mcp_tools"] = [tool["name"] for tool in responses[1]["result"]["tools"]]
    report["mcp_digest"] = mcp_digest
    report["preview_equals_mcp"] = mcp_digest == preview
    report["unknown_tool_is_error"] = responses[3]["result"]["isError"]
    serialized = json.dumps(mcp_digest)
    report["mcp_contains_real_identity"] = any(value in serialized for value in ("Morgan", "northwind", "482913", "@"))
    print(json.dumps(report, indent=2))
    ok = report["preview_equals_mcp"] and not report["mcp_contains_real_identity"] and report["unknown_tool_is_error"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
