#!/usr/bin/env python3
"""Evaluate the pinned Bonsai 2 MLX checkpoint on synthetic email fixtures."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import time
from typing import Any
from urllib.error import HTTPError, URLError

from evaluate import DEFAULT_MODEL_DIR, ROOT, SystemMemorySampler, load_fixtures, make_detector
from evaluate_qwen import (
    DEFAULT_PROMPT_VERSION,
    ProcessMemorySampler,
    SYSTEM_PROMPTS,
    call_api,
    score_message,
    stop_server,
)


MODEL_KEY = "ternary-bonsai-2-27b-mlx-2bit"
OUTPUT_LIMITS = {
    "eligible_exact_expected_fact_text_count": 4,
    "relevance_correct_count": 10,
    "predicted_fact_count": 14,
    "parse_error_count": 0,
    "unsupported_evidence_count": 0,
    "remaining_prohibited_fact_mention_count": 0,
}


def wait_until_ready(server: subprocess.Popen[bytes], port: int) -> str:
    deadline = time.monotonic() + 300
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"mlx-vlm server exited during startup with code {server.returncode}")
        try:
            response = call_api(port, "/v1/models")
            models = response.get("data")
            if isinstance(models, list) and models and isinstance(models[0], dict):
                model_id = models[0].get("id")
                if isinstance(model_id, str) and model_id:
                    return model_id
            last_error = ValueError("mlx-vlm returned no model ID")
        except (HTTPError, OSError, URLError, ValueError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise TimeoutError(f"mlx-vlm server did not become ready within 300 seconds: {last_error}")


def score_run(
    messages: tuple[Any, ...],
    supported_languages: tuple[str, ...],
    model_id: str,
    port: int,
    prompt_version: str,
    detector: Any | None,
    max_tokens: int,
) -> tuple[dict[str, Any], list[str]]:
    results = []
    generated_outputs: list[dict[str, Any]] = []
    inference_times: list[float] = []
    errors: list[str] = []
    attempted_messages = 0
    for message in messages:
        if message.language not in supported_languages:
            results.append(score_message(message, supported_languages, None, None, detector))
            continue
        attempted_messages += 1
        request_body = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPTS[prompt_version]},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "sender": message.sender,
                            "subject": message.subject,
                            "body": message.body,
                        },
                        ensure_ascii=False,
                    )
                    + " /no_think",
                },
            ],
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0,
            "presence_penalty": 1.5,
            "presence_context_size": 64,
            "repetition_penalty": 1.0,
            "enable_thinking": False,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        before = time.perf_counter()
        try:
            response = call_api(port, "/v1/chat/completions", request_body)
        except (HTTPError, OSError, URLError, TimeoutError, ValueError) as exc:
            errors.append(f"{message.id}: {type(exc).__name__}: {exc}")
            continue
        duration_ms = (time.perf_counter() - before) * 1000
        inference_times.append(duration_ms)
        choices = response.get("choices")
        content = (
            choices[0].get("message", {}).get("content")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict)
            else None
        )
        generated_outputs.append({"id": message.id, "content": content})
        results.append(score_message(message, supported_languages, response, duration_ms, detector))

    scored = [result for result in results if not result.withheld]
    report = {
        "fixture_count": len(messages),
        "attempted_messages": attempted_messages,
        "scored_message_count": len(scored),
        "withheld_message_count": len(results) - len(scored),
        "expected_fact_count": sum(result.expected_fact_count for result in scored),
        "eligible_exact_expected_fact_text_count": sum(
            result.eligible_exact_expected_fact_text_count for result in scored
        ),
        "relevance_correct_count": sum(result.relevance_correct is True for result in scored),
        "predicted_fact_count": sum(result.predicted_fact_count for result in scored),
        "eligible_fact_count_after_privacy_check": sum(
            result.eligible_fact_count for result in scored
        ),
        "unsupported_evidence_count": sum(result.unsupported_evidence_count for result in scored),
        "remaining_prohibited_fact_mention_count": sum(
            result.remaining_prohibited_fact_mention_count for result in scored
        ),
        "parse_error_count": sum(result.parse_error for result in scored),
        "mean_inference_ms": (
            statistics.mean(inference_times) if inference_times else None
        ),
        "messages_per_minute": (
            len(inference_times) * 60_000 / sum(inference_times)
            if inference_times and sum(inference_times)
            else None
        ),
        "runner_error_count": len(errors),
        "runner_errors": errors,
        "work_count": len(scored),
        "generated_outputs": generated_outputs,
    }
    report["gate_passed"] = (
        report["eligible_exact_expected_fact_text_count"] >= OUTPUT_LIMITS[
            "eligible_exact_expected_fact_text_count"
        ]
        and report["relevance_correct_count"] >= OUTPUT_LIMITS["relevance_correct_count"]
        and report["predicted_fact_count"] <= OUTPUT_LIMITS["predicted_fact_count"]
        and report["parse_error_count"] == OUTPUT_LIMITS["parse_error_count"]
        and report["unsupported_evidence_count"] == OUTPUT_LIMITS["unsupported_evidence_count"]
        and report["remaining_prohibited_fact_mention_count"]
        == OUTPUT_LIMITS["remaining_prohibited_fact_mention_count"]
        and report["runner_error_count"] == 0
        and report["scored_message_count"] == 11
    )
    return report, errors


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_fields = (
        "eligible_exact_expected_fact_text_count",
        "relevance_correct_count",
        "predicted_fact_count",
        "eligible_fact_count_after_privacy_check",
        "unsupported_evidence_count",
        "remaining_prohibited_fact_mention_count",
        "parse_error_count",
        "mean_inference_ms",
        "messages_per_minute",
        "process_peak_rss_bytes",
        "system_peak_used_bytes",
    )
    metrics = {}
    for field in numeric_fields:
        values = [
            run[field]
            for run in runs
            if isinstance(run.get(field), (int, float))
        ]
        metrics[field] = {
            "median": statistics.median(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    return {
        "run_count": len(runs),
        "fixture_count_per_run": runs[0]["fixture_count"],
        "scored_message_count_per_run": runs[0]["scored_message_count"],
        "metrics": metrics,
        "gate_passed_each_run": all(run["gate_passed"] for run in runs),
        "gate_results": [run["gate_passed"] for run in runs],
        "runner_error_count": sum(run["runner_error_count"] for run in runs),
        "work_count": sum(run["work_count"] for run in runs),
    }


def main(argv: list[str] | None = None) -> int:
    lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8"))
    model = lock["models"][MODEL_KEY]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=ROOT / "fixtures/email-evaluation.json")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument(
        "--mlx-python",
        type=Path,
        default=Path.home() / ".cache/everything-proxy/venvs/bonsai-mlx/bin/python",
    )
    parser.add_argument("--privacy-detector", default="rules+gliner")
    parser.add_argument("--prompt-version", choices=tuple(SYSTEM_PROMPTS), default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--port", type=int, default=18227)
    parser.add_argument("--context-size", type=int, default=4096)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".audit/model-quality-trials/ternary-bonsai-2-27b-mlx",
    )
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("at least one full-corpus run is required")
    if args.privacy_detector not in {
        "rules", "gliner", "privacy-filter", "rules+gliner", "rules+privacy-filter"
    }:
        parser.error("unknown privacy detector profile")

    model_dir = args.model_dir.expanduser() / MODEL_KEY
    weights_path = model_dir / model["weights_file"]
    if not weights_path.is_file():
        parser.error(f"model checkpoint is missing: {weights_path}")
    actual_size = weights_path.stat().st_size
    if actual_size != model["file_size_bytes"]:
        parser.error(f"model weight size is {actual_size}, expected {model['file_size_bytes']}")
    mlx_python = args.mlx_python.expanduser()
    if not mlx_python.is_file():
        parser.error(f"MLX Python interpreter is missing: {mlx_python}")
    runtime_check = subprocess.run(
        [str(mlx_python), "-c", "import mlx, mlx_vlm"],
        capture_output=True,
        text=True,
        check=False,
    )
    if runtime_check.returncode:
        parser.error(f"MLX runtime is unavailable: {runtime_check.stderr.strip()}")

    supported_languages, messages = load_fixtures(args.fixtures)
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", args.port))
        except OSError as exc:
            parser.error(f"local port {args.port} is unavailable: {exc}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8"))
    server_log_path = args.output_dir / "mlx-server.log"
    server_command = [
        str(mlx_python),
        "-m",
        "mlx_vlm.server",
        "--model",
        str(model_dir),
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
        "--max-kv-size",
        str(args.context_size),
        "--max-num-seqs",
        "1",
        "--max-tokens",
        str(args.max_tokens),
        "--enable-thinking",
    ]
    runs: list[dict[str, Any]] = []
    all_errors: list[dict[str, Any]] = []
    server_started_at = time.perf_counter()
    process_memory: ProcessMemorySampler | None = None
    server: subprocess.Popen[bytes] | None = None
    detector_init_ms = 0.0
    server_environment = os.environ.copy()
    server_environment["HF_HUB_OFFLINE"] = "1"
    server_environment["TRANSFORMERS_OFFLINE"] = "1"
    with server_log_path.open("wb") as server_log, SystemMemorySampler() as memory:
        detector_start = time.perf_counter()
        detector = make_detector(args.privacy_detector, args.model_dir.expanduser(), lock)
        detector_init_ms = (time.perf_counter() - detector_start) * 1000
        server = subprocess.Popen(
            server_command,
            stdin=subprocess.DEVNULL,
            stdout=server_log,
            stderr=subprocess.STDOUT,
            env=server_environment,
        )
        try:
            process_memory = ProcessMemorySampler(server)
            process_memory.__enter__()
            model_id = wait_until_ready(server, args.port)
            model_init_ms = (time.perf_counter() - server_started_at) * 1000
            warmup = {
                "model": model_id,
                "messages": [{"role": "user", "content": "Return JSON: {\"ready\": true}"}],
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 20,
                "min_p": 0,
                "presence_penalty": 1.5,
                "presence_context_size": 64,
                "repetition_penalty": 1.0,
                "enable_thinking": False,
                "max_tokens": 16,
                "response_format": {"type": "json_object"},
            }
            warmup_response = call_api(args.port, "/v1/chat/completions", warmup)
            warmup_content = warmup_response["choices"][0]["message"]["content"]
            if not isinstance(warmup_content, str) or not isinstance(
                json.loads(warmup_content), dict
            ):
                raise ValueError("mlx-vlm warmup did not return a JSON object")
            for index in range(1, args.runs + 1):
                run, errors = score_run(
                    messages,
                    supported_languages,
                    model_id,
                    args.port,
                    args.prompt_version,
                    detector,
                    args.max_tokens,
                )
                run.update(
                    {
                        "run": index,
                        "model_init_ms": model_init_ms if index == 1 else None,
                        "process_peak_rss_bytes": process_memory.peak,
                        "system_peak_used_bytes": memory.peak,
                        "host_total_memory_bytes": memory.total,
                    }
                )
                generated_output_path = args.output_dir / f"{index:02d}-{MODEL_KEY}-outputs.json"
                generated_output_path.write_text(
                    json.dumps(run.pop("generated_outputs"), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                report_path = args.output_dir / f"{index:02d}-{MODEL_KEY}.json"
                report_path.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                runs.append(run)
                all_errors.extend({"run": index, "error": error} for error in errors)
                print(json.dumps(run, sort_keys=True), flush=True)
        finally:
            if process_memory is not None:
                process_memory.__exit__()
            if server is not None:
                stop_server(server)

    summary = {
        "model": model["repo_id"],
        "revision": model["revision"],
        "weights_sha256": model["sha256"],
        "runtime": "mlx-vlm==0.7.8 / mlx==0.32.3 / mlx-lm==0.32.0",
        "prompt_version": args.prompt_version,
        "privacy_detector": detector.name,
        "detector_init_ms": detector_init_ms,
        "sampling": {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0,
            "presence_penalty": 1.5,
            "presence_context_size": 64,
            "repetition_penalty": 1.0,
            "enable_thinking": False,
        },
        "max_tokens": args.max_tokens,
        "context_size": args.context_size,
        "attempted_runs": args.runs,
        "completed_runs": len(runs),
        "runner_errors": all_errors,
        "results": summarize(runs) if runs else None,
        "model_init_ms": model_init_ms if runs else None,
        "server_log": str(server_log_path),
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if not runs or all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
