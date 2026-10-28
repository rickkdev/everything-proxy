"""Read-only MCP over local stdio. The only reachable code is ReleaseService.

There is no tool for raw messages, approval, settings, OAuth, or identity lookup. Email text is
never parsed for instructions here; it is only ever data inside approved, checked facts.
"""

from __future__ import annotations

import json
import os
import sys

from . import db as store
from .release import CATEGORIES, MAX_RESULTS, ReleaseError, ReleaseService, ReleaseSession

PROTOCOL_VERSION = "2025-06-18"
DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
TOOLS = [
    {
        "name": "get_status",
        "description": "Sanitized sync health, import coverage, processing backlog, and privacy limits of the local Gmail gateway.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_digest",
        "description": "Locally approved email facts for an interval. Pass exactly one of: since (YYYY-MM-DD), "
                       "checkpoint (repeat an earlier digest), or after_checkpoint (facts approved since that digest). "
                       "People and organizations are aliased per session.",
        "inputSchema": {"type": "object", "properties": {
            "since": DATE, "checkpoint": {"type": "string"}, "after_checkpoint": {"type": "string"},
        }, "additionalProperties": False},
    },
    {
        "name": "search_facts",
        "description": "Search locally approved email facts relevant to a question. Returns bounded facts, never email text.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 200},
            "since": DATE, "until": DATE,
            "categories": {"type": "array", "items": {"type": "string", "enum": list(CATEGORIES)}},
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
        }, "required": ["query"], "additionalProperties": False},
    },
    {
        "name": "get_source_facts",
        "description": "Expand an opaque ref from this session into the other approved facts from the same conversation. Never returns original email.",
        "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"], "additionalProperties": False},
    },
]
_ALLOWED_ARGS = {tool["name"]: set(tool["inputSchema"]["properties"]) for tool in TOOLS}


def call_tool(service: ReleaseService, session: ReleaseSession, name: str, arguments: dict) -> dict:
    if name not in _ALLOWED_ARGS or not isinstance(arguments, dict) or set(arguments) - _ALLOWED_ARGS[name]:
        raise ReleaseError("unknown tool or argument")
    return getattr(service, name)(session, **arguments)


def handle(service: ReleaseService, session: ReleaseSession, request: dict) -> dict | None:
    method = request.get("method")
    request_id = request.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        result = {
            "protocolVersion": request.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "everything-proxy", "version": "0.1.0"},
            "instructions": "Read-only, locally approved facts from the user's Gmail. Aliases are not real names.",
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = request.get("params", {})
        try:
            payload = call_tool(service, session, params.get("name"), params.get("arguments") or {})
            result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                      "structuredContent": payload, "isError": False}
        except ReleaseError as error:
            result = {"content": [{"type": "text", "text": f"invalid_request: {error}"}], "isError": True}
        except Exception:  # never echo internals or private state in errors
            result = {"content": [{"type": "text", "text": "internal_error"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    # Protocol output goes only to the saved stdout; anything a library prints lands on stderr.
    protocol = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    from . import privacy

    privacy.detector()
    service = ReleaseService(store.connect(), channel="mcp")
    session = ReleaseSession()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            protocol.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
            continue
        response = handle(service, session, request) if isinstance(request, dict) else None
        if response is not None:
            protocol.write(json.dumps(response, ensure_ascii=False) + "\n")
    return 0
