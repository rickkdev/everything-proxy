"""Synthetic behavior tests for sync, processing, review, release, HTTP boundary, and MCP."""

from __future__ import annotations

import base64
import http.client
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import unittest

os.environ["EVERYTHING_PROXY_HOME"] = tempfile.mkdtemp(prefix="ep-test-")

from companion import db as store  # noqa: E402
from companion import privacy  # noqa: E402
from companion import text  # noqa: E402
from companion.gmail import AuthExpired, GmailClient, Grant  # noqa: E402
from companion.mcp_server import TOOLS, handle  # noqa: E402
from companion.release import ReleaseService, ReleaseSession  # noqa: E402
from companion.server import Companion, serve  # noqa: E402
from companion.sync import Gateway  # noqa: E402
from companion.tests.fakes import FakeGmail, ScriptedExtractor, TestDetector, fake_client, gmail_message  # noqa: E402

privacy.set_detector(TestDetector())

REQUEST = gmail_message(
    "m1", "t1", "Morgan Lee <morgan@northwind.test>", "Launch checklist",
    "Hi Rick,\nCould you please review the launch checklist by Thursday, April 16? [REQ]\n\n-- \nMorgan Lee\nNorthwind Labs",
    days_ago=3,
)
OUTPUTS = {
    "[REQ]": json.dumps({"relevance": "include", "facts": [{
        "text": "Morgan Lee asks for a review of the launch checklist by Thursday, April 16.",
        "evidence": "review the launch checklist by Thursday, April 16"}]}),
    "[MOVE]": json.dumps({"relevance": "include", "facts": [{
        "text": "The launch checklist review moved to Monday, April 20.",
        "evidence": [{"message_id": "PLACEHOLDER", "quote": "moved the checklist review to Monday, April 20"}]}]}),
    "[ALERT]": json.dumps({"relevance": "include", "facts": [{
        "text": "A sign-in was blocked; recovery code 482913 was issued.",
        "evidence": "A sign-in attempt was blocked"}]}),
    "[BAD]": json.dumps({"relevance": "include", "facts": [{"text": "Invented claim.", "evidence": "not in the email"}]}),
}


def build(api: FakeGmail, extractor: ScriptedExtractor | None = None, max_messages: int = 50) -> Gateway:
    path = Path(tempfile.mkdtemp(prefix="ep-db-")) / "gateway.sqlite3"
    return Gateway(store.connect(path), fake_client(api), extractor or ScriptedExtractor(OUTPUTS), max_messages)


def mailbox() -> FakeGmail:
    api = FakeGmail()
    api.add(REQUEST, record=False)
    api.add(gmail_message("m2", "t2", "Deals <deals@shop.test>", "50% off", "Big sale this week only.",
                          labels=["CATEGORY_PROMOTIONS"]), record=False)
    api.add(gmail_message("m3", "t3", "Accounts <no-reply@accounts.test>", "Security alert: sign-in blocked",
                          "A sign-in attempt was blocked. Your recovery code is 482913. [ALERT]"), record=False)
    api.add(gmail_message("m4", "t4", "Kollegin <k@firma.test>", "Termin",
                          "Bitte schick mir die Unterlagen bis Freitag, das wäre sehr nett von dir und mir hilft es."), record=False)
    api.add(gmail_message("m5", "t5", "HR <hr@corp.test>", "Health update",
                          "Please note my medical leave starts next week."), record=False)
    api.add(gmail_message("m6", "t6", "Random <r@x.test>", "Thoughts", "Here is a claim [BAD] for you to review please."), record=False)
    api.add(gmail_message("m7", "t7", "Old <old@x.test>", "Ancient", "Please review this.", days_ago=45), record=False)
    return api


def state(gateway: Gateway, gmail_id: str):
    return gateway.db.execute("SELECT * FROM messages WHERE gmail_id = ?", (gmail_id,)).fetchone()


def facts(gateway: Gateway, status: str | None = None):
    sql = "SELECT * FROM facts" + (" WHERE status = ?" if status else "")
    return gateway.db.execute(sql, (status,) if status else ()).fetchall()


