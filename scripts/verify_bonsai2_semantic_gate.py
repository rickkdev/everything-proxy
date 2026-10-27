#!/usr/bin/env python3
"""Verify the fail-closed behavior of the reviewed Bonsai semantic gate."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from evaluate import ROOT, load_fixtures
from score_bonsai2_redesigned import score_output, score_run


class NoopDetector:
    def detect(self, _text: str):
        return ()


def main() -> int:
    _, fixture_list = load_fixtures(ROOT / "fixtures/email-evaluation.json")
    message = next(item for item in fixture_list if item.id == "security-alert-001")
    reviewed = json.loads((ROOT / "fixtures/bonsai2-semantic-adjudication.json").read_text())["reviewed_outputs"]
    detector = NoopDetector()
    good = {
        "id": message.id,
        "content": json.dumps({"relevance": "include", "facts": [{
            "text": "A sign-in attempt from an unrecognized device was blocked on April 8, 2026.",
            "evidence": "A sign-in attempt from an unrecognized device was blocked on April 8, 2026.",
        }]}),
    }
    baseline = score_output(good, message, reviewed, detector)
    assert baseline["facts"][0]["evidence_support"] == "supported"
    assert baseline["facts"][0]["review_status"] == "reviewed"

    unrelated = json.loads(json.dumps(good))
    unrelated["content"] = json.dumps({"relevance": "include", "facts": [{
        "text": "A sign-in attempt from an unrecognized device was blocked on April 8, 2026.",
        "evidence": "New sign-in blocked",
    }]})
    rejected_quote = score_output(unrelated, message, reviewed, detector)
    assert rejected_quote["facts"][0]["evidence_support"] == "unsupported"
    assert rejected_quote["facts"][0]["review_status"] == "unreviewed"

    evidence_leak = json.loads(json.dumps(good))
    evidence_leak["content"] = json.dumps({"relevance": "include", "facts": [{
        "text": "A sign-in attempt was blocked.",
        "evidence": "Recovery code 9KQ2-WD7P-4M6R",
    }]})
    rejected_leak = score_output(evidence_leak, message, reviewed, detector)
    assert rejected_leak["facts"][0]["privacy_risk"] == "hard-fail"
    assert rejected_leak["unreviewed_string_prohibited_disclosure"]

    false_date = json.loads(json.dumps(good))
    false_date["content"] = json.dumps({"relevance": "include", "facts": [
        {"text": "A sign-in attempt from an unrecognized device was blocked on April 8, 2026.",
         "evidence": "A sign-in attempt from an unrecognized device was blocked on April 8, 2026."},
        {"text": "The May 2026 deadline moved to June 2026.", "evidence": "April 8, 2026"},
    ]})
    rejected_extra = score_output(false_date, message, reviewed, detector)
    assert rejected_extra["facts"][1]["review_status"] == "unreviewed"
    assert rejected_extra["facts"][1]["evidence_support"] == "unsupported"

    messages = {item.id: item for item in fixture_list if item.language == "en"}
    source_outputs = sorted((ROOT / ".audit/model-quality-trials/ternary-bonsai-2-27b-mlx-security-scope").glob("*-outputs.json"))[0]
    retained = json.loads(source_outputs.read_text())
    baseline_run = score_run(source_outputs, messages, reviewed, detector)
    assert baseline_run["gate_passed"]
    baseline_useful = baseline_run["reviewed_useful_supported_fact_count"]

    duplicate_gold = json.loads(json.dumps(retained))
    direct = next(row for row in duplicate_gold if row["id"] == "direct-request-001")
    direct_payload = json.loads(direct["content"])
    direct_payload["facts"].append(json.loads(json.dumps(direct_payload["facts"][0])))
    direct["content"] = json.dumps(direct_payload)

    noninclude_claim = json.loads(json.dumps(retained))
    direct = next(row for row in noninclude_claim if row["id"] == "direct-request-001")
    direct_payload = json.loads(direct["content"])
    direct_payload["relevance"] = "inspect"
    direct["content"] = json.dumps(direct_payload)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "mutated-outputs.json"
        tmp_path.write_text(json.dumps(duplicate_gold))
        duplicate_run = score_run(tmp_path, messages, reviewed, detector)
        assert duplicate_run["reviewed_useful_supported_fact_count"] == baseline_useful
        assert not duplicate_run["gate_passed"]
        tmp_path.write_text(json.dumps(noninclude_claim))
        noninclude_run = score_run(tmp_path, messages, reviewed, detector)
        assert not noninclude_run["gate_passed"]
        tmp_path.write_text(json.dumps([row for row in retained if row["id"] != "receipt-001"]))
        coverage_run = score_run(tmp_path, messages, reviewed, detector)
        assert coverage_run["case_coverage_error"] and not coverage_run["gate_passed"]

    print(json.dumps({"checks": 8, "passed": 8, "rejected_unrelated_quote": True,
                      "rejected_evidence_disclosure": True, "rejected_unreviewed_false_date": True,
                      "rejected_noninclude_facts": True, "prevented_duplicate_credit": True,
                      "rejected_case_coverage_gap": True}))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    raise SystemExit(main())
