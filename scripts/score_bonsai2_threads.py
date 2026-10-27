#!/usr/bin/env python3
"""Apply reviewed, fail-closed labels to retained Bonsai 2 thread outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from evaluate import DEFAULT_MODEL_DIR, ROOT, make_detector


def _key(text: str, evidence: list[dict[str, str]]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return text, tuple((item["message_id"], item["quote"]) for item in evidence)


def _prefix_hash(messages: list[dict]) -> str:
    encoded = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _review_map(adjudication: dict, case_id: str, checkpoint_id: str) -> dict:
    key = f"{case_id}/{checkpoint_id}"
    entries = adjudication.get("reviewed_outputs", {}).get(key, [])
    result = {}
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get("text"), str)
                or not isinstance(entry.get("evidence"), list)
                or entry.get("evidence_support") not in {"supported", "unsupported"}
                or not isinstance(entry.get("equivalent_expected_fact_ids"), list)):
            raise ValueError(f"malformed reviewed output for {key}")
        evidence = entry["evidence"]
        if any(not isinstance(item, dict) or set(item) != {"message_id", "quote"}
               or not isinstance(item["message_id"], str) or not isinstance(item["quote"], str)
               for item in evidence):
            raise ValueError(f"malformed evidence review for {key}")
        pair = _key(entry["text"], evidence)
        if pair in result:
            raise ValueError(f"duplicate reviewed output for {key}")
        ids = entry["equivalent_expected_fact_ids"]
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"invalid expected fact IDs for {key}")
        result[pair] = entry
    return result


def _string_leaves(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _string_leaves(child)


def _model_text_leaves(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            if key != "message_id":
                yield from _model_text_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from _model_text_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_leaves(child)


def score_output(row: dict, case: dict, checkpoint: dict, prefix: list[dict],
                 adjudication: dict, detector: Any) -> dict:
    content = row.get("content")
    parsed: dict = {}
    parse_error = not isinstance(content, str)
    if isinstance(content, str):
        try:
            parsed_value = json.loads(content)
            if isinstance(parsed_value, dict):
                parsed = parsed_value
            else:
                parse_error = True
        except json.JSONDecodeError:
            parse_error = True

    expected_message_ids = [message["id"] for message in prefix]
    schema_ok = (set(row) == {"case_id", "checkpoint_id", "input_message_ids", "input_sha256", "content"}
                 and row.get("case_id") == case["id"]
                 and row.get("checkpoint_id") == checkpoint["id"]
                 and row.get("input_message_ids") == expected_message_ids
                 and row.get("input_sha256") == _prefix_hash(prefix)
                 and set(parsed) == {"relevance", "facts"}
                 and parsed.get("relevance") in {"include", "deprioritize", "skip", "inspect"}
                 and isinstance(parsed.get("facts"), list))
    facts = parsed.get("facts", []) if isinstance(parsed.get("facts"), list) else []
    if len(facts) > 2 or (parsed.get("relevance") != "include" and facts):
        schema_ok = False
        parse_error = True

    prefix_by_id = {message["id"]: message for message in prefix}
    source_text = {message_id: "\n".join(message[key] for key in ("sender", "subject", "body"))
                   for message_id, message in prefix_by_id.items()}
    reviews = _review_map(adjudication, case["id"], checkpoint["id"])
    expected_by_id = {fact["id"]: fact for fact in checkpoint["expected_facts"]}
    seen_pairs = set()
    scored_facts = []
    for fact in facts:
        if (not isinstance(fact, dict) or set(fact) != {"text", "evidence"}
                or not isinstance(fact.get("text"), str) or not isinstance(fact.get("evidence"), list)):
            parse_error = True
            continue
        text = fact["text"]
        evidence = fact["evidence"]
        if any(not isinstance(item, dict) or set(item) != {"message_id", "quote"}
               or not isinstance(item["message_id"], str) or not isinstance(item["quote"], str)
               for item in evidence) or not evidence:
            parse_error = True
            continue
        pair = _key(text, evidence)
        annotation = reviews.get(pair)
        duplicate = pair in seen_pairs
        seen_pairs.add(pair)
        evidence_supported = all(
            item["message_id"] in source_text
            and bool(item["quote"])
            and item["quote"] in source_text[item["message_id"]]
            for item in evidence
        )
        reviewed_ids = annotation["equivalent_expected_fact_ids"] if annotation else []
        useful_ids = [fact_id for fact_id in reviewed_ids if fact_id in expected_by_id]
        unsupported_label = bool(annotation and annotation["evidence_support"] != "supported")
        all_strings = [text, *(item["quote"] for item in evidence)]
        prohibited = [secret for secret in checkpoint["prohibited_disclosures"]
                      if any(secret.casefold() in value.casefold() for value in all_strings)]
        detector_labels = [span.label.casefold() for value in all_strings for span in detector.detect(value)]
        privacy_risk = "hard-fail" if prohibited else "review" if any(label != "date" for label in detector_labels) else "clear"
        scored_facts.append({
            "text": text,
            "evidence": evidence,
            "review_status": "unreviewed" if annotation is None else "reviewed",
            "matching_expected_fact_ids": useful_ids,
            "reviewed_expected_fact_ids": reviewed_ids,
            "evidence_support": "supported" if evidence_supported and annotation and not unsupported_label else "unsupported",
            "privacy_risk": privacy_risk,
            "detector_labels": detector_labels,
            "duplicate_pair": duplicate,
            "unexpected_expected_fact_ids": [fact_id for fact_id in reviewed_ids if fact_id not in expected_by_id],
        })

    strings = list(_model_text_leaves(parsed))
    if isinstance(content, str) and parse_error:
        strings.append(content)
    prohibited_leak = any(secret.casefold() in value.casefold()
                          for secret in checkpoint["prohibited_disclosures"] for value in strings)
    privacy_review = any(span.label.casefold() != "date"
                         for value in strings for span in detector.detect(value))
    recovered_ids = {
        fact_id for fact in scored_facts
        if fact["review_status"] == "reviewed" and fact["evidence_support"] == "supported"
        and fact["privacy_risk"] == "clear" and not fact["duplicate_pair"]
        for fact_id in fact["matching_expected_fact_ids"]
    }
    credited_ids = [fact_id for fact in scored_facts for fact_id in fact["matching_expected_fact_ids"]]
    duplicate_expected_ids = sorted({fact_id for fact_id in credited_ids if credited_ids.count(fact_id) > 1})
    stale_text_emitted = [stale for stale in checkpoint["absent_fact_texts"]
                          if any(stale.casefold() in fact["text"].casefold() for fact in scored_facts)]
    case_result = {
        "case_id": case["id"], "checkpoint_id": checkpoint["id"],
        "input_message_ids": expected_message_ids, "input_sha256": _prefix_hash(prefix),
        "expected_relevance": checkpoint["expected_relevance"],
        "predicted_relevance": parsed.get("relevance"),
        "relevance_correct": parsed.get("relevance") == checkpoint["expected_relevance"],
        "expected_fact_ids": sorted(expected_by_id), "recovered_fact_ids": sorted(recovered_ids),
        "missing_fact_ids": sorted(set(expected_by_id) - recovered_ids),
        "absent_fact_texts": checkpoint["absent_fact_texts"],
        "stale_fact_texts_emitted": stale_text_emitted,
        "parse_error": parse_error, "schema_error": not schema_ok,
        "unreviewed_fact_count": sum(fact["review_status"] == "unreviewed" for fact in scored_facts),
        "unsupported_evidence_count": sum(fact["evidence_support"] != "supported" for fact in scored_facts),
        "prohibited_disclosure_count": sum(fact["privacy_risk"] == "hard-fail" for fact in scored_facts) + int(prohibited_leak),
        "privacy_review_count": sum(fact["privacy_risk"] == "review" for fact in scored_facts) + int(privacy_review),
        "duplicate_pair_count": sum(fact["duplicate_pair"] for fact in scored_facts),
        "duplicate_expected_fact_ids": duplicate_expected_ids,
        "unexpected_expected_fact_ids": sorted({fact_id for fact in scored_facts for fact_id in fact["unexpected_expected_fact_ids"]}),
        "facts": scored_facts,
    }
    case_result["gate_passed"] = (
        schema_ok and not parse_error and case_result["relevance_correct"]
        and not case_result["missing_fact_ids"] and not stale_text_emitted
        and case_result["unreviewed_fact_count"] == 0
        and case_result["unsupported_evidence_count"] == 0
        and case_result["prohibited_disclosure_count"] == 0
        and case_result["privacy_review_count"] == 0
        and case_result["duplicate_pair_count"] == 0
        and not case_result["duplicate_expected_fact_ids"]
        and not case_result["unexpected_expected_fact_ids"]
    )
    return case_result


def score_run(output_path: Path, cases: list[dict], adjudication: dict, detector: Any) -> dict:
    outputs = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(outputs, list) or any(not isinstance(row, dict) for row in outputs):
        raise ValueError(f"{output_path} must contain a list of outputs")
    expected = [(case, checkpoint, case["messages"][: next(i for i, message in enumerate(case["messages"])
                    if message["id"] == checkpoint["through_message_id"]) + 1])
                for case in cases for checkpoint in case["checkpoints"]]
    expected_keys = [(case["id"], checkpoint["id"]) for case, checkpoint, _ in expected]
    output_keys = [(row.get("case_id"), row.get("checkpoint_id")) for row in outputs]
    coverage_error = len(output_keys) != len(expected_keys) or output_keys != expected_keys
    output_by_key = {}
    for key, row in zip(output_keys, outputs):
        output_by_key.setdefault(key, row)
    results = []
    for case, checkpoint, prefix in expected:
        row = output_by_key.get((case["id"], checkpoint["id"]), {})
        if row:
            results.append(score_output(row, case, checkpoint, prefix, adjudication, detector))
        else:
            results.append({"case_id": case["id"], "checkpoint_id": checkpoint["id"], "gate_passed": False, "missing_output": True})
    grouped = []
    for case in cases:
        case_results = [result for result in results if result["case_id"] == case["id"]]
        grouped.append({"id": case["id"], "checkpoint_count": len(case_results),
                        "gate_passed": not coverage_error and len(case_results) == len(case["checkpoints"])
                        and all(result["gate_passed"] for result in case_results),
                        "checkpoints": case_results})
    return {
        "run": output_path.name[:2], "case_count": len(cases), "checkpoint_count": len(expected),
        "case_coverage_error": coverage_error, "gate_passed": not coverage_error and all(case["gate_passed"] for case in grouped),
        "passed_case_count": sum(case["gate_passed"] for case in grouped),
        "passed_checkpoint_count": sum(result["gate_passed"] for result in results),
        "cases": grouped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fixtures", type=Path, default=ROOT / "fixtures/thread-evaluation.json")
    parser.add_argument("--adjudication", type=Path, default=ROOT / "fixtures/thread-semantic-adjudication.json")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args()
    fixture = json.loads(args.fixtures.read_text(encoding="utf-8"))
    cases = fixture["thread_cases"]
    adjudication = json.loads(args.adjudication.read_text(encoding="utf-8"))
    if adjudication.get("schema_version") != 1:
        parser.error("thread adjudications must use schema_version 1")
    lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8"))
    detector = make_detector("rules+gliner", args.model_dir.expanduser(), lock)
    output_files = sorted(args.run_dir.glob("*-thread-outputs.json"))
    if not output_files:
        parser.error("no retained thread outputs found")
    runs = [score_run(path, cases, adjudication, detector) for path in output_files]
    gate_by_run = {int(run["run"]): run["gate_passed"] for run in runs}
    inference_reports = {}
    for path in args.run_dir.glob("*-thread.json"):
        inference = json.loads(path.read_text(encoding="utf-8"))
        inference.pop("gate_passed", None)
        inference["runner_passed"] = inference.get("runner_error_count") == 0
        run_number = int(path.name.split("-", 1)[0])
        inference["reviewed_gate_passed"] = gate_by_run.get(run_number, False)
        path.write_text(json.dumps(inference, indent=2) + "\n", encoding="utf-8")
        inference_reports[run_number] = inference
    for run in runs:
        run_number = int(run["run"])
        run["inference"] = inference_reports.get(run_number)
    summary_path = args.run_dir / "thread-summary.json"
    inference_summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    for inference in inference_summary.get("runs", []):
        inference.pop("gate_passed", None)
        inference["runner_passed"] = inference.get("runner_error_count") == 0
        inference["reviewed_gate_passed"] = gate_by_run.get(inference["run"], False)
    if inference_summary:
        inference_summary["reviewed_gate_passed_each_run"] = all(gate_by_run.values())
        inference_summary["reviewed_gate_results"] = [gate_by_run.get(index, False)
                                                       for index in sorted(gate_by_run)]
        summary_path.write_text(json.dumps(inference_summary, indent=2) + "\n", encoding="utf-8")
    report = {
        "schema_version": 1, "model": "prism-ml/Ternary-Bonsai-2-27B-mlx-2bit",
        "candidate": args.run_dir.name, "inference_enabled_during_scoring": False,
        "semantic_labels": "reviewed exact fact and message-attributed evidence pairs with explicit support and expected-fact IDs",
        "coverage_contract": "every case/checkpoint appears once in fixture order; each output binds to the exact chronological visible message prefix by ID and SHA-256",
        "gate_contract": "each checkpoint must match relevance, recover all current reviewed facts, omit obsolete fact text, and have no parse, schema, review, evidence, privacy, duplicate, or coverage errors",
        "memory_scope": inference_summary.get("memory_scope"),
        "sampling": inference_summary.get("sampling"),
        "run_count": len(runs), "gate_passed_each_run": all(run["gate_passed"] for run in runs), "runs": runs,
    }
    output = args.output or args.run_dir / "reviewed-thread-semantic-gate.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for run in runs:
        print(json.dumps({key: value for key, value in run.items() if key != "cases"}))
        for case in run["cases"]:
            for checkpoint in case["checkpoints"]:
                print(f"{case['id']}/{checkpoint['checkpoint_id']}", json.dumps(checkpoint, ensure_ascii=False))
    return 0 if report["gate_passed_each_run"] else 1


if __name__ == "__main__":
    sys.exit(main())
