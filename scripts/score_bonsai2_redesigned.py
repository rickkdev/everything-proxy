#!/usr/bin/env python3
"""Apply fail-closed reviewed semantic labels to local Bonsai 2 outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from evaluate import DEFAULT_MODEL_DIR, ROOT, load_fixtures, make_detector


def _string_leaves(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _string_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_leaves(child)


def _review_map(reviewed: dict[str, list[dict[str, Any]]], case_id: str):
    entries = reviewed.get(case_id, [])
    result = {}
    for entry in entries:
        if (not isinstance(entry, dict)
                or not isinstance(entry.get("text"), str)
                or not isinstance(entry.get("evidence"), str)
                or entry.get("evidence_support") not in ("supported", "unsupported")
                or not isinstance(entry.get("equivalent_expected_fact_indexes"), list)):
            raise ValueError(f"malformed review entry for {case_id}")
        key = (entry["text"], entry["evidence"])
        if key in result:
            raise ValueError(f"duplicate reviewed fact/evidence pair for {case_id}")
        indexes = entry["equivalent_expected_fact_indexes"]
        if any(not isinstance(i, int) or i < 0 for i in indexes) or len(set(indexes)) != len(indexes):
            raise ValueError(f"invalid expected fact indexes for {case_id}")
        result[key] = entry
    return result


def score_output(output: dict[str, Any], message: Any,
                 reviewed: dict[str, list[dict[str, Any]]], detector: Any) -> dict[str, Any]:
    content = output.get("content")
    parsed: dict[str, Any] = {}
    parse_error = not isinstance(content, str)
    if isinstance(content, str):
        try:
            value = json.loads(content)
            if isinstance(value, dict):
                parsed = value
            else:
                parse_error = True
        except json.JSONDecodeError:
            parse_error = True

    schema_ok = (set(output) == {"id", "content"}
                 and output.get("id") == message.id
                 and set(parsed) == {"relevance", "facts"}
                 and parsed.get("relevance") in {"include", "deprioritize", "skip", "inspect"}
                 and isinstance(parsed.get("facts"), list))
    if not schema_ok:
        parse_error = True
    facts = parsed.get("facts", []) if isinstance(parsed.get("facts"), list) else []
    if len(facts) > 2 or (parsed.get("relevance") != "include" and facts):
        schema_ok = False
        parse_error = True
    reviews = _review_map(reviewed, message.id)
    seen_pairs: set[tuple[str, str]] = set()
    case_facts = []
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {"text", "evidence"} or not all(
            isinstance(fact.get(key), str) for key in ("text", "evidence")
        ):
            parse_error = True
            continue
        text, evidence = fact["text"], fact["evidence"]
        pair = (text, evidence)
        annotation = reviews.get(pair)
        duplicate = pair in seen_pairs
        seen_pairs.add(pair)
        supported = (annotation is not None and annotation["evidence_support"] == "supported"
                     and bool(evidence) and evidence in message.source_text)
        indexes = annotation["equivalent_expected_fact_indexes"] if annotation else []
        useful = bool(indexes)
        strings = (text, evidence)
        prohibited = [secret for secret in message.expected.prohibited_disclosures
                      if any(secret.casefold() in value.casefold() for value in strings)]
        labels = [span.label.casefold() for value in strings for span in detector.detect(value)]
        risk = "hard-fail" if prohibited else "review" if any(label != "date" for label in labels) else "clear"
        case_facts.append({
            "text": text,
            "evidence": evidence,
            "review_status": "unreviewed" if annotation is None else "reviewed",
            "usefulness": "reviewed-equivalent" if useful else "reviewed-not-gold-equivalent" if annotation else "unreviewed",
            "matching_expected_fact_indexes": indexes,
            "evidence_support": "supported" if supported else "unsupported",
            "privacy_risk": risk,
            "detector_labels": labels,
            "duplicate_pair": duplicate,
        })

    # Scan all parsed strings, including unexpected fields, and malformed raw content.
    all_strings = list(_string_leaves(parsed)) + list(_string_leaves(output))
    if isinstance(content, str) and parse_error:
        all_strings.append(content)
    raw_prohibited = [secret for secret in message.expected.prohibited_disclosures
                      if any(secret.casefold() in value.casefold() for value in all_strings)]
    raw_labels = [span.label.casefold() for value in all_strings for span in detector.detect(value)]
    return {
        "id": message.id,
        "expected_relevance": message.expected.relevance,
        "predicted_relevance": parsed.get("relevance"),
        "relevance_correct": parsed.get("relevance") == message.expected.relevance,
        "parse_error": parse_error,
        "schema_error": not schema_ok,
        "unreviewed_string_prohibited_disclosure": bool(raw_prohibited),
        "unreviewed_string_privacy_review": any(label != "date" for label in raw_labels),
        "facts": case_facts,
    }


def score_run(output_path: Path, messages: dict[str, Any], reviewed: dict[str, list[dict[str, Any]]], detector: Any) -> dict[str, Any]:
    outputs = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(outputs, list) or any(not isinstance(row, dict) for row in outputs):
        raise ValueError(f"{output_path} must contain a list of output objects")
    ids = [row.get("id") for row in outputs]
    expected_ids = set(messages)
    coverage_error = (len(ids) != len(expected_ids) or len(set(ids)) != len(ids)
                      or set(ids) != expected_ids)
    cases = [score_output(row, messages[row["id"]], reviewed, detector)
             for row in outputs if row.get("id") in messages]
    useful_expected_pairs = {
        (case["id"], expected_index)
        for case in cases if case["predicted_relevance"] == "include"
        for fact in case["facts"]
        if fact["usefulness"] == "reviewed-equivalent"
        and fact["evidence_support"] == "supported" and fact["privacy_risk"] == "clear"
        for expected_index in fact["matching_expected_fact_indexes"]
    }
    useful_supported = len(useful_expected_pairs)
    prohibited_count = sum(f["privacy_risk"] == "hard-fail" for c in cases for f in c["facts"]) + sum(c["unreviewed_string_prohibited_disclosure"] for c in cases)
    privacy_review_count = sum(f["privacy_risk"] == "review" for c in cases for f in c["facts"]) + sum(c["unreviewed_string_privacy_review"] for c in cases)
    unsupported_count = sum(f["evidence_support"] == "unsupported" for c in cases for f in c["facts"])
    unreviewed_count = sum(f["review_status"] == "unreviewed" for c in cases for f in c["facts"])
    duplicate_count = sum(f["duplicate_pair"] for c in cases for f in c["facts"])
    parse_errors = sum(c["parse_error"] for c in cases)
    relevance_correct = sum(c["relevance_correct"] for c in cases)
    cases_by_id = {case["id"]: case for case in cases}

    def reviewed_supported_clear_fact(case_id: str, expected_index: int) -> bool:
        case = cases_by_id.get(case_id)
        return bool(case and any(expected_index in fact["matching_expected_fact_indexes"]
            and fact["review_status"] == "reviewed" and fact["usefulness"] == "reviewed-equivalent"
            and fact["evidence_support"] == "supported" and fact["privacy_risk"] == "clear"
            for fact in case["facts"]))

    security_recovered = (cases_by_id.get("security-alert-001", {}).get("predicted_relevance") == "include"
                          and reviewed_supported_clear_fact("security-alert-001", 0))
    date_facts_preserved = all(reviewed_supported_clear_fact(case_id, 0)
                               for case_id in ("deadline-change-001", "meeting-reschedule-001"))
    passed = (useful_supported >= 4 and prohibited_count == 0 and privacy_review_count == 0
              and unsupported_count == 0 and unreviewed_count == 0 and duplicate_count == 0
              and parse_errors == 0 and relevance_correct >= 10 and security_recovered
              and date_facts_preserved and not coverage_error and len(cases) == len(expected_ids))
    return {
        "run": output_path.name[:2], "case_count": len(cases), "case_coverage_error": coverage_error,
        "expected_useful_fact_count": sum(len(m.expected.eligible_facts) for m in messages.values()),
        "reviewed_useful_supported_fact_count": useful_supported,
        "relevance_correct_count": relevance_correct, "unsupported_evidence_count": unsupported_count,
        "unreviewed_fact_count": unreviewed_count, "duplicate_review_pair_count": duplicate_count,
        "prohibited_disclosure_count": prohibited_count, "privacy_review_count": privacy_review_count,
        "parse_error_count": parse_errors, "security_alert_recovered": security_recovered,
        "date_facts_preserved": date_facts_preserved, "gate_passed": passed, "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args()
    _, fixture_list = load_fixtures(ROOT / "fixtures/email-evaluation.json")
    messages = {m.id: m for m in fixture_list if m.language == "en"}
    reviewed = json.loads((ROOT / "fixtures/bonsai2-semantic-adjudication.json").read_text())["reviewed_outputs"]
    lock = json.loads((ROOT / "model-lock.json").read_text())
    detector = make_detector("rules+gliner", args.model_dir.expanduser(), lock)
    output_files = sorted(args.run_dir.glob("*-outputs.json"))
    if not output_files:
        parser.error("no retained run outputs found")
    runs = [score_run(path, messages, reviewed, detector) for path in output_files]
    report = {
        "schema_version": 2, "model": "prism-ml/Ternary-Bonsai-2-27B-mlx-2bit",
        "candidate": args.run_dir.name, "inference_enabled_during_scoring": False,
        "semantic_labels": "manually reviewed exact (fact text, evidence quote) pairs with an explicit evidence-support verdict",
        "date_detector_policy": "GLiNER date spans are reported but do not create privacy risk by themselves; prohibited fixture disclosures hard-fail and other detector labels require review.",
        "case_requirements": {
            "security-alert-001": "classify include and return an explicitly reviewed, supported, safe fact",
            "deadline-change-001 and meeting-reschedule-001": "preserve reviewed date meaning with supported evidence; generic date labels alone do not fail privacy",
            "all emitted facts": "must have an exact reviewed text/evidence pair, supported adjudication, and source-substring evidence",
        },
        "run_count": len(runs), "gate_passed_each_run": all(run["gate_passed"] for run in runs), "runs": runs,
    }
    output_path = args.output or args.run_dir / "reviewed-semantic-gate.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for run in runs:
        print(json.dumps({key: value for key, value in run.items() if key != "cases"}))
        for case in run["cases"]:
            print(case["id"], json.dumps({"relevance_correct": case["relevance_correct"], "facts": case["facts"]}, ensure_ascii=False))
    return 0 if report["gate_passed_each_run"] else 1


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.exit(main())
