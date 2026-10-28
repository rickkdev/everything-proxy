"""Read-only Gmail access: installed-app OAuth with PKCE and an allowlisted GET client."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import webbrowser

from . import credentials

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"
API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me/"
CREDENTIAL_NAME = "account"

# The only Gmail API paths this client can reach. Every call is an HTTP GET.
ALLOWED_PATHS = (
    re.compile(r"profile"),
    re.compile(r"messages"),
    re.compile(r"messages/[A-Za-z0-9]+"),
    re.compile(r"history"),
)


class AuthExpired(RuntimeError):
    """The stored grant no longer works; the user must reconnect locally."""


class HistoryExpired(RuntimeError):
    """Gmail rejected the history checkpoint; reconcile the configured window."""


class GmailUnavailable(RuntimeError):
    """Gmail could not be reached; the caller should report offline state."""


Transport = Callable[[Request], tuple[int, bytes]]


def _urlopen_transport(request: Request) -> tuple[int, bytes]:
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()
    except (URLError, TimeoutError, OSError) as error:
        raise GmailUnavailable(type(error).__name__) from error


@dataclass
class Grant:
    client_id: str
    client_secret: str
    refresh_token: str
    email: str

    @classmethod
    def load(cls) -> Grant | None:
        stored = credentials.load(CREDENTIAL_NAME)
        return cls(**stored) if stored else None

    def save(self) -> None:
        credentials.save(CREDENTIAL_NAME, self.__dict__)


class GmailClient:
    def __init__(self, grant: Grant, transport: Transport = _urlopen_transport) -> None:
        self.grant = grant
        self.transport = transport
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def _token(self) -> str:
        with self._lock:
            if self._access_token and time.time() < self._expires_at - 60:
                return self._access_token
            body = urlencode({
                "client_id": self.grant.client_id,
                "client_secret": self.grant.client_secret,
                "refresh_token": self.grant.refresh_token,
                "grant_type": "refresh_token",
            }).encode()
            status, raw = self.transport(Request(TOKEN_URI, data=body, method="POST"))
            payload = _json(raw)
            if status in (400, 401):
                raise AuthExpired("stored Gmail grant was rejected")
            if status != 200 or "access_token" not in payload:
                raise GmailUnavailable(f"token refresh returned {status}")
            granted = set(str(payload.get("scope", SCOPE)).split())
            if granted != {SCOPE}:
                raise AuthExpired("grant scope is not exactly gmail.readonly")
            self._access_token = payload["access_token"]
            self._expires_at = time.time() + int(payload.get("expires_in", 3600))
            return self._access_token

    def get(self, path: str, params: dict[str, object] | None = None) -> dict:
        if not any(pattern.fullmatch(path) for pattern in ALLOWED_PATHS):
            raise PermissionError(f"Gmail path is not allowlisted: {path}")
        query = urlencode(
            [(key, item) for key, value in (params or {}).items() if value is not None
             for item in (value if isinstance(value, (list, tuple)) else [value])]
        )
        url = API_BASE + path + (f"?{query}" if query else "")
        delay = 1.0
        for attempt in range(6):
            request = Request(url, headers={"Authorization": f"Bearer {self._token()}"}, method="GET")
            status, raw = self.transport(request)
            if status == 200:
                return _json(raw)
            payload = _json(raw)
            reasons = {item.get("reason") for item in payload.get("error", {}).get("errors", [])}
            if status == 401 and attempt == 0:
                self._access_token = None
                continue
            if status == 404 and path == "history":
                raise HistoryExpired("history checkpoint is no longer available")
            if status == 404:
                raise LookupError("message not found")
            if status == 429 or status >= 500 or (status == 403 and reasons & {"rateLimitExceeded", "userRateLimitExceeded"}):
                time.sleep(delay)
                delay = min(delay * 2, 32)
                continue
            if status in (401, 403):
                raise AuthExpired(f"Gmail rejected the request with {status}")
            raise GmailUnavailable(f"Gmail returned {status}")
        raise GmailUnavailable("Gmail rate limit or server errors persisted")

    def profile(self) -> dict:
        return self.get("profile")

    def list_messages(self, query: str, page_token: str | None, max_results: int) -> dict:
        return self.get("messages", {"q": query, "pageToken": page_token, "maxResults": max_results})

    def get_message(self, message_id: str, full: bool) -> dict:
        if full:
            return self.get(f"messages/{message_id}", {"format": "full"})
        return self.get(f"messages/{message_id}", {
            "format": "metadata",
            "metadataHeaders": ["From", "To", "Cc", "Subject", "Date", "List-Id", "List-Unsubscribe", "Content-Language"],
        })

    def list_history(self, start_history_id: str, page_token: str | None) -> dict:
        return self.get("history", {
            "startHistoryId": start_history_id,
            "pageToken": page_token,
            "historyTypes": ["messageAdded", "messageDeleted", "labelAdded", "labelRemoved"],
        })


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def connect(client_secrets_path: Path, open_browser: bool = True) -> Grant:
    """Run the local installed-app consent flow and store the grant in the OS keychain."""
    config = json.loads(client_secrets_path.expanduser().read_text(encoding="utf-8"))
    installed = config.get("installed")
    if not isinstance(installed, dict):
        raise ValueError("use an OAuth client of type 'Desktop app' (JSON with an 'installed' section)")
    client_id, client_secret = installed["client_id"], installed["client_secret"]

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    result: dict[str, str] = {}
    done = threading.Event()

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            params = {key: values[0] for key, values in parse_qs(urlparse(self.path).query).items()}
            if params.get("state") != state or "code" not in params:
                result["error"] = params.get("error", "invalid_callback")
            else:
                result["code"] = params["code"]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Everything Proxy received the Gmail consent result. You can close this tab.")
            done.set()

        def log_message(self, *_: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Callback)
    redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    url = AUTH_URI + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print("Open this URL to grant read-only Gmail access:\n" + url, flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        if not done.wait(timeout=300):
            raise TimeoutError("no consent response within five minutes")
    finally:
        server.shutdown()
    if "code" not in result:
        raise PermissionError(f"consent failed: {result.get('error')}")

    status, raw = _urlopen_transport(Request(TOKEN_URI, method="POST", data=urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": result["code"],
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()))
    token = _json(raw)
    if status != 200 or "refresh_token" not in token:
        raise PermissionError(f"token exchange failed with {status}")
    if set(str(token.get("scope", "")).split()) != {SCOPE}:
        _revoke(token["refresh_token"])
        raise PermissionError("Google granted a scope other than gmail.readonly; the grant was revoked")
    grant = Grant(client_id, client_secret, token["refresh_token"], "")
    grant.email = GmailClient(grant).profile()["emailAddress"]
    grant.save()
    return grant


def _revoke(token: str) -> None:
    try:
        _urlopen_transport(Request(REVOKE_URI, method="POST", data=urlencode({"token": token}).encode()))
    except GmailUnavailable:
        pass


def disconnect() -> bool:
    grant = Grant.load()
    if grant is None:
        return False
    _revoke(grant.refresh_token)
    credentials.delete(CREDENTIAL_NAME)
    return True
