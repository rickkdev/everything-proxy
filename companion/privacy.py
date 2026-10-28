"""Identifier detection, local entity tokens, and the final outgoing privacy check.

Detection is a candidate signal, not a guarantee. Anything the detectors flag that is not a
person/organization (aliased) or an ordinary date blocks release until the user edits it.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid

from . import ROOT
from .paths import MODEL_DIR

ALIAS_LABELS = {
    "name": "person", "first_name": "person", "last_name": "person", "email": "person",
    "company_name": "organization",
}
ALLOWED_LABELS = {"date", "date_time"}
TOKEN = re.compile(r"⟦([po]):([0-9a-f]{12})⟧")
_TOKEN_SPLIT = re.compile(r"(⟦[po]:[0-9a-f]{12}⟧)")
POLICY = {
    "detector": "rules+gliner",
    "alias_labels": sorted(ALIAS_LABELS),
    "allowed_labels": sorted(ALLOWED_LABELS),
    "release_requires": ["approved", "source_in_scope", "current_policy", "final_check"],
}
POLICY_VERSION = hashlib.sha256(json.dumps(POLICY, sort_keys=True).encode()).hexdigest()[:12]
_FREE_MAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "icloud.com", "yahoo.com", "gmx.de", "web.de"}

_detector = None
_detector_lock = threading.Lock()


class _Serialized:
    """GLiNER is not thread-safe; HTTP handlers and the sync worker share one instance."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.lock = threading.Lock()

    def detect(self, text: str):
        with self.lock:
            return self.inner.detect(text)


def detector():
    global _detector
    with _detector_lock:
        if _detector is None:
            from evaluate import make_detector

            lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8"))
            _detector = _Serialized(make_detector("rules+gliner", MODEL_DIR, lock))
        return _detector


def set_detector(value) -> None:
    """Tests inject a deterministic detector."""
    global _detector
    _detector = _Serialized(value)


def _entity(db: sqlite3.Connection, kind: str, value: str) -> str:
    normalized = " ".join(value.split()).casefold()
    row = db.execute("SELECT id FROM entities WHERE kind = ? AND value = ?", (kind, normalized)).fetchone()
    if row:
        return row["id"]
    entity_id = uuid.uuid4().hex[:12]
    db.execute("INSERT INTO entities VALUES (?, ?, ?)", (entity_id, kind, normalized))
    return entity_id


def _token(kind: str, entity_id: str) -> str:
    return f"⟦{kind[0]}:{entity_id}⟧"


def _participant_patterns(participants: list[tuple[str, str]]) -> list[tuple[re.Pattern[str], str, str]]:
    patterns: list[tuple[re.Pattern[str], str, str]] = []
    for name, address in participants:
        patterns.append((re.compile(re.escape(address), re.IGNORECASE), "person", address))
        domain = address.rpartition("@")[2]
        if domain and domain not in _FREE_MAIL:
            patterns.append((re.compile(rf"\b{re.escape(domain)}\b", re.IGNORECASE), "organization", domain))
            stem = domain.split(".")[0]
            if len(stem) >= 4:
                patterns.append((re.compile(rf"\b{re.escape(stem)}\b", re.IGNORECASE), "organization", domain))
        clean = re.sub(r"[\"'()]", "", name).strip()
        if "@" in clean or not clean:
            continue
        patterns.append((re.compile(rf"\b{re.escape(clean)}\b"), "person", address))
        for part in clean.replace(",", " ").split():
            if len(part) >= 3 and part[0].isupper():
                patterns.append((re.compile(rf"\b{re.escape(part)}\b"), "person", address))
    patterns.sort(key=lambda item: -len(item[0].pattern))
    return patterns


def _blank_tokens(template: str) -> str:
    """Same length as the template so detector offsets line up; tokens become neutral filler."""
    return TOKEN.sub(lambda match: "x" * len(match.group(0)), template)


def tokenize(db: sqlite3.Connection, text: str, participants: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """Replace identities with local entity tokens; return the template and blocking labels."""
    template = text
    for pattern, kind, value in _participant_patterns(participants):
        pieces = _TOKEN_SPLIT.split(template)
        template = "".join(
            piece if index % 2 else
            pattern.sub(lambda _: _token(kind, _entity(db, kind, value)), piece)
            for index, piece in enumerate(pieces)
        )
    spans = detector().detect(_blank_tokens(template))
    flags: list[str] = []
    for span in sorted(spans, key=lambda item: -item.start):
        fragment = template[span.start:span.end]
        if TOKEN.search(fragment) or not fragment.strip():
            continue
        kind = ALIAS_LABELS.get(span.label)
        if kind:
            template = template[:span.start] + _token(kind, _entity(db, kind, fragment)) + template[span.end:]
        elif span.label not in ALLOWED_LABELS:
            flags.append(span.label)
    return template, sorted(set(flags))


def search_text(template: str) -> str:
    """Neutral text for search, so a query cannot probe a real identity."""
    return " ".join(TOKEN.sub(" ", template).split())


def render_local(db: sqlite3.Connection, template: str) -> str:
    def replace(match: re.Match[str]) -> str:
        row = db.execute("SELECT value FROM entities WHERE id = ?", (match.group(2),)).fetchone()
        return row["value"].title() if row else "[unknown]"

    return TOKEN.sub(replace, template)


class AliasSession:
    """Request-scoped aliases. A new session never reuses another session's mapping."""

    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}
        self.counts = {"p": 0, "o": 0}

    def alias(self, kind: str, entity_id: str) -> str:
        if entity_id not in self.aliases:
            index = self.counts[kind]
            self.counts[kind] += 1
            letters = ""
            while True:
                letters = chr(65 + index % 26) + letters
                index = index // 26 - 1
                if index < 0:
                    break
            self.aliases[entity_id] = ("Person " if kind == "p" else "Organization ") + letters
        return self.aliases[entity_id]

    def render(self, template: str) -> str:
        return TOKEN.sub(lambda match: self.alias(match.group(1), match.group(2)), template)


def final_check(text: str, session: AliasSession) -> list[str]:
    """Run the detectors on the exact outgoing string. Alias names and dates are allowed."""
    allowed = [match.span() for alias in set(session.aliases.values())
               for match in re.finditer(re.escape(alias), text)]
    flags = []
    for span in detector().detect(text):
        if span.label in ALLOWED_LABELS:
            continue
        if any(start <= span.start and span.end <= end for start, end in allowed):
            continue
        flags.append(span.label)
    if TOKEN.search(text) or "@" in text:
        flags.append("identity_marker")
    return sorted(set(flags))
