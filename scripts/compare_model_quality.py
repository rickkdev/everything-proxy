#!/usr/bin/env python3
"""Run alternating, repeated synthetic model-quality evaluations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "everything-proxy" / "models"
QUALITY_METRICS = (
    "eligible_exact_expected_fact_text_count",
    "relevance_correct_count",
    "predicted_fact_count",
    "eligible_fact_count_after_privacy_check",
    "unsupported_evidence_count",
    "remaining_prohibited_fact_mention_count",
    "parse_error_count",
    "process_peak_rss_bytes",
    "system_peak_used_bytes",
)


def summarize(reports: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {
        name: {
            "median": statistics.median(report[name] for report in reports),
            "min": min(report[name] for report in reports),
            "max": max(report[name] for report in reports),
        }
        for name in QUALITY_METRICS
    }
    gates = [
        {
            "eligible_exact_fact_target": report["eligible_exact_expected_fact_text_count"] >= 4,
            "relevance_floor": report["relevance_correct_count"] >= 10,
            "fact_count_ceiling": report["predicted_fact_count"] <= 14,
            "parse_errors": report["parse_error_count"] == 0,
            "unsupported_evidence": report["unsupported_evidence_count"] == 0,
            "remaining_prohibited_mentions": report["remaining_prohibited_fact_mention_count"] == 0,
        }
        for report in reports
    ]
    return {
        "run_count": len(reports),
        "fixture_count_per_run": reports[0]["fixture_count"],
        "scored_message_count_per_run": reports[0]["scored_message_count"],
        "metrics": metrics,
        "gate_passed_each_run": all(all(run.values()) for run in gates),
        "gate_results": gates,
    }


def main(argv: list[str] | None = None) -> int:
    lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8"))
    candidates = tuple(name for name, model in lock["models"].items() if "filename" in model)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", choices=candidates, default="qwen3-4b-q4km")
    parser.add_argument("--candidate", choices=candidates, required=True)
    parser.add_argument("--fixtures", type=Path, default=ROOT / "fixtures/email-evaluation.json")
    parser.add_argument("--prompt-version", default="4-empty-noninclude")
    parser.add_argument("--privacy-detector", default="rules+gliner")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--context-size", type=int, default=4096)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--base-port", type=int, default=18200)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".audit/model-quality-trials")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    if args.baseline == args.candidate:
        parser.error("baseline and candidate must differ")
    if args.pairs < 5:
        parser.error("at least five alternating run pairs are required")

    for name in (args.baseline, args.candidate):
        entry = lock["models"][name]
        model_path = args.model_dir.expanduser() / name / entry["filename"]
        if not model_path.is_file():
            parser.error(f"model file is missing for {name}: {model_path}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports: dict[str, list[dict[str, Any]]] = {
        args.baseline: [],
        args.candidate: [],
    }
    runner_errors: list[dict[str, Any]] = []
    attempted_runs = 0
    for pair in range(args.pairs):
        order = (args.baseline, args.candidate) if pair % 2 == 0 else (args.candidate, args.baseline)
        for candidate in order:
            attempted_runs += 1
            output_path = args.output_dir / f"{attempted_runs:02d}-{candidate}.json"
            command = [
                sys.executable,
                str(ROOT / "scripts/evaluate_qwen.py"),
                "--candidate",
                candidate,
                "--prompt-version",
                args.prompt_version,
                "--privacy-detector",
                args.privacy_detector,
                "--fixtures",
                str(args.fixtures),
                "--model-dir",
                str(args.model_dir.expanduser()),
                "--context-size",
                str(args.context_size),
                "--max-tokens",
                str(args.max_tokens),
                "--port",
                str(args.base_port + attempted_runs),
                "--output",
                str(output_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                runner_errors.append(
                    {
                        "candidate": candidate,
                        "pair": pair + 1,
                        "return_code": result.returncode,
                        "stderr": result.stderr.strip(),
                    }
                )
                continue
            report = json.loads(output_path.read_text(encoding="utf-8"))
            if report["fixture_count"] <= 0 or report["scored_message_count"] <= 0:
                runner_errors.append(
                    {"candidate": candidate, "pair": pair + 1, "error": "no scored work"}
                )
                continue
            reports[candidate].append(report)

    summaries = {
        candidate: summarize(candidate_reports) if candidate_reports else None
        for candidate, candidate_reports in reports.items()
    }
    summary = {
        "baseline": args.baseline,
        "candidate": args.candidate,
        "prompt_version": args.prompt_version,
        "privacy_detector": args.privacy_detector,
        "context_size": args.context_size,
        "pairs_requested": args.pairs,
        "attempted_runs": attempted_runs,
        "completed_runs": sum(len(items) for items in reports.values()),
        "runner_error_count": len(runner_errors),
        "runner_errors": runner_errors,
        "work_count": {
            name: sum(report["scored_message_count"] for report in items)
            for name, items in reports.items()
        },
        "results": summaries,
    }
    summary_path = args.summary or args.output_dir / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if runner_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
