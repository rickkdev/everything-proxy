from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


RULE_VERSION = "2026-10-29.1"


class Relevance(StrEnum):
    INCLUDE = "include"
    DEPRIORITIZE = "deprioritize"
    SKIP = "skip"
    INSPECT = "inspect"


class Reason(StrEnum):
    USER_EXCLUDED = "user_excluded"
    GMAIL_SPAM = "gmail_spam"
    GMAIL_TRASH = "gmail_trash"
    GMAIL_DRAFT = "gmail_draft"
    USER_INCLUDED = "user_included"
    SELECTED_SENDER = "selected_sender"
    TRACKED_THREAD = "tracked_thread"
    STARRED = "starred"
    SECURITY_ALERT = "security_alert"
    FAILURE_OR_CANCELLATION = "failure_or_cancellation"
    PROMOTION = "promotion"
    NEWSLETTER = "newsletter"
    ROUTINE_RECEIPT = "routine_receipt"
    ROUTINE_SHIPMENT = "routine_shipment"
    DIRECT_REQUEST = "direct_request"
    CHANGED_DATE = "changed_date"
    EXPLICIT_DECISION = "explicit_decision"
    UNCERTAIN = "uncertain"


class PrivacyHold(StrEnum):
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    SENSITIVE_TOPIC = "sensitive_topic"


@dataclass(frozen=True)
class MessageMetadata:
    sender: str | None
    list_id: str | None
    subject: str | None
    labels: frozenset[str] = frozenset()
    tracked_thread: bool = False
    language: str | None = None


@dataclass(frozen=True)
class RuleSet:
    excluded_senders: frozenset[str] = frozenset()
    excluded_lists: frozenset[str] = frozenset()
    included_senders: frozenset[str] = frozenset()
    included_lists: frozenset[str] = frozenset()
    selected_senders: frozenset[str] = frozenset()
    newsletter_lists: frozenset[str] = frozenset()
    routine_receipt_senders: frozenset[str] = frozenset()
    routine_shipment_senders: frozenset[str] = frozenset()
    supported_languages: frozenset[str] = frozenset({"en"})


@dataclass(frozen=True)
class FilterDecision:
    relevance: Relevance
    reason: Reason
    rule_version: str = RULE_VERSION
    fetch_body: bool = True
    privacy_hold: PrivacyHold | None = None


_RECEIPT_SUBJECT = re.compile(r"\b(?:receipt|invoice|payment received)\b", re.IGNORECASE)
_SHIPMENT_SUBJECT = re.compile(
    r"\b(?:package is on the way|shipment notice|delivery update)\b", re.IGNORECASE
)
_SECURITY_SUBJECT = re.compile(
    r"\b(?:security alert|sign-in (?:blocked|alert)|unrecognized sign-in)\b",
    re.IGNORECASE,
)
_FAILURE_SUBJECT = re.compile(
    r"\b(?:failure|failed|cancellation|cancelled|canceled)\b", re.IGNORECASE
)
_DIRECT_REQUEST = re.compile(
    r"\b(?:please|could you|can you|would you)\b.{0,100}"
    r"\b(?:review|send|share|update|prepare|check|reply|confirm)\b",
    re.IGNORECASE | re.DOTALL,
)
_CHANGED_DATE = re.compile(
    r"\b(?:date|deadline|meeting|review).{0,60}"
    r"\b(?:moved|changed|postponed|rescheduled)\b|"
    r"\b(?:moved|changed|postponed|rescheduled).{0,60}"
    r"\b(?:date|deadline|meeting|review)\b",
    re.IGNORECASE | re.DOTALL,
)
_DECISION = re.compile(r"\bdecision\s*:", re.IGNORECASE)
_SENSITIVE = re.compile(
    r"\b(?:medical leave|multiple sclerosis|diagnosis|account number|"
    r"account \d{6,}|bank account|private transfer|health update)\b",
    re.IGNORECASE,
)


def _key(value: str | None) -> str | None:
    return value.strip().casefold() if value and value.strip() else None


def _has_any(value: str | None, configured: frozenset[str]) -> bool:
    normalized = _key(value)
    return normalized is not None and normalized in {_key(item) for item in configured}


