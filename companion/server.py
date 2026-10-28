"""Loopback HTTP companion: serves the browser UI and its private local API.

Implements .audit/loopback-http-boundary.md: exact Host and Origin checks, terminal pairing,
HttpOnly SameSite=Strict session cookie, CSRF header on mutations, strict CSP, no CORS.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import mimetypes
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlparse

from . import ROOT
from . import db as store
from . import privacy
from .release import ReleaseError, ReleaseService, ReleaseSession
from .mcp_server import call_tool
from .model import runtime_available
from .sync import Gateway

STATIC_DIR = ROOT / "browser" / "build"
MAX_BODY = 16 * 1024
IDLE_SECONDS = 30 * 60
ABSOLUTE_SECONDS = 8 * 60 * 60
PAIRING_SECONDS = 5 * 60
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
       "font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'")
VIEWS = {
    "all": "1",
    "included": "state = 'processed' AND model_relevance = 'include'",
    "review": "id IN (SELECT message_id FROM facts WHERE status = 'proposed')",
    "deprioritized": "(relevance = 'deprioritize' AND state = 'filtered') OR model_relevance = 'deprioritize'",
    "skipped": "(relevance = 'skip' AND state = 'filtered') OR model_relevance = 'skip'",
    "withheld": "state = 'withheld' OR model_relevance = 'inspect'",
    "pending": "state IN ('pending_body', 'pending_model', 'failed')",
}


class Companion:
    def __init__(self, port: int, gateway, account_email: str | None) -> None:
        self.port = port
        self.origin = f"http://127.0.0.1:{port}"
        self.host = f"127.0.0.1:{port}"
        self.gateway = gateway
        self.account_email = account_email
        self.pairing_secret: str | None = secrets.token_urlsafe(32)
        self.pairing_expires = time.monotonic() + PAIRING_SECONDS
        self.pairing_attempts = 0
        self.sessions: dict[str, dict] = {}
        self.lock = threading.Lock()

    def new_pairing_secret(self) -> str:
        with self.lock:
            self.pairing_secret = secrets.token_urlsafe(32)
            self.pairing_expires = time.monotonic() + PAIRING_SECONDS
            self.pairing_attempts = 0
            return self.pairing_secret

    def pair(self, presented: str) -> tuple[str, str] | None:
        with self.lock:
            self.pairing_attempts += 1
            secret = self.pairing_secret
            if (secret is None or time.monotonic() > self.pairing_expires or self.pairing_attempts > 10
                    or not hmac.compare_digest(presented.encode(), secret.encode())):
                return None
            self.pairing_secret = None
            session_id, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            now = time.monotonic()
            self.sessions[session_id] = {"csrf": csrf, "created": now, "seen": now}
            return session_id, csrf

    def session(self, session_id: str | None) -> dict | None:
        with self.lock:
            record = self.sessions.get(session_id or "")
            now = time.monotonic()
            if record is None:
                return None
            if now - record["seen"] > IDLE_SECONDS or now - record["created"] > ABSOLUTE_SECONDS:
                self.sessions.pop(session_id, None)
                return None
            record["seen"] = now
            return record


def _fact_view(db, row, include_preview: bool = True) -> dict:
    service = ReleaseService(db, channel="local-review")
    session = ReleaseSession()
    reason, aliased = service.check_fact(row, session)
    flags = json.loads(row["privacy_flags"])
    if row["status"] != "approved" and not flags:
        # Show whether the text would pass if approved.
        final = privacy.final_check(aliased, session.aliases)
        reason = "final_privacy_check" if final else None
        flags = final
    return {
        "id": row["id"], "status": row["status"], "category": row["category"],
        "local_text": privacy.render_local(db, row["template"]),
        "outgoing_text": aliased if include_preview else None,
        "evidence": json.loads(row["evidence"]), "privacy_flags": flags,
        "release_blocked": reason, "edited": bool(row["edited"]),
        "model": row["model"], "prompt_version": row["prompt_version"], "created_at": row["created_at"],
    }


def _message_summary(row) -> dict:
    return {
        "id": row["id"], "received_at": row["received_at"], "sender": row["sender"],
        "sender_address": row["sender_address"], "subject": row["subject"],
        "relevance": row["relevance"], "reason": row["reason"], "privacy_hold": row["privacy_hold"],
        "model_relevance": row["model_relevance"], "state": row["state"], "error": row["error"],
        "language": row["language"], "labels": json.loads(row["labels"]),
    }


def make_handler(app: Companion):
    class Handler(BaseHTTPRequestHandler):
        server_version = "everything-proxy"
        sys_version = ""

        # ----- plumbing --------------------------------------------------------------------

        def log_message(self, *_: object) -> None:
            return None  # URLs can carry private search text; keep no access log

        def _headers(self, status: int, content_type: str, length: int, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cache-Control", "no-store")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()

        def _json(self, status: int, payload: object, extra: dict | None = None) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self._headers(status, "application/json; charset=utf-8", len(body), extra)
            self.wfile.write(body)

        def _deny(self, status: int = 403) -> None:
            self._json(status, {"error": {401: "unauthenticated", 403: "forbidden", 404: "not_found"}.get(status, "bad_request")})

        def _boundary_ok(self) -> bool:
            hosts = self.headers.get_all("Host") or []
            if len(hosts) != 1 or hosts[0] != app.host:
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin != app.origin:
                return False
            fetch_site = self.headers.get("Sec-Fetch-Site")
            if fetch_site is not None and fetch_site not in ("same-origin", "none"):
                return False
            if fetch_site == "none" and self.path.startswith("/api/"):
                return False
            return True

        def _session_id(self) -> str | None:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return cookie["ep_session"].value if "ep_session" in cookie else None

        def _body(self) -> dict | None:
            if not (self.headers.get("Content-Type", "").split(";")[0].strip() == "application/json"):
                return None
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > MAX_BODY:
                return None
            try:
                value = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None

        # ----- dispatch --------------------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802
            if not self._boundary_ok():
                return self._deny()
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                return self._static(path)
            record = app.session(self._session_id())
            if record is None:
                return self._deny(401)
            query = {key: values[0] for key, values in parse_qs(urlparse(self.path).query).items()}
            self._get_api(path, query, record)

        def do_POST(self) -> None:  # noqa: N802
            if not self._boundary_ok() or self.headers.get("Origin") != app.origin:
                return self._deny()
            path = urlparse(self.path).path
            body = self._body()
            if body is None:
                return self._deny(400)
            if path == "/api/session":
                auth = self.headers.get("Authorization", "")
                paired = app.pair(auth.removeprefix("Bearer ").strip()) if auth.startswith("Bearer ") else None
                if paired is None:
                    return self._deny(401)
                session_id, csrf = paired
                cookie = f"ep_session={session_id}; HttpOnly; SameSite=Strict; Path=/; Max-Age={ABSOLUTE_SECONDS}"
                return self._json(200, {"csrf": csrf}, {"Set-Cookie": cookie})
            record = app.session(self._session_id())
            if record is None:
                return self._deny(401)
            if not hmac.compare_digest(self.headers.get("X-CSRF-Token", "").encode(), record["csrf"].encode()):
                return self._deny()
            self._post_api(path, body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._deny()

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS

        # ----- static ----------------------------------------------------------------------

        def _static(self, path: str) -> None:
            relative = "index.html" if path in ("/", "") else path.lstrip("/")
            if not re.fullmatch(r"[A-Za-z0-9._/-]+", relative) or ".." in relative:
                return self._deny(404)
            target = (STATIC_DIR / relative).resolve()
            if not target.is_file() or STATIC_DIR.resolve() not in target.parents:
                return self._deny(404)
            data = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._headers(200, content_type, len(data))
            self.wfile.write(data)

        # ----- API -------------------------------------------------------------------------

        def _get_api(self, path: str, query: dict, record: dict) -> None:
            db = store.connect()
            try:
                if path == "/api/session":
                    return self._json(200, {"csrf": record["csrf"]})
                if path == "/api/status":
                    return self._json(200, self._status(db))
                if path == "/api/messages":
                    return self._json(200, self._messages(db, query))
                match = re.fullmatch(r"/api/messages/([0-9a-f]{32})", path)
                if match:
                    return self._message(db, match.group(1))
                if path == "/api/facts":
                    status = query.get("status", "proposed")
                    if status not in ("proposed", "approved", "dismissed", "superseded"):
                        return self._deny(400)
                    rows = db.execute(
                        "SELECT facts.* FROM facts JOIN messages ON messages.id = facts.message_id"
                        " WHERE facts.status = ? ORDER BY messages.received_at DESC LIMIT 200", (status,),
                    ).fetchall()
                    facts = []
                    for row in rows:
                        view = _fact_view(db, row)
                        message = db.execute("SELECT * FROM messages WHERE id = ?", (row["message_id"],)).fetchone()
                        view["message"] = _message_summary(message)
                        facts.append(view)
                    return self._json(200, {"facts": facts})
                self._deny(404)
            finally:
                db.close()

        def _post_api(self, path: str, body: dict) -> None:
            db = store.connect()
            try:
                if path == "/api/logout":
                    with app.lock:
                        app.sessions.pop(self._session_id() or "", None)
                    return self._json(200, {"ok": True}, {"Set-Cookie": "ep_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
                if path == "/api/refresh":
                    if app.gateway is None:
                        return self._json(409, {"error": "not_connected"})
                    threading.Thread(target=app.gateway.refresh, daemon=True).start()
                    return self._json(202, {"started": True})
                if path == "/api/retry-failed":
                    if app.gateway is None:
                        return self._json(409, {"error": "not_connected"})
                    count = Gateway(db, None, None).retry_failed()
                    threading.Thread(target=app.gateway.refresh, daemon=True).start()
                    return self._json(202, {"retried": count})
                if path == "/api/senders":
                    address, action = body.get("address"), body.get("action")
                    if set(body) - {"address", "action"} or not isinstance(address, str) or "@" not in address \
                            or len(address) > 320 or action not in ("include", "exclude", None) or app.gateway is None:
                        return self._deny(400)
                    Gateway(db, None, None).set_sender_override(address, action)
                    threading.Thread(target=app.gateway.refresh, daemon=True).start()
                    return self._json(200, {"ok": True})
                match = re.fullmatch(r"/api/facts/([0-9a-f]{32})", path)
                if match:
                    return self._fact_action(db, match.group(1), body)
                if path == "/api/preview":
                    tool, arguments = body.get("tool"), body.get("arguments", {})
                    if set(body) - {"tool", "arguments"}:
                        return self._deny(400)
                    service = ReleaseService(db, channel="preview")
                    try:
                        return self._json(200, {"result": call_tool(service, ReleaseSession(), tool, arguments)})
                    except ReleaseError as error:
                        return self._json(400, {"error": str(error)})
                self._deny(404)
            finally:
                db.close()

        def _status(self, db) -> dict:
            counts = {row["state"]: row["n"] for row in db.execute("SELECT state, COUNT(*) AS n FROM messages GROUP BY state")}
            facts = {row["status"]: row["n"] for row in db.execute("SELECT status, COUNT(*) AS n FROM facts GROUP BY status")}
            views = {name: db.execute(f"SELECT COUNT(*) FROM messages WHERE {where}").fetchone()[0] for name, where in VIEWS.items()}
            return {
                "account": app.account_email,
                "connected": app.gateway is not None and app.gateway.client is not None,
                "progress": app.gateway.progress if app.gateway else {"phase": "idle", "detail": ""},
                "last_sync_at": store.get_meta(db, "last_sync_at"),
                "sync_error": store.get_meta(db, "sync_error", "") or None,
                "coverage": json.loads(store.get_meta(db, "coverage", "{}") or "{}"),
                "message_states": counts, "fact_states": facts, "views": views,
                "model_unavailable": runtime_available(),
                "policy_version": privacy.POLICY_VERSION,
            }

        def _messages(self, db, query: dict) -> dict:
            view = query.get("view", "all")
            if view not in VIEWS:
                return {"messages": []}
            sql = f"SELECT * FROM messages WHERE ({VIEWS[view]})"
            params: list[object] = []
            text = query.get("q", "")[:200]
            if text:
                sql += " AND (subject LIKE ? OR sender LIKE ? OR id IN (SELECT message_id FROM facts WHERE search_text LIKE ?))"
                params += [f"%{text}%"] * 3
            if query.get("from"):
                sql += " AND received_at >= ?"
                params.append(query["from"][:10])
            if query.get("to"):
                sql += " AND substr(received_at, 1, 10) <= ?"
                params.append(query["to"][:10])
            rows = db.execute(sql + " ORDER BY received_at DESC LIMIT 500", params).fetchall()
            result = []
            for row in rows:
                summary = _message_summary(row)
                summary["fact_counts"] = {
                    item["status"]: item["n"] for item in db.execute(
                        "SELECT status, COUNT(*) AS n FROM facts WHERE message_id = ? GROUP BY status", (row["id"],))
                }
                result.append(summary)
            return {"messages": result}

        def _message(self, db, message_id: str) -> None:
            row = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
            if row is None:
                return self._deny(404)
            detail = _message_summary(row)
            detail["body"] = row["body"]
            detail["coverage"] = json.loads(row["coverage"])
            facts = db.execute(
                "SELECT * FROM facts WHERE gmail_thread_id = ? ORDER BY created_at DESC", (row["gmail_thread_id"],)
            ).fetchall()
            detail["facts"] = [_fact_view(db, fact) for fact in facts]
            thread = db.execute(
                "SELECT id, received_at, sender, subject, state FROM messages WHERE gmail_thread_id = ? ORDER BY received_at",
                (row["gmail_thread_id"],),
            ).fetchall()
            detail["thread"] = [dict(item) for item in thread]
            detail["gmail_url"] = f"https://mail.google.com/mail/u/0/#all/{row['gmail_id']}"
            override = db.execute("SELECT action FROM sender_overrides WHERE address = ?", (row["sender_address"],)).fetchone()
            detail["sender_override"] = override["action"] if override else None
            self._json(200, detail)

        def _fact_action(self, db, fact_id: str, body: dict) -> None:
            action = body.get("action")
            if set(body) - {"action", "text"} or action not in ("approve", "dismiss", "edit", "reopen"):
                return self._deny(400)
            row = db.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
            if row is None or row["status"] == "superseded":
                return self._deny(404)
            if action == "edit":
                new_text = body.get("text")
                if not isinstance(new_text, str) or not new_text.strip() or len(new_text) > 300:
                    return self._deny(400)
                message = db.execute("SELECT participants FROM messages WHERE id = ?", (row["message_id"],)).fetchone()
                participants = [tuple(item) for item in json.loads(message["participants"])]
                with store.transaction(db):
                    template, flags = privacy.tokenize(db, " ".join(new_text.split()), participants)
                    db.execute(
                        "UPDATE facts SET template = ?, search_text = ?, privacy_flags = ?, edited = 1, status = 'proposed',"
                        " policy_version = ?, reviewed_at = ? WHERE id = ?",
                        (template, privacy.search_text(template), json.dumps(flags), privacy.POLICY_VERSION, store.now(), fact_id),
                    )
            elif action == "approve":
                view = _fact_view(db, row)
                if view["privacy_flags"]:
                    return self._json(409, {"error": "privacy_check_failed", "flags": view["privacy_flags"]})
                with store.transaction(db):
                    db.execute("UPDATE facts SET status = 'approved', policy_version = ?, reviewed_at = ? WHERE id = ?",
                               (privacy.POLICY_VERSION, store.now(), fact_id))
            else:
                status = "dismissed" if action == "dismiss" else "proposed"
                with store.transaction(db):
                    db.execute("UPDATE facts SET status = ?, reviewed_at = ? WHERE id = ?", (status, store.now(), fact_id))
            updated = db.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
            self._json(200, _fact_view(db, updated))

    return Handler


def serve(app: Companion) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", app.port), make_handler(app))
    server.daemon_threads = True
    return server
