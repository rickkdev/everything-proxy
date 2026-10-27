#!/usr/bin/env python3
"""Verify fail-closed thread scoring against retained synthetic outputs."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

from evaluate import ROOT
from score_bonsai2_threads import score_run


class NoopDetector:
    def detect(self, _text: str):
        return ()


def score_mutation(outputs: list[dict], cases: list[dict], adjudication: dict) -> dict:
    with tempfile.TemporaryDirectory() as temp:
        output_path = Path(temp) / "mutated-thread-outputs.json"
        output_path.write_text(json.dumps(outputs), encoding="utf-8")
        return score_run(output_path, cases, adjudication, NoopDetector())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / ".audit/model-quality-trials/ternary-bonsai-2-27b-mlx-expanded-screen")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "fixtures/thread-evaluation.json")
    parser.add_argument("--adjudication", type=Path, default=ROOT / "fixtures/thread-semantic-adjudication.json")
    args = parser.parse_args()
    run_dir = args.run_dir
    fixture = json.loads(args.fixtures.read_text(encoding="utf-8"))
    cases = fixture["thread_cases"]
    adjudication = json.loads(args.adjudication.read_text(encoding="utf-8"))
    source_path = next(run_dir.glob("*-thread-outputs.json"))
    retained = json.loads(source_path.read_text(encoding="utf-8"))
    baseline = score_mutation(copy.deepcopy(retained), cases, adjudication)
    assert not baseline["case_coverage_error"], "retained screen must cover every fixture checkpoint"
    failed_checkpoints = {
        (checkpoint["case_id"], checkpoint["checkpoint_id"])
        for case in baseline["cases"] for checkpoint in case["checkpoints"]
        if not checkpoint["gate_passed"]
    }
    assert ("workshop-brief-thread-001", "brief-completed") in failed_checkpoints
    assert ("announcement-pause-resume-thread-001", "announcement-paused") in failed_checkpoints

    missing = score_mutation(retained[:-1], cases, adjudication)
    assert missing["case_coverage_error"] and not missing["gate_passed"]

    reordered = score_mutation(list(reversed(retained)), cases, adjudication)
    assert reordered["case_coverage_error"] and not reordered["gate_passed"]

    wrong_prefix = copy.deepcopy(retained)
    wrong_prefix[1]["input_message_ids"].reverse()
    result = score_mutation(wrong_prefix, cases, adjudication)
    revised = result["cases"][0]["checkpoints"][1]
    assert revised["schema_error"] and not revised["gate_passed"]

    future_evidence = copy.deepcopy(retained)
    payload = json.loads(future_evidence[0]["content"])
    payload["facts"][0]["evidence"] = [{
        "message_id": "deadline-revision-001-m2",
        "quote": "The deadline has moved from August 7 to August 14.",
    }]
    future_evidence[0]["content"] = json.dumps(payload)
    result = score_mutation(future_evidence, cases, adjudication)
    first = result["cases"][0]["checkpoints"][0]
    assert first["unsupported_evidence_count"] and not first["gate_passed"]

    unreviewed = copy.deepcopy(retained)
    payload = json.loads(unreviewed[0]["content"])
    payload["facts"][0]["text"] = "The launch plan is approved for August 7."
    unreviewed[0]["content"] = json.dumps(payload)
    result = score_mutation(unreviewed, cases, adjudication)
    first = result["cases"][0]["checkpoints"][0]
    assert first["unreviewed_fact_count"] and not first["gate_passed"]

    secret_leak = copy.deepcopy(retained)
    security_row = next(row for row in secret_leak
                        if row["case_id"] == "security-context-thread-001"
                        and row["checkpoint_id"] == "blocked-sign-in")
    payload = json.loads(security_row["content"])
    payload["facts"][0]["text"] += " Recovery code RC-7K4M-9Q2P."
    security_row["content"] = json.dumps(payload)
    result = score_mutation(secret_leak, cases, adjudication)
    security_first = result["cases"][2]["checkpoints"][0]
    assert security_first["prohibited_disclosure_count"] and not security_first["gate_passed"]

    unsupported_quote = copy.deepcopy(retained)
    payload = json.loads(unsupported_quote[0]["content"])
    payload["facts"][0]["evidence"][0]["quote"] = "An unrelated statement."
    unsupported_quote[0]["content"] = json.dumps(payload)
    result = score_mutation(unsupported_quote, cases, adjudication)
    first = result["cases"][0]["checkpoints"][0]
    assert first["unreviewed_fact_count"] and first["unsupported_evidence_count"] and not first["gate_passed"]

    duplicate = copy.deepcopy(retained)
    payload = json.loads(duplicate[0]["content"])
    payload["facts"].append(copy.deepcopy(payload["facts"][0]))
    duplicate[0]["content"] = json.dumps(payload)
    result = score_mutation(duplicate, cases, adjudication)
    first = result["cases"][0]["checkpoints"][0]
    assert first["duplicate_pair_count"] and first["duplicate_expected_fact_ids"] and not first["gate_passed"]

    stale = copy.deepcopy(retained)
    payload = json.loads(stale[1]["content"])
    payload["facts"][0] = {
        "text": "The draft is due August 7.",
        "evidence": [{"message_id": "deadline-revision-001-m1", "quote": "Please send the draft by August 7."}],
    }
    stale[1]["content"] = json.dumps(payload)
    result = score_mutation(stale, cases, adjudication)
    revised = result["cases"][0]["checkpoints"][1]
    assert revised["stale_fact_texts_emitted"] and revised["unreviewed_fact_count"] and not revised["gate_passed"]

    print(json.dumps({"negative_controls": 9, "passed": 9,
                      "screen_coverage_complete": True, "screen_gate_passed": baseline["gate_passed"],
                      "rejected_missing_and_reordered_coverage": True,
                      "rejected_wrong_prefix_and_future_evidence": True,
                      "rejected_unreviewed_and_unsupported_facts": True,
                      "rejected_recovery_code_disclosure": True,
                      "rejected_duplicate_credit_and_stale_deadline": True}))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    raise SystemExit(main())
