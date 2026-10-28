"""Local Bonsai 2 extraction with the evaluated prompts, sampling, and output validation.

Model output is a proposal. It is validated against the source text here and stays local
until the user approves each fact and the final privacy check passes at release time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
from typing import Protocol

from . import ROOT
from .paths import MLX_PYTHON, MODEL_DIR, data_dir

MODEL_KEY = "ternary-bonsai-2-27b-mlx-2bit"
MESSAGE_PROMPT_VERSION = "6-security-scope"
THREAD_PROMPT_VERSION = "thread-1-current-state"
MAX_THREAD_MESSAGES = 5
MAX_THREAD_CHARS = 6000
MAX_FACTS = 2
MAX_FACT_CHARS = 300
SAMPLING = {
    "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0,
    "presence_penalty": 1.5, "presence_context_size": 64, "repetition_penalty": 1.0,
    "enable_thinking": False,
}
RELEVANCE = {"include", "deprioritize", "skip", "inspect"}


@dataclass
class ProposedFact:
    text: str
    evidence: list[tuple[str, str]]


@dataclass
class Extraction:
    relevance: str
    facts: list[ProposedFact]
    prompt_version: str
    rejected: list[str] = field(default_factory=list)


class Extractor(Protocol):
    name: str

    def extract(self, messages: list[dict]) -> Extraction: ...


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def validate(content: str | None, messages: list[dict], prompt_version: str) -> Extraction:
    """Reject malformed output and any fact whose evidence is not an exact source excerpt."""
    try:
        payload = json.loads(content or "")
    except json.JSONDecodeError:
        return Extraction("inspect", [], prompt_version, ["malformed_output"])
    if not isinstance(payload, dict) or payload.get("relevance") not in RELEVANCE:
        return Extraction("inspect", [], prompt_version, ["malformed_output"])
    relevance = payload["relevance"]
    raw_facts = payload.get("facts")
    if not isinstance(raw_facts, list):
        return Extraction("inspect", [], prompt_version, ["malformed_output"])
    if relevance != "include":
        rejected = ["facts_on_non_include"] if raw_facts else []
        return Extraction(relevance, [], prompt_version, rejected)

    sources = {message["id"]: _normalize(f"{message['subject']}\n{message['body']}") for message in messages}
    facts: list[ProposedFact] = []
    rejected: list[str] = []
    for raw in raw_facts[:MAX_FACTS]:
        if not isinstance(raw, dict) or not isinstance(raw.get("text"), str) or not raw["text"].strip():
            rejected.append("malformed_fact")
            continue
        text = " ".join(raw["text"].split())
        if len(text) > MAX_FACT_CHARS:
            rejected.append("fact_too_long")
            continue
        evidence_items = raw.get("evidence")
        if isinstance(evidence_items, str):
            evidence_items = [{"message_id": messages[-1]["id"], "quote": evidence_items}]
        if not isinstance(evidence_items, list):
            rejected.append("malformed_evidence")
            continue
        evidence: list[tuple[str, str]] = []
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            message_id, quote = item.get("message_id"), item.get("quote")
            if len(messages) == 1:
                message_id = messages[0]["id"]
            if (isinstance(quote, str) and quote.strip() and message_id in sources
                    and _normalize(quote) in sources[message_id]):
                evidence.append((message_id, " ".join(quote.split())))
        if not evidence:
            rejected.append("unsupported_evidence")
            continue
        facts.append(ProposedFact(text, evidence))
    if len(raw_facts) > MAX_FACTS:
        rejected.append("too_many_facts")
    return Extraction(relevance, facts, prompt_version, rejected)


def bound_thread(messages: list[dict]) -> list[dict]:
    """Keep the newest messages within the evaluated context budget."""
    kept: list[dict] = []
    total = 0
    for message in reversed(messages[-MAX_THREAD_MESSAGES:]):
        size = len(message["subject"]) + len(message["body"])
        if kept and total + size > MAX_THREAD_CHARS:
            break
        kept.append(message)
        total += size
    return list(reversed(kept))


class BonsaiExtractor:
    name = f"{MODEL_KEY}"

    def __init__(self, port: int = 18229) -> None:
        self.port = port
        self.server: subprocess.Popen[bytes] | None = None
        self.model_id: str | None = None
        self._lock = threading.Lock()

    def _start(self) -> None:
        from evaluate_bonsai2_mlx import wait_until_ready

        lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8"))["models"][MODEL_KEY]
        model_dir = MODEL_DIR / MODEL_KEY
        weights = model_dir / lock["weights_file"]
        if not weights.is_file() or weights.stat().st_size != lock["file_size_bytes"]:
            raise RuntimeError("pinned Bonsai 2 checkpoint is missing or has the wrong size")
        if not MLX_PYTHON.is_file():
            raise RuntimeError(f"MLX runtime is missing: {MLX_PYTHON}")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", self.port))
        environment = os.environ.copy()
        environment.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        log = (data_dir() / "mlx-server.log").open("wb")
        self.server = subprocess.Popen(
            [str(MLX_PYTHON), "-m", "mlx_vlm.server", "--model", str(model_dir), "--host", "127.0.0.1",
             "--port", str(self.port), "--max-kv-size", "4096", "--max-num-seqs", "1",
             "--max-tokens", "512", "--enable-thinking"],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=environment,
        )
        self.model_id = wait_until_ready(self.server, self.port)

    def extract(self, messages: list[dict]) -> Extraction:
        from evaluate_bonsai2_threads import PROMPT as THREAD_PROMPT
        from evaluate_qwen import SYSTEM_PROMPTS, call_api

        with self._lock:
            if self.server is None or self.server.poll() is not None:
                self._start()
            messages = bound_thread(messages)
            if len(messages) == 1:
                message = messages[0]
                system, version = SYSTEM_PROMPTS[MESSAGE_PROMPT_VERSION], MESSAGE_PROMPT_VERSION
                user = {"sender": message["sender"], "subject": message["subject"], "body": message["body"]}
                max_tokens = 512
            else:
                system, version = THREAD_PROMPT, THREAD_PROMPT_VERSION
                user = {"thread_id": "local", "messages": [
                    {key: message[key] for key in ("id", "sent_at", "sender", "subject", "body")}
                    for message in messages
                ]}
                max_tokens = 384
            response = call_api(self.port, "/v1/chat/completions", {
                "model": self.model_id,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False) + " /no_think"},
                ],
                **SAMPLING,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            })
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = None
        return validate(content if isinstance(content, str) else None, messages, version)

    def stop(self) -> None:
        from evaluate_qwen import stop_server

        if self.server is not None:
            stop_server(self.server)
            self.server = None


def category(reason: str, text: str) -> str:
    lowered = text.casefold()
    if reason == "security_alert" or re.search(r"sign-in|security|password", lowered):
        return "security"
    if re.search(r"\b(moved|changed|postponed|rescheduled|now due|new date)\b", lowered):
        return "change"
    if re.search(r"\b(decided|decision|confirmed|approved)\b", lowered):
        return "decision"
    if re.search(r"\b(by|due|deadline|before)\b.{0,40}\d", lowered):
        return "deadline"
    if re.search(r"\b(please|requests?|asks?|needs? to|must)\b", lowered):
        return "request"
    return "summary"


def runtime_available() -> str | None:
    """Return a reason the local model cannot run, or None."""
    lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8"))["models"][MODEL_KEY]
    weights = MODEL_DIR / MODEL_KEY / lock["weights_file"]
    if not weights.is_file():
        return "Bonsai 2 weights are not downloaded"
    if not Path(MLX_PYTHON).is_file():
        return "MLX runtime venv is missing"
    return None
