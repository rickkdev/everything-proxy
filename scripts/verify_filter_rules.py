#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from filter_rules import (
    MessageMetadata,
    RuleSet,
    evaluate_message,
    evaluate_metadata,
)


ROOT = Path(__file__).resolve().parents[1]
RULE_FIELDS = {
    "excluded_senders",
    "excluded_lists",
    "included_senders",
    "included_lists",
    "selected_senders",
    "newsletter_lists",
    "routine_receipt_senders",
    "routine_shipment_senders",
    "supported_languages",
}


def _record(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _strings(value: Any, label: str) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return frozenset(value)


def _load_case(case: dict[str, Any]) -> tuple[MessageMetadata, str, RuleSet]:
    metadata_raw = _record(case.get("metadata"), "metadata")
    text_fields = ("sender", "list_id", "subject", "language")
    if any(
        key in metadata_raw and not isinstance(metadata_raw[key], str)
        for key in text_fields
    ):
        raise ValueError("metadata text fields must be strings")
    labels = _strings(metadata_raw.get("labels", []), "metadata.labels")
    tracked = metadata_raw.get("tracked_thread", False)
    if not isinstance(tracked, bool):
        raise ValueError("metadata.tracked_thread must be a boolean")
    metadata = MessageMetadata(
        sender=metadata_raw.get("sender"),
        list_id=metadata_raw.get("list_id"),
        subject=metadata_raw.get("subject"),
        labels=labels,
        tracked_thread=tracked,
        language=metadata_raw.get("language"),
    )

    rules_raw = _record(case.get("rules", {}), "rules")
    if set(rules_raw) - RULE_FIELDS:
        raise ValueError("rules contains an unknown field")
    rules = RuleSet(
        **{name: _strings(rules_raw.get(name, list(getattr(RuleSet(), name))), f"rules.{name}")
           for name in RULE_FIELDS}
    )
    body = case.get("body", "")
    if not isinstance(body, str):
        raise ValueError("body must be a string")
    return metadata, body, rules


def verify() -> int:
    payload = json.loads((ROOT / "fixtures/filter-rule-cases.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("fixture file must use schema_version 1")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("fixture file must contain cases")

    seen: set[str] = set()
    failures: list[str] = []
    for raw_case in cases:
        case = _record(raw_case, "case")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("case IDs must be unique non-empty strings")
        seen.add(case_id)
        metadata, body, rules = _load_case(case)
        decision = evaluate_metadata(metadata, rules)
        if "body" in case and decision.fetch_body:
            decision = evaluate_message(metadata, body, rules, prior=decision)
        expected = _record(case.get("expected"), f"{case_id}.expected")
        actual = {
            "relevance": decision.relevance.value,
            "reason": decision.reason.value,
            "fetch_body": decision.fetch_body,
            "privacy_hold": decision.privacy_hold.value if decision.privacy_hold else None,
        }
        if actual != expected:
            failures.append(f"{case_id}: expected {expected!r}, got {actual!r}")

    if failures:
        raise AssertionError("\n".join(failures))
    print(f"{len(seen)} synthetic filter cases passed")
    return len(seen)


if __name__ == "__main__":
    verify()