class SyncAndProcessing(unittest.TestCase):
    def test_import_filters_and_withholds(self) -> None:
        api = mailbox()
        gateway = build(api)
        gateway.refresh()
        self.assertIsNone(state(gateway, "m7"), "messages outside the 30-day window are not imported")
        self.assertEqual(state(gateway, "m2")["relevance"], "deprioritize")
        self.assertEqual(state(gateway, "m2")["state"], "filtered")
        self.assertEqual(state(gateway, "m3")["reason"], "security_alert")
        self.assertEqual(state(gateway, "m4")["privacy_hold"], "unsupported_language")
        self.assertEqual(state(gateway, "m5")["privacy_hold"], "sensitive_topic")
        self.assertEqual(state(gateway, "m6")["error"], "unsupported_evidence")
        self.assertTrue(json.loads(state(gateway, "m1")["coverage"])["attachments_skipped"])
        sent = {call[0] for call in gateway.extractor.calls}
        self.assertNotIn(state(gateway, "m4")["id"], sent, "withheld mail never reaches the model")
        self.assertNotIn(state(gateway, "m5")["id"], sent)
        self.assertTrue(all(method == "GET" for method, path in api.requests if "gmail" in path))

    def test_fact_is_tokenized_and_flagged_locally(self) -> None:
        gateway = build(mailbox())
        gateway.refresh()
        request_fact = [row for row in facts(gateway) if "checklist" in row["template"]][0]
        self.assertNotIn("Morgan", request_fact["template"])
        self.assertEqual(json.loads(request_fact["privacy_flags"]), [])
        alert_fact = [row for row in facts(gateway) if "sign-in" in row["template"]][0]
        self.assertTrue(json.loads(alert_fact["privacy_flags"]), "recovery code must block release")
        self.assertEqual(request_fact["category"], "deadline")

    def test_replay_restart_and_rate_limit_are_idempotent(self) -> None:
        api = mailbox()
        api.rate_limit_once = True
        gateway = build(api)
        gateway.refresh()
        before = (len(facts(gateway)), gateway.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
        store.set_meta(gateway.db, "import_complete", "0")  # simulate a restart mid-import
        gateway.db.execute("UPDATE messages SET state = 'pending_model' WHERE gmail_id = 'm1'")
        gateway.refresh()
        gateway.refresh()
        after = (len(facts(gateway)), gateway.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
        self.assertEqual(before, after)

    def test_import_cap_and_pagination(self) -> None:
        api = FakeGmail()
        for index in range(30):
            api.add(gmail_message(f"p{index}", f"pt{index}", "A <a@a.test>", "Newsletter", "hello"), record=False)
        gateway = build(api, max_messages=25)
        gateway.refresh()
        self.assertEqual(gateway.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 25)
        self.assertTrue(json.loads(store.get_meta(gateway.db, "coverage"))["capped"])

    def test_changed_deadline_supersedes_without_duplicates(self) -> None:
        api = mailbox()
        gateway = build(api)
        gateway.refresh()
        first = [row for row in facts(gateway, "proposed") if "checklist" in row["template"]][0]
        gateway.db.execute("UPDATE facts SET status = 'approved' WHERE id = ?", (first["id"],))
        reply = gmail_message("m8", "t1", "Morgan Lee <morgan@northwind.test>", "Re: Launch checklist",
                              "Update: we moved the checklist review to Monday, April 20. [MOVE]", days_ago=1)
        api.add(reply)
        local_id = None

        def patched(messages):
            nonlocal local_id
            local_id = messages[-1]["id"]
            gateway.extractor.outputs["[MOVE]"] = OUTPUTS["[MOVE]"].replace("PLACEHOLDER", local_id)
            return ScriptedExtractor.extract(gateway.extractor, messages)

        gateway.extractor.extract = patched
        gateway.refresh()
        self.assertEqual(gateway.db.execute("SELECT status FROM facts WHERE id = ?", (first["id"],)).fetchone()[0], "superseded")
        current = [row for row in facts(gateway, "proposed") if "April 20" in row["template"]]
        self.assertEqual(len(current), 1)
        gateway.db.execute("UPDATE messages SET state = 'pending_model' WHERE gmail_id = 'm8'")
        gateway.refresh()
        self.assertEqual(len([row for row in facts(gateway) if "April 20" in row["template"]]), 1)

    def test_deletion_label_change_expired_history_and_offline(self) -> None:
        api = mailbox()
        gateway = build(api)
        gateway.refresh()
        self.assertTrue(facts(gateway))
        api.delete("m1")
        api.relabel("m6", ["SPAM"])
        gateway.refresh()
        self.assertIsNone(state(gateway, "m1"))
        self.assertFalse([row for row in facts(gateway) if "checklist" in row["template"]], "facts leave with their source")
        self.assertEqual(state(gateway, "m6")["reason"], "gmail_spam")
        api.add(gmail_message("m9", "t9", "New <n@x.test>", "Hello", "Please review the plan by Friday."))
        api.expired_before = 10_000
        gateway.refresh()
        self.assertIsNotNone(state(gateway, "m9"), "expired history reconciles the window")
        api.offline = True
        gateway.refresh()
        self.assertEqual(store.get_meta(gateway.db, "sync_error"), "offline")

    def test_sender_override_recovers_and_excludes(self) -> None:
        api = mailbox()
        gateway = build(api)
        gateway.refresh()
        gateway.set_sender_override("deals@shop.test", "include")
        gateway.refresh()
        self.assertEqual(state(gateway, "m2")["reason"], "user_included")
        gateway.set_sender_override("morgan@northwind.test", "exclude")
        gateway.refresh()
        self.assertEqual(state(gateway, "m1")["reason"], "user_excluded")
        self.assertFalse(facts(gateway, "proposed") and [r for r in facts(gateway, "proposed") if "checklist" in r["template"]])

    def test_auth_expiry_is_reported(self) -> None:
        def reject(request):
            return 400, b'{"error": "invalid_grant"}'

        client = GmailClient(Grant("id", "s", "r", "e"), transport=reject)
        with self.assertRaises(AuthExpired):
            client.profile()
        with self.assertRaises(PermissionError):
            fake_client(FakeGmail()).get("messages/abc/modify")


class Release(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = build(mailbox())
        self.gateway.refresh()
        self.service = ReleaseService(self.gateway.db, "test")

    def approve_request(self) -> str:
        row = [row for row in facts(self.gateway) if "checklist" in row["template"]][0]
        self.gateway.db.execute("UPDATE facts SET status = 'approved', reviewed_at = ? WHERE id = ?", (store.now(), row["id"]))
        return row["id"]

    def test_only_approved_checked_facts_leave(self) -> None:
        since = "2000-01-01"
        self.assertEqual(self.service.get_digest(ReleaseSession(), since=since)["facts"], [])
        self.approve_request()
        result = self.service.get_digest(ReleaseSession(), since=since)
        self.assertEqual(len(result["facts"]), 1)
        text = result["facts"][0]["text"]
        self.assertIn("Person A", text)
        self.assertNotIn("Morgan", json.dumps(result))
        self.assertNotIn("northwind", json.dumps(result).casefold())
        self.assertNotIn("m1", json.dumps(result))

    def test_flagged_fact_is_withheld_even_if_approved(self) -> None:
        alert = [row for row in facts(self.gateway) if "sign-in" in row["template"]][0]
        self.gateway.db.execute("UPDATE facts SET status = 'approved' WHERE id = ?", (alert["id"],))
        result = self.service.search_facts(ReleaseSession(), "sign-in blocked")
        self.assertEqual(result["facts"], [])
        self.assertEqual(result["withheld"], {"flagged_identifier": 1})
        self.assertNotIn("482913", json.dumps(result))

    def test_digest_checkpoint_repeats_and_policy_change_withholds(self) -> None:
        self.approve_request()
        first = self.service.get_digest(ReleaseSession(), since="2000-01-01")
        again = self.service.get_digest(ReleaseSession(), checkpoint=first["checkpoint"])
        self.assertEqual(first["facts"], again["facts"])
        self.gateway.db.execute("UPDATE facts SET policy_version = 'old'")
        changed = self.service.get_digest(ReleaseSession(), checkpoint=first["checkpoint"])
        self.assertEqual(changed["facts"], [])
        self.assertEqual(changed["withheld"], {"policy_changed": 1})

    def test_search_cannot_probe_real_identity(self) -> None:
        self.approve_request()
        self.assertEqual(self.service.search_facts(ReleaseSession(), "Morgan Lee")["facts"], [])
        self.assertEqual(len(self.service.search_facts(ReleaseSession(), "launch checklist")["facts"]), 1)

    def test_mcp_tools_are_bounded_and_errors_fixed(self) -> None:
        session = ReleaseSession()
        names = {tool["name"] for tool in TOOLS}
        self.assertEqual(names, {"get_status", "get_digest", "search_facts", "get_source_facts"})

        def call(name, arguments):
            return handle(self.service, session, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                  "params": {"name": name, "arguments": arguments}})["result"]

        self.assertTrue(call("get_raw_message", {"id": "m1"})["isError"])
        self.assertTrue(call("search_facts", {"query": "x", "path": "/etc/passwd"})["isError"])
        self.assertTrue(call("get_source_facts", {"ref": "m1"})["isError"])
        self.assertTrue(call("search_facts", {"query": "x" * 201})["isError"])
        self.approve_request()
        found = call("search_facts", {"query": "checklist"})["structuredContent"]
        expanded = call("get_source_facts", {"ref": found["facts"][0]["ref"]})["structuredContent"]
        self.assertEqual(expanded["facts"][0]["text"], found["facts"][0]["text"])
        status = call("get_status", {})["structuredContent"]
        self.assertNotIn("rick@example.test", json.dumps(status))


class HttpBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gateway = build(mailbox())
        cls.gateway.refresh()
        os.environ["EVERYTHING_PROXY_HOME"] = str(Path(cls.gateway.db.execute("PRAGMA database_list").fetchone()[2]).parent)
        build_dir = Path(__file__).resolve().parents[2] / "browser" / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        if not (build_dir / "index.html").exists():
            (build_dir / "index.html").write_text("<!doctype html><title>test</title>")
        cls.app = Companion(0, cls.gateway, "rick@example.test")
        cls.server = serve(cls.app)
        cls.app.port = cls.server.server_port
        cls.app.origin = f"http://127.0.0.1:{cls.app.port}"
        cls.app.host = f"127.0.0.1:{cls.app.port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.app.port)
        base = {"Host": self.app.host}
        base.update(headers or {})
        payload = json.dumps(body).encode() if body is not None else None
        if payload is not None:
            base.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=payload, headers=base)
        response = connection.getresponse()
        data = response.read()
        return response.status, dict(response.getheaders()), (json.loads(data) if data and response.getheader("Content-Type", "").startswith("application/json") else data)

    def pair(self):
        secret = self.app.new_pairing_secret()
        status, headers, body = self.request("POST", "/api/session", {}, {"Origin": self.app.origin, "Authorization": f"Bearer {secret}"})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";")[0]
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        return cookie, body["csrf"], secret

    def test_host_origin_and_fetch_metadata(self) -> None:
        self.assertEqual(self.request("GET", "/", headers={"Host": "evil.test:%d" % self.app.port})[0], 403)
        self.assertEqual(self.request("GET", "/", headers={"Host": "localhost:%d" % self.app.port})[0], 403)
        self.assertEqual(self.request("GET", "/", headers={"Origin": "http://127.0.0.1:1"})[0], 403)
        self.assertEqual(self.request("GET", "/", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_auth_pairing_and_csrf(self) -> None:
        self.assertEqual(self.request("GET", "/api/status")[0], 401)
        cookie, csrf, secret = self.pair()
        reused = self.request("POST", "/api/session", {}, {"Origin": self.app.origin, "Authorization": f"Bearer {secret}"})
        self.assertEqual(reused[0], 401, "pairing secret is single use")
        status, _, body = self.request("GET", "/api/status", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertGreater(body["views"]["all"], 0)
        fact = [row for row in facts(self.gateway) if "checklist" in row["template"]][0]
        path = f"/api/facts/{fact['id']}"
        self.assertEqual(self.request("POST", path, {"action": "approve"}, {"Cookie": cookie, "Origin": self.app.origin})[0], 403)
        self.assertEqual(self.request("POST", path, {"action": "approve"}, {"Cookie": cookie, "X-CSRF-Token": csrf})[0], 403)
        self.assertEqual(self.request("GET", path + "?action=approve", headers={"Cookie": cookie})[0], 404)
        form = self.request("POST", path, None, {"Cookie": cookie, "Origin": self.app.origin, "X-CSRF-Token": csrf,
                                                 "Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(form[0], 400)
        ok = self.request("POST", path, {"action": "approve"}, {"Cookie": cookie, "Origin": self.app.origin, "X-CSRF-Token": csrf})
        self.assertEqual(ok[0], 200)
        self.assertEqual(ok[2]["status"], "approved")

    def test_preview_equals_mcp_result(self) -> None:
        cookie, csrf, _ = self.pair()
        fact = [row for row in facts(self.gateway) if "checklist" in row["template"]][0]
        self.gateway.db.execute("UPDATE facts SET status = 'approved', reviewed_at = ? WHERE id = ?", (store.now(), fact["id"]))
        for tool, arguments in (("search_facts", {"query": "checklist"}), ("get_digest", {"since": "2000-01-01"})):
            status, _, preview = self.request("POST", "/api/preview", {"tool": tool, "arguments": arguments},
                                              {"Cookie": cookie, "Origin": self.app.origin, "X-CSRF-Token": csrf})
            self.assertEqual(status, 200)
            mcp = handle(ReleaseService(self.gateway.db, "mcp"), ReleaseSession(), {
                "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}})
            self.assertEqual(preview["result"], mcp["result"]["structuredContent"])
            self.assertTrue(preview["result"]["facts"])

    def test_alerted_fact_cannot_be_approved_until_edited(self) -> None:
        cookie, csrf, _ = self.pair()
        headers = {"Cookie": cookie, "Origin": self.app.origin, "X-CSRF-Token": csrf}
        alert = [row for row in facts(self.gateway) if "sign-in" in row["template"]][0]
        path = f"/api/facts/{alert['id']}"
        self.assertEqual(self.request("POST", path, {"action": "approve"}, headers)[0], 409)
        edited = self.request("POST", path, {"action": "edit", "text": "A sign-in attempt was blocked."}, headers)
        self.assertEqual(edited[2]["privacy_flags"], [])
        self.assertEqual(self.request("POST", path, {"action": "approve"}, headers)[0], 200)


SERVE_WITH_STUB_MODEL = """
import sys
from pathlib import Path
from companion import __main__ as cli, gmail, model, privacy
class Stub:
    def stop(self):
        Path(sys.argv[1]).write_text("stopped")
gmail.Grant.load = staticmethod(lambda: None)
model.runtime_available = lambda: None
model.BonsaiExtractor = Stub
privacy.detector = lambda: None
raise SystemExit(cli.main(["serve", "--port", "0"]))
"""


class ServeShutdownTest(unittest.TestCase):
    def test_sigterm_stops_the_local_model(self) -> None:
        root = Path(__file__).resolve().parents[2]
        (root / "browser" / "build").mkdir(parents=True, exist_ok=True)
        if not (root / "browser" / "build" / "index.html").exists():
            (root / "browser" / "build" / "index.html").write_text("<!doctype html><title>test</title>")
        for stdin in (subprocess.PIPE, subprocess.DEVNULL):
            with self.subTest(stdin="pipe" if stdin == subprocess.PIPE else "devnull"):
                marker = Path(tempfile.mkdtemp()) / "stopped"
                process = subprocess.Popen([sys.executable, "-c", SERVE_WITH_STUB_MODEL, str(marker)], cwd=root,
                                           stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in process.stdout:
                    if line.startswith("Press Enter"):
                        break
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=10), 0)
                process.stdout.close()
                if process.stdin:
                    process.stdin.close()
                self.assertTrue(marker.exists(), "serve stops the model server on SIGTERM")


class BodyTextTest(unittest.TestCase):
    @staticmethod
    def payload(*parts: tuple[str, str]) -> dict:
        encode = lambda text: base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
        return {"mimeType": "multipart/alternative",
                "parts": [{"mimeType": mime, "body": {"data": encode(text)}} for mime, text in parts]}

    def test_markup_in_plain_part_is_converted(self) -> None:
        template = ('<!--[if !mso]><!--><div>Your order shipped.</div><!--<![endif]-->\n'
                    '<!--[if false]><!--><v:textbox inset="0"><w:anchorlock/>Track it</v:textbox><!--<![endif]-->'
                    'Line one<br/>Line two')
        body, _ = text.body_text(self.payload(("text/plain", template)))
        self.assertNotIn("<", body)
        for words in ("Your order shipped.", "Track it", "Line one", "Line two"):
            self.assertIn(words, body)

    def test_markup_plain_part_defers_to_html_part(self) -> None:
        body, _ = text.body_text(self.payload(
            ("text/plain", "<!--[if !mso]><!-->Sale<!--<![endif]-->"), ("text/html", "<p>Sale ends Friday.</p>")))
        self.assertEqual(body, "Sale ends Friday.")

    def test_angle_brackets_in_real_plain_text_survive(self) -> None:
        plain = "Reply to <ops@example.test> or see <https://example.test/a>. 3 < 5 & 5 > 3."
        body, _ = text.body_text(self.payload(("text/plain", plain), ("text/html", "<p>other</p>")))
        self.assertEqual(body, "Reply to <ops@example.test> or see <[link removed] 3 < 5 & 5 > 3.")

    def test_one_line_outlook_quote_header_is_cut(self) -> None:
        plain = ("We hold no data about you.\n\nFrom: privacy@corp.test &lt;privacy@corp.test&gt; Sent: Monday, "
                 "26 October 2026 10:00 To: me@example.test Subject: Request\nYour original request.")
        self.assertEqual(text.body_text(self.payload(("text/plain", plain)))[0], "We hold no data about you.")

    def test_escaped_plain_part_is_decoded(self) -> None:
        body, _ = text.body_text(self.payload(("text/plain", "Write to &lt;privacy@corp.test&gt; &amp; wait.")))
        self.assertEqual(body, "Write to <privacy@corp.test> & wait.")


if __name__ == "__main__":
    unittest.main()