def _decision(
    relevance: Relevance,
    reason: Reason,
    fetch_body: bool,
    hold: PrivacyHold | None = None,
) -> FilterDecision:
    return FilterDecision(relevance, reason, fetch_body=fetch_body, privacy_hold=hold)


def evaluate_metadata(metadata: MessageMetadata, rules: RuleSet) -> FilterDecision:
    """Choose a metadata-only action before deciding whether to fetch the body."""
    labels = {_key(label) for label in metadata.labels}
    sender = metadata.sender
    list_id = metadata.list_id

    if _has_any(sender, rules.excluded_senders) or _has_any(list_id, rules.excluded_lists):
        return _decision(Relevance.SKIP, Reason.USER_EXCLUDED, False)
    if "spam" in labels:
        return _decision(Relevance.SKIP, Reason.GMAIL_SPAM, False)
    if "trash" in labels:
        return _decision(Relevance.SKIP, Reason.GMAIL_TRASH, False)
    if "draft" in labels:
        return _decision(Relevance.SKIP, Reason.GMAIL_DRAFT, False)

    if _has_any(sender, rules.included_senders) or _has_any(list_id, rules.included_lists):
        return _decision(Relevance.INCLUDE, Reason.USER_INCLUDED, True)
    if _has_any(sender, rules.selected_senders):
        return _decision(Relevance.INCLUDE, Reason.SELECTED_SENDER, True)
    if metadata.tracked_thread:
        return _decision(Relevance.INCLUDE, Reason.TRACKED_THREAD, True)
    if "starred" in labels:
        return _decision(Relevance.INCLUDE, Reason.STARRED, True)

    subject = metadata.subject or ""
    if _SECURITY_SUBJECT.search(subject):
        return _decision(Relevance.INCLUDE, Reason.SECURITY_ALERT, True)
    if _FAILURE_SUBJECT.search(subject):
        return _decision(Relevance.INCLUDE, Reason.FAILURE_OR_CANCELLATION, True)
    if _has_any(sender, rules.routine_receipt_senders) and _RECEIPT_SUBJECT.search(subject):
        return _decision(Relevance.SKIP, Reason.ROUTINE_RECEIPT, False)
    if _has_any(sender, rules.routine_shipment_senders) and _SHIPMENT_SUBJECT.search(subject):
        return _decision(Relevance.SKIP, Reason.ROUTINE_SHIPMENT, False)
    if "category_promotions" in labels:
        return _decision(Relevance.DEPRIORITIZE, Reason.PROMOTION, True)
    if _has_any(list_id, rules.newsletter_lists):
        return _decision(Relevance.DEPRIORITIZE, Reason.NEWSLETTER, True)
    return _decision(Relevance.INSPECT, Reason.UNCERTAIN, True)


def evaluate_message(
    metadata: MessageMetadata,
    body: str,
    rules: RuleSet,
    prior: FilterDecision | None = None,
) -> FilterDecision:
    """Refine relevance from local body text while keeping privacy holds separate."""
    prior = prior or evaluate_metadata(metadata, rules)
    if not prior.fetch_body:
        return prior

    hold = None
    language = _key(metadata.language)
    supported = {_key(item) for item in rules.supported_languages}
    if language is None or language not in supported:
        hold = PrivacyHold.UNSUPPORTED_LANGUAGE
    elif _SENSITIVE.search(f"{metadata.subject or ''}\n{body}"):
        hold = PrivacyHold.SENSITIVE_TOPIC

    if prior.relevance in {Relevance.INCLUDE, Relevance.SKIP}:
        return FilterDecision(
            prior.relevance, prior.reason, prior.rule_version, prior.fetch_body, hold
        )

    if _CHANGED_DATE.search(body):
        return _decision(Relevance.INCLUDE, Reason.CHANGED_DATE, True, hold)
    if _DECISION.search(body):
        return _decision(Relevance.INCLUDE, Reason.EXPLICIT_DECISION, True, hold)
    if _DIRECT_REQUEST.search(body):
        return _decision(Relevance.INCLUDE, Reason.DIRECT_REQUEST, True, hold)
    return FilterDecision(
        prior.relevance, prior.reason, prior.rule_version, prior.fetch_body, hold
    )
