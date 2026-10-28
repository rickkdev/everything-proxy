"""Synthetic Gmail API and extractor for companion tests. No network, no real mailbox."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

from evaluate import DetectedSpan, RulesDetector

from companion.gmail import SCOPE, Grant, GmailClient
from companion.model import Extraction, validate


def b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def gmail_message(gmail_id: str, thread_id: str, sender: str, subject: str, body: str,
                  labels: list[str] | None = None, days_ago: float = 1, html: bool = False,
                  to: str = "Rick Example <rick@example.test>") -> dict:
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    part = {"mimeType": "text/html" if html else "text/plain", "body": {"data": b64(body)}}
    return {
        "id": gmail_id, "threadId": thread_id, "labelIds": labels or ["INBOX"],
        "internalDate": str(int(when.timestamp() * 1000)),
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [{"name": "From", "value": sender}, {"name": "To", "value": to},
                        {"name": "Subject", "value": subject}],
            "parts": [part, {"mimeType": "application/pdf", "filename": "x.pdf", "body": {"attachmentId": "a"}}],
        },
    }


class FakeGmail:
    """Implements the GET endpoints the client may call and records every request."""

    def __init__(self) -> None:
        self.messages: dict[str, dict] = {}
        self.history: list[dict] = []
        self.history_id = 100
        self.expired_before: int | None = None
        self.requests: list[tuple[str, str]] = []
        self.rate_limit_once = False
        self.offline = False

    def add(self, message: dict, record: bool = True) -> None:
        self.messages[message["id"]] = message
        if record:
            self.history_id += 1
            self.history.append({"id": str(self.history_id), "messagesAdded": [{"message": {"id": message["id"]}}]})

    def delete(self, gmail_id: str) -> None:
        self.messages.pop(gmail_id, None)
        self.history_id += 1
        self.history.append({"id": str(self.history_id), "messagesDeleted": [{"message": {"id": gmail_id}}]})

    def relabel(self, gmail_id: str, labels: list[str]) -> None:
        self.messages[gmail_id]["labelIds"] = labels
        self.history_id += 1
        self.history.append({"id": str(self.history_id), "labelsAdded": [{"message": {"id": gmail_id}}]})

    def __call__(self, request: Request) -> tuple[int, bytes]:
        from companion.gmail import GmailUnavailable

        if self.offline:
            raise GmailUnavailable("URLError")
        url = urlparse(request.full_url)
        self.requests.append((request.get_method(), url.path))
        if url.netloc == "oauth2.googleapis.com":
            return 200, json.dumps({"access_token": "t", "expires_in": 3600, "scope": SCOPE}).encode()
        if self.rate_limit_once:
            self.rate_limit_once = False
            return 429, b"{}"
        query = {key: values for key, values in parse_qs(url.query).items()}
        path = url.path.removeprefix("/gmail/v1/users/me/")
        if path == "profile":
            return 200, json.dumps({"emailAddress": "rick@example.test", "historyId": str(self.history_id)}).encode()
        if path == "messages":
            ids = sorted(self.messages, key=lambda key: -int(self.messages[key]["internalDate"]))
            start = int(query.get("pageToken", ["0"])[0])
            size = int(query["maxResults"][0])
            page = {"messages": [{"id": key} for key in ids[start:start + size]]}
            if start + size < len(ids):
                page["nextPageToken"] = str(start + size)
            return 200, json.dumps(page).encode()
        match = re.fullmatch(r"messages/(\w+)", path)
        if match:
            message = self.messages.get(match.group(1))
            if message is None:
                return 404, b"{}"
            if query["format"][0] == "metadata":
                trimmed = dict(message, payload={"headers": message["payload"]["headers"]})
                return 200, json.dumps(trimmed).encode()
            return 200, json.dumps(message).encode()
        if path == "history":
            start = int(query["startHistoryId"][0])
            if self.expired_before is not None and start < self.expired_before:
                return 404, b"{}"
            records = [item for item in self.history if int(item["id"]) > start]
            return 200, json.dumps({"history": records, "historyId": str(self.history_id)}).encode()
        return 400, b"{}"


def fake_client(api: FakeGmail) -> GmailClient:
    return GmailClient(Grant("id", "secret", "refresh", "rick@example.test"), transport=api)


class ScriptedExtractor:
    """Returns canned model JSON keyed by a marker in the newest message body; validated like real output."""

    name = "scripted-test-extractor"

    def __init__(self, outputs: dict[str, str]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def extract(self, messages: list[dict]) -> Extraction:
        self.calls.append([message["id"] for message in messages])
        newest = messages[-1]["body"]
        for marker, content in self.outputs.items():
            if marker in newest:
                return validate(content, messages, "test")
        return validate('{"relevance": "inspect", "facts": []}', messages, "test")


class TestDetector(RulesDetector):
    """Rules plus a deterministic stand-in for GLiNER names and PIN over-detection."""

    names = ("Morgan Lee", "Avery Stone", "Northwind Labs")

    def detect(self, text: str):
        spans = list(super().detect(text))
        for name in self.names:
            for match in re.finditer(re.escape(name), text):
                spans.append(DetectedSpan(match.start(), match.end(), "company_name" if "Labs" in name else "name"))
        for match in re.finditer(r"\b\d{6}\b", text):
            spans.append(DetectedSpan(match.start(), match.end(), "pin"))
        return tuple(spans)
