"""OS credential store access. Secrets never touch the database, logs, or argv."""

from __future__ import annotations

import json

import keyring
from keyring.errors import PasswordDeleteError

SERVICE = "everything-proxy.gmail"


def save(name: str, value: dict[str, str]) -> None:
    keyring.set_password(SERVICE, name, json.dumps(value))


def load(name: str) -> dict[str, str] | None:
    raw = keyring.get_password(SERVICE, name)
    return json.loads(raw) if raw else None


def delete(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except PasswordDeleteError:
        pass
