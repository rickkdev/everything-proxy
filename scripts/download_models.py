#!/usr/bin/env python3
"""Download pinned evaluation checkpoints to the user's local cache."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MODEL_LOCK = ROOT / "model-lock.json"
DEFAULT_CACHE = Path.home() / ".cache" / "everything-proxy" / "models"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "model",
        choices=(
            "gliner",
            "privacy-filter",
            "qwen3-4b-q4km",
            "qwen3-8b-q4km",
            "ternary-bonsai-2-27b-mlx-2bit",
            "qwen3-1_7b-q8_0",
            "bonsai-1_7b-q1_0",
            "ternary-bonsai-1_7b-q2_0-g64",
        ),
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args(argv)

    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        parser.error("install requirements-model-evaluation.txt first")

    lock = json.loads(MODEL_LOCK.read_text(encoding="utf-8"))
    model = lock["models"][args.model]
    destination = args.cache_dir.expanduser() / args.model
    try:
        if "filename" in model:
            path = hf_hub_download(
                repo_id=model["repo_id"],
                filename=model["filename"],
                revision=model["revision"],
                local_dir=destination,
            )
            print(f"downloaded {args.model} revision {model['revision']} to {path}")
            return 0
        path = snapshot_download(
            repo_id=model["repo_id"],
            revision=model["revision"],
            local_dir=destination,
            allow_patterns=(
                "config.json",
                "model.safetensors",
                "tokenizer.json",
                "tokenizer_config.json",
                "viterbi_calibration.json",
            )
            if args.model == "privacy-filter"
            else None,
        )
        if args.model == "gliner":
            dependency_dirs: dict[str, Path] = {}
            for dependency in lock["models"]["gliner_dependencies"]:
                name = dependency["name"]
                local_path = destination / "dependencies" / name
                snapshot_download(
                    repo_id=dependency["repo_id"],
                    revision=dependency["revision"],
                    local_dir=local_path,
                    allow_patterns=(
                        "config.json",
                        "tokenizer.json",
                        "tokenizer_config.json",
                        "special_tokens_map.json",
                        "vocab.txt",
                        "spm.model",
                    ),
                )
                dependency_dirs[name] = local_path
            config_path = destination / "gliner_config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["model_name"] = str(dependency_dirs["deberta"])
            config["labels_encoder"] = str(dependency_dirs["labels"])
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"model download failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"downloaded {args.model} revision {model['revision']} to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
