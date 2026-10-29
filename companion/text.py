"""Turn Gmail payloads into bounded plain text. Email is untrusted data, never markup."""

from __future__ import annotations

import base64
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser
import re

MAX_BODY_CHARS = 6000

_QUOTE_HEADERS = re.compile(
    r"^(?:On .{0,200}wrote:|Am .{0,200}schrieb .{0,200}:|-{2,}\s*Original Message\s*-{2,}|"
    r"-{2,}\s*Ursprüngliche Nachricht\s*-{2,}|From: .+\nSent: .+)",
    re.MULTILINE | re.IGNORECASE,
)
_SIGNATURE = re.compile(r"^-- ?$", re.MULTILINE)
_TRACKING_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_MARKUP = re.compile(r"<(?:!--|!\[|/?[a-z][a-z0-9]*(?::[a-z0-9]+)?(?:\s[^<>]*)?/?>)", re.IGNORECASE)

_ENGLISH = frozenset(
    "the and to of a in is you that for it on with as this be are your have will please "
    "we at by from or can not if our an was would could about".split()
)
_GERMAN = frozenset(
    "der die das und ist nicht ich sie es zu den mit sich des auf für von dem ein eine "
    "wir ihr bitte haben wird werden auch noch bei aus oder kann".split()
)


class _TextExtractor(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "head", "title"}:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "head", "title"} and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts)


def _decode(data: str) -> str:
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return raw.decode("utf-8", errors="replace")


def _walk(part: dict, plain: list[str], html: list[str]) -> bool:
    """Collect inline text parts. Returns True if an attachment was skipped."""
    skipped = False
    if part.get("filename"):
        return True
    mime = part.get("mimeType", "")
    data = part.get("body", {}).get("data")
    if data and mime == "text/plain":
        plain.append(_decode(data))
    elif data and mime == "text/html":
        html.append(_decode(data))
    for child in part.get("parts", []) or []:
        skipped |= _walk(child, plain, html)
    return skipped


def strip_quoted(text: str) -> str:
    text = text.replace("\r\n", "\n")
    match = _QUOTE_HEADERS.search(text)
    if match:
        text = text[: match.start()]
    signature = _SIGNATURE.search(text)
    if signature:
        text = text[: signature.start()]
    lines = [line for line in text.split("\n") if not line.lstrip().startswith(">")]
    text = "\n".join(lines)
    text = _TRACKING_URL.sub("[link removed]", text)
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def body_text(payload: dict) -> tuple[str, dict[str, bool]]:
    """Return sanitized body text and coverage flags for one Gmail message payload."""
    plain: list[str] = []
    html: list[str] = []
    attachments = _walk(payload, plain, html)
    # Template mailers often put their HTML into the text/plain part too.
    markup = [part for part in plain if _MARKUP.search(part)]
    plain = [part for part in plain if not _MARKUP.search(part)]
    html = html or markup
    source = "\n".join(plain) if plain else html_to_text("\n".join(html))
    text = strip_quoted(source)
    truncated = len(text) > MAX_BODY_CHARS
    return text[:MAX_BODY_CHARS], {
        "attachments_skipped": attachments,
        "html_only": not plain and bool(html),
        "truncated": truncated,
    }


def headers(payload: dict) -> dict[str, str]:
    return {item["name"].lower(): item["value"] for item in payload.get("headers", []) if "name" in item}


def sender_address(value: str) -> str:
    return parseaddr(value)[1].casefold()


def participants(header_values: dict[str, str]) -> list[tuple[str, str]]:
    """Display names and addresses from routing headers, used for local alias detection."""
    fields = [header_values.get(key, "") for key in ("from", "to", "cc")]
    return [(name.strip(), address.casefold()) for name, address in getaddresses(fields) if address]


def detect_language(text: str, declared: str | None = None) -> str | None:
    if declared:
        return declared.split(",")[0].strip().split("-")[0].lower() or None
    words = re.findall(r"[a-zäöüß]+", text.casefold())
    if len(words) < 3:
        return "en" if words else None
    english = sum(word in _ENGLISH for word in words)
    german = sum(word in _GERMAN for word in words)
    if german == 0 and english >= 1 and len(words) < 15:
        return "en"
    if english >= max(2, german * 1.5):
        return "en"
    if german >= max(2, english * 1.5):
        return "de"
    return None
