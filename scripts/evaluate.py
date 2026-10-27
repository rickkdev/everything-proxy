#!/usr/bin/env python3
"""Evaluate local identifier detectors against synthetic email fixtures."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import resource
import sys
import threading
import time
from typing import Literal, Protocol


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "everything-proxy" / "models"
RULES_VERSION = "2026-10-26.1"
GLINER_LABELS = (
    "medical_record_number",
    "date_of_birth",
    "ssn",
    "date",
    "first_name",
    "email",
    "last_name",
    "customer_id",
    "employee_id",
    "name",
    "street_address",
    "phone_number",
    "ipv4",
    "credit_card_number",
    "license_plate",
    "device_identifier",
    "bank_routing_number",
    "date_time",
    "company_name",
    "unique_identifier",
    "biometric_identifier",
    "account_number",
    "api_key",
    "certificate_license_number",
    "health_plan_beneficiary_number",
    "coordinate",
    "tax_id",
    "url",
    "swift_bic",
    "password",
    "national_id",
    "pin",
)


@dataclass(frozen=True)
class ExpectedFact:
    text: str
    evidence: str | None = None


@dataclass(frozen=True)
class ExpectedResult:
    relevance: str
    prohibited_disclosures: tuple[str, ...]
    eligible_facts: tuple[ExpectedFact, ...]
    local_only_facts: tuple[ExpectedFact, ...]


@dataclass(frozen=True)
class MessageFixture:
    id: str
    language: str
    sender: str
    subject: str
    body: str
    expected: ExpectedResult

    @property
    def source_text(self) -> str:
        return "\n".join((self.sender, self.subject, self.body))


@dataclass(frozen=True)
class DetectedSpan:
    start: int
    end: int
    label: str


@dataclass(frozen=True)
class MessageScore:
    id: str
    withheld: bool
    gold_count: int
    covered_gold_count: int
    exact_match_count: int
    predicted_span_count: int
    extra_span_count: int


@dataclass(frozen=True)
class EvaluationReport:
    schema_version: int
    started_at: str
    finished_at: str
    detector: str
    detector_version: str
    fixture_file: str
    fixture_count: int
    scored_message_count: int
    withheld_message_count: int
    gold_span_count: int
    covered_gold_span_count: int
    full_coverage_recall: float | None
    exact_span_precision: float | None
    exact_span_count: int
    predicted_span_count: int
    extra_span_count: int
    model_init_ms: float
    warm_inference_ms: float
    process_peak_rss_bytes: int
    system_memory_before_bytes: int | None
    system_peak_used_bytes: int | None
    host_total_memory_bytes: int | None
    target_total_memory_bytes: int | None
    messages: tuple[MessageScore, ...]


class Detector(Protocol):
    name: str
    version: str

    def initialize(self) -> None: ...

    def detect(self, text: str) -> tuple[DetectedSpan, ...]: ...


RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "email",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    ),
    ("url", re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)),
    (
        "credential",
        re.compile(
            r"(?i)(?:recovery\s+code|access\s+token|api\s+key|password|secret)"
            r"\s*(?:is|:|=)?\s*[A-Z0-9._-]{6,}"
        ),
    ),
    ("invoice", re.compile(r"\b[A-Z]{2,}-INV-\d+\b", re.IGNORECASE)),
    ("card_suffix", re.compile(r"(?i)card ending\s+\d{4}")),
    (
        "medical_topic",
        re.compile(r"(?i)multiple sclerosis|medical leave|\bdiagnosis\b"),
    ),
)


def load_fixtures(path: Path) -> tuple[tuple[str, ...], tuple[MessageFixture, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("fixture root must use schema_version 1")
    languages = payload.get("language_support")
    records = payload.get("messages")
    if not isinstance(languages, list) or not all(
        isinstance(language, str) for language in languages
    ):
        raise ValueError("language_support must be a list of language codes")
    if not isinstance(records, list) or not records:
        raise ValueError("messages must be a non-empty list")

    messages: list[MessageFixture] = []
    ids: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"messages[{index}] must be an object")
        required = ("id", "language", "sender", "subject", "body", "expected")
        if any(not isinstance(record.get(key), str) for key in required[:-1]):
            raise ValueError(f"messages[{index}] is missing a string field")
        expected = record.get("expected")
        if not isinstance(expected, dict):
            raise ValueError(f"messages[{index}].expected must be an object")
        relevance = expected.get("relevance")
        disclosures = expected.get("prohibited_disclosures")
        facts = expected.get("facts", [])
        local_facts = expected.get("local_only_facts", [])
        if relevance not in {"include", "deprioritize", "skip", "inspect"}:
            raise ValueError(f"messages[{index}] has an invalid relevance decision")
        if not isinstance(disclosures, list) or not disclosures or not all(
            isinstance(value, str) and value for value in disclosures
        ):
            raise ValueError(f"messages[{index}] needs prohibited disclosure strings")
        if not isinstance(facts, list) or not isinstance(local_facts, list):
            raise ValueError(f"messages[{index}] facts must be lists")
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("text"), str)
            or not item["text"]
            for item in (*facts, *local_facts)
        ):
            raise ValueError(f"messages[{index}] facts need non-empty text fields")
        if any(
            not isinstance(item.get("evidence"), str) or not item["evidence"]
            for item in facts
        ):
            raise ValueError(f"messages[{index}] eligible facts need evidence strings")

        fixture = MessageFixture(
            id=record["id"],
            language=record["language"],
            sender=record["sender"],
            subject=record["subject"],
            body=record["body"],
            expected=ExpectedResult(
                relevance=relevance,
                prohibited_disclosures=tuple(disclosures),
                eligible_facts=tuple(
                    ExpectedFact(item["text"], item["evidence"]) for item in facts
                ),
                local_only_facts=tuple(ExpectedFact(item["text"]) for item in local_facts),
            ),
        )
        if fixture.id in ids:
            raise ValueError(f"messages[{index}] repeats id {fixture.id!r}")
        ids.add(fixture.id)
        if fixture.language in languages:
            for target in fixture.expected.prohibited_disclosures:
                if target not in fixture.source_text:
                    raise ValueError(
                        f"messages[{index}] prohibited disclosure is absent from source"
                    )
            for fact in fixture.expected.eligible_facts:
                if fact.evidence not in fixture.source_text:
                    raise ValueError(f"messages[{index}] fact evidence is absent from source")
        messages.append(fixture)
    return tuple(languages), tuple(messages)


def gold_spans(message: MessageFixture) -> tuple[DetectedSpan, ...]:
    spans: list[DetectedSpan] = []
    for target in message.expected.prohibited_disclosures:
        cursor = 0
        while True:
            start = message.source_text.find(target, cursor)
            if start < 0:
                break
            spans.append(DetectedSpan(start, start + len(target), "prohibited"))
            cursor = start + 1
    return tuple(spans)


class RulesDetector:
    name = "rules"
    version = RULES_VERSION

    def initialize(self) -> None:
        return None

    def detect(self, text: str) -> tuple[DetectedSpan, ...]:
        return tuple(
            DetectedSpan(match.start(), match.end(), label)
            for label, pattern in RULES
            for match in pattern.finditer(text)
        )


class PresidioPatternDetector:
    name = "presidio-patterns"

    def __init__(self, version: str) -> None:
        self.version = version
        self._recognizers = None

    def initialize(self) -> None:
        try:
            from presidio_analyzer import Pattern, PatternRecognizer
        except ImportError as exc:
            raise RuntimeError(
                "Presidio dependencies are missing; install requirements-model-evaluation.txt"
            ) from exc
        patterns = [(label, pattern.pattern) for label, pattern in RULES]
        patterns.extend(
            (
                ("phone", r"\+?\d(?:[\s().-]*\d){7,}"),
                ("currency", r"\b(?:USD|EUR|GBP)\s?\d+(?:\.\d{2})?\b"),
                ("customer_id", r"(?i)\b(?:customer|account|member)[\s_-]+id\s*[:#=]?\s*[A-Z0-9_-]{4,}\b"),
            )
        )
        self._recognizers = tuple(
            (entity, PatternRecognizer(
                supported_entity=entity.upper(),
                patterns=[Pattern(name=entity, regex=regex, score=0.85)],
                supported_language="en",
            ))
            for entity, regex in patterns
        )

    def detect(self, text: str) -> tuple[DetectedSpan, ...]:
        if self._recognizers is None:
            raise RuntimeError("Presidio pattern detector was not initialized")
        return tuple(
            DetectedSpan(result.start, result.end, result.entity_type)
            for entity, recognizer in self._recognizers
            for result in recognizer.analyze(text=text, entities=[entity.upper()])
        )


class GlinerDetector:
    name = "gretel-gliner"

    def __init__(self, model_dir: Path, revision: str) -> None:
        self.model_dir = model_dir
        self.version = revision
        self._model = None

    def initialize(self) -> None:
        try:
            import torch
            from gliner import GLiNER
        except ImportError as exc:
            raise RuntimeError(
                "GLiNER dependencies are missing; install requirements-model-evaluation.txt"
            ) from exc
        torch.set_num_threads(1)
        self._model = GLiNER.from_pretrained(
            str(self.model_dir), local_files_only=True
        )
        self._model.predict_entities(
            "Synthetic contact test at demo@example.invalid",
            list(GLINER_LABELS),
            threshold=0.7,
        )

    def detect(self, text: str) -> tuple[DetectedSpan, ...]:
        if self._model is None:
            raise RuntimeError("GLiNER detector was not initialized")
        entities = self._model.predict_entities(
            text, list(GLINER_LABELS), threshold=0.7
        )
        return tuple(
            DetectedSpan(int(item["start"]), int(item["end"]), str(item["label"]))
            for item in entities
        )


class PrivacyFilterDetector:
    name = "openai-privacy-filter"

    def __init__(self, model_dir: Path, revision: str) -> None:
        self.model_dir = model_dir
        self.version = revision
        self._classifier = None

    def initialize(self) -> None:
        try:
            import torch
            from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
        except ImportError as exc:
            raise RuntimeError(
                "Privacy Filter dependencies are missing; install requirements-model-evaluation.txt"
            ) from exc
        torch.set_num_threads(1)
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_dir, local_files_only=True
        )
        model = AutoModelForTokenClassification.from_pretrained(
            self.model_dir, local_files_only=True
        )
        self._classifier = pipeline(
            "token-classification",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy="simple",
            device=-1,
        )
        self.detect("Synthetic contact test at demo@example.invalid")

    def detect(self, text: str) -> tuple[DetectedSpan, ...]:
        if self._classifier is None:
            raise RuntimeError("Privacy Filter detector was not initialized")
        predictions = self._classifier(text)
        spans = sorted(
            (
                DetectedSpan(
                    int(item["start"]),
                    int(item["end"]),
                    str(item["entity_group"]),
                )
                for item in predictions
                if item.get("start") is not None and item.get("end") is not None
            ),
            key=lambda span: (span.start, span.end),
        )
        merged: list[DetectedSpan] = []
        for span in spans:
            start, end = span.start, span.end
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            if start == end:
                continue
            if merged:
                previous = merged[-1]
                gap = text[previous.end:start]
                if (
                    previous.label == span.label
                    and previous.end <= start
                    and gap.isspace()
                    and "\n" not in gap
                    and "\r" not in gap
                ):
                    merged[-1] = DetectedSpan(previous.start, end, previous.label)
                    continue
            merged.append(DetectedSpan(start, end, span.label))
        return tuple(merged)


class CombinedDetector:
    def __init__(self, detectors: tuple[Detector, ...]) -> None:
        self.detectors = detectors
        self.name = "+".join(detector.name for detector in detectors)
        self.version = "+".join(detector.version for detector in detectors)

    def initialize(self) -> None:
        for detector in self.detectors:
            detector.initialize()

    def detect(self, text: str) -> tuple[DetectedSpan, ...]:
        spans = {
            (span.start, span.end): span
            for detector in self.detectors
            for span in detector.detect(text)
        }
        return tuple(sorted(spans.values(), key=lambda span: (span.start, span.end)))


def make_detector(mode: str, model_dir: Path, lock: dict[str, object]) -> Detector:
    if mode == "rules":
        detector: Detector = RulesDetector()
    else:
        model_name = mode.removeprefix("rules+")
        model = lock["models"][model_name]
        if model_name == "presidio":
            model_detector: Detector = PresidioPatternDetector(
                str(model["package_version"])
            )
        else:
            revision = str(model["revision"])
            path = model_dir / model_name
            if not path.is_dir():
                raise FileNotFoundError(
                    f"missing local model {model_name}; run scripts/download_models.py {model_name}"
                )
        if model_name == "gliner":
            model_detector: Detector = GlinerDetector(path, revision)
        elif model_name == "privacy-filter":
            model_detector = PrivacyFilterDetector(path, revision)
        detector = (
            model_detector
            if mode == model_name
            else CombinedDetector((RulesDetector(), model_detector))
        )
    detector.initialize()
    return detector


def evaluate(
    messages: tuple[MessageFixture, ...],
    supported_languages: tuple[str, ...],
    detector: Detector,
) -> tuple[tuple[MessageScore, ...], float, int, int, int, int, int]:
    scores: list[MessageScore] = []
    warm_times: list[float] = []
    total_gold = covered_gold = exact_count = predicted_count = extra_count = 0
    for message in messages:
        should_withhold = message.language not in supported_languages
        if should_withhold:
            scores.append(MessageScore(message.id, True, 0, 0, 0, 0, 0))
            continue
        gold = gold_spans(message)
        start = time.perf_counter()
        predicted = detector.detect(message.source_text)
        warm_times.append(time.perf_counter() - start)
        for span in predicted:
            if span.start < 0 or span.end <= span.start or span.end > len(message.source_text):
                raise ValueError(f"{detector.name} returned an invalid span")
        covered = sum(
            any(pred.start <= target.start and pred.end >= target.end for pred in predicted)
            for target in gold
        )
        exact = sum(
            any(pred.start == target.start and pred.end == target.end for pred in predicted)
            for target in gold
        )
        extra = sum(
            not any(pred.start == target.start and pred.end == target.end for target in gold)
            for pred in predicted
        )
        total_gold += len(gold)
        covered_gold += covered
        exact_count += exact
        predicted_count += len(predicted)
        extra_count += extra
        scores.append(
            MessageScore(
                id=message.id,
                withheld=False,
                gold_count=len(gold),
                covered_gold_count=covered,
                exact_match_count=exact,
                predicted_span_count=len(predicted),
                extra_span_count=extra,
            )
        )
    warm_seconds = sum(warm_times)
    return (
        tuple(scores),
        warm_seconds * 1000,
        total_gold,
        covered_gold,
        exact_count,
        predicted_count,
        extra_count,
    )


class SystemMemorySampler:
    def __init__(self) -> None:
        try:
            import psutil
        except ImportError:
            self._psutil = None
        else:
            self._psutil = psutil
        self.before = self._used()
        self.peak = self.before
        self.total = self._psutil.virtual_memory().total if self._psutil else None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _used(self) -> int | None:
        return self._psutil.virtual_memory().used if self._psutil else None

    def _sample(self) -> None:
        while not self._stop.wait(0.1):
            current = self._used()
            if current is not None:
                self.peak = max(self.peak or 0, current)

    def __enter__(self) -> SystemMemorySampler:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()


def process_peak_rss_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument(
        "--detector",
        choices=(
            "rules",
            "gliner",
            "privacy-filter",
            "presidio",
            "rules+gliner",
            "rules+privacy-filter",
            "rules+presidio",
        ),
        default="rules",
    )
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8"))
        languages, messages = load_fixtures(args.fixtures)
        with SystemMemorySampler() as memory:
            init_start = time.perf_counter()
            detector = make_detector(args.detector, args.model_dir.expanduser(), lock)
            init_ms = (time.perf_counter() - init_start) * 1000
            result = evaluate(messages, languages, detector)
        scores, warm_ms, gold_count, covered, exact, predicted, extra = result
    except (OSError, ValueError, KeyError, RuntimeError, ImportError, TypeError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 2

    scored_count = sum(not score.withheld for score in scores)
    report = EvaluationReport(
        schema_version=1,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        detector=detector.name,
        detector_version=detector.version,
        fixture_file=str(args.fixtures),
        fixture_count=len(messages),
        scored_message_count=scored_count,
        withheld_message_count=len(messages) - scored_count,
        gold_span_count=gold_count,
        covered_gold_span_count=covered,
        full_coverage_recall=covered / gold_count if gold_count else None,
        exact_span_precision=exact / predicted if predicted else None,
        exact_span_count=exact,
        predicted_span_count=predicted,
        extra_span_count=extra,
        model_init_ms=init_ms,
        warm_inference_ms=warm_ms,
        process_peak_rss_bytes=process_peak_rss_bytes(),
        system_memory_before_bytes=memory.before,
        system_peak_used_bytes=memory.peak,
        host_total_memory_bytes=memory.total,
        target_total_memory_bytes=memory.total,
        messages=scores,
    )
    output = json.dumps(asdict(report), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
