#!/usr/bin/env python3
"""Verify the synthetic model gate without running model inference."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "fixtures" / "model-gate-cases.json"
REPORT = ROOT / ".audit" / "synthetic-model-gate-results.json"


def normalize(text: str) -> str:
    return " ".join(text.casefold().split()).removesuffix(".")


def evaluate(case: dict[str, object]) -> dict[str, object]:
    expected = str(case["expected"])
    output = str(case["output"])
    source = str(case["source"])
    evidence = str(case["evidence"])
    prohibited_value = case["prohibited"]
    assert isinstance(prohibited_value, list)
    prohibited = [str(term) for term in prohibited_value]

    exact_text = normalize(expected) == normalize(output)
    evidence_supported = bool(evidence) and evidence in source
    useful = bool(case["meaning_equivalent"])
    privacy_violation = any(term.casefold() in output.casefold() for term in prohibited)

    old_pass = exact_text and evidence_supported and not bool(case["detector_flags_date"]) and not privacy_violation
    new_pass = useful and evidence_supported and not privacy_violation
    return {
        "id": case["id"],
        "before": "pass" if old_pass else "reject",
        "after": "hard-fail" if privacy_violation else "pass" if new_pass else "reject",
        "usefulness": "supported-meaning" if useful else "not-established",
        "evidence_support": "supported" if evidence_supported else "unsupported",
        "privacy_risk": "hard-fail" if privacy_violation else "no-prohibited-disclosure",
        "old_exact_text_match": exact_text,
        "old_detector_flagged_date": bool(case["detector_flags_date"]),
    }


def main() -> int:
    payload = json.loads(CASES.read_text())
    cases = payload["cases"]
    results = [evaluate(case) for case in cases]
    report = {
        "schema_version": 1,
        "inference_enabled": False,
        "case_count": len(results),
        "before_pass_count": sum(result["before"] == "pass" for result in results),
        "after_pass_count": sum(result["after"] == "pass" for result in results),
        "after_hard_fail_count": sum(result["after"] == "hard-fail" for result in results),
        "cases": results,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print("id | before | after | usefulness | evidence | privacy")
    for result in results:
        print(" | ".join(str(result[key]) for key in (
            "id", "before", "after", "usefulness", "evidence_support", "privacy_risk"
        )))
    print(f"before passes={report['before_pass_count']}/{len(results)}; after passes={report['after_pass_count']}/{len(results)}; hard fails={report['after_hard_fail_count']}")
    return 0 if len(results) == 9 and report["after_hard_fail_count"] == 2 else 1


if __name__ == "__main__":
    sys.exit(main())
