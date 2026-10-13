#!/usr/bin/env python3
"""Fail-closed inbound reply custody router for commercial outreach.

This module does not read mailbox bodies, send replies, authorize money, or
recognize revenue. It consumes an operator/provider-classified evidence
snapshot and emits a deterministic custody/action receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

CONTEXT_SCHEMA = "inbound-reply-context/v1"
EVIDENCE_SCHEMA = "inbound-reply-evidence/v1"
RECEIPT_SCHEMA = "inbound-reply-router-receipt/v1"

ACTIONS = {
    "HOLD",
    "OWNER_REPLY_REQUIRED",
    "OWNER_REVIEW_REQUIRED",
    "CLOSE_DO_NOT_CONTACT",
    "ROUTE_REPAIR_REQUIRED",
    "WAIT_NO_ACTION",
}

HUMAN_CLASSIFICATIONS = {
    "HUMAN_INTERESTED",
    "HUMAN_QUESTION",
    "HUMAN_ROUTE_CHANGE",
    "HUMAN_DECLINED",
    "HUMAN_UNSUBSCRIBE",
    "HUMAN_ROUTING_ACK",
    "HUMAN_OTHER",
}
PROVIDER_CLASSIFICATIONS = {
    "AUTO_ACK",
    "OUT_OF_OFFICE",
    "DELIVERY_FAILURE",
    "DELIVERY_DELAY",
    "UNKNOWN",
}
CLASSIFICATIONS = HUMAN_CLASSIFICATIONS | PROVIDER_CLASSIFICATIONS

DEFAULT_MAX_EVIDENCE_AGE_SECONDS = 900
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 300
MAX_EVENTS = 10_000
MAX_OWNER_BINDINGS = 1_000

_EMAIL_RE = re.compile(r"^[^\s@<>(),;:]+@[^\s@<>(),;:]+$")


class RouterError(ValueError):
    """Raised when structurally invalid input cannot be routed safely."""


class DuplicateKeyError(RouterError):
    """Raised when JSON contains a duplicate object key."""


@dataclass(frozen=True)
class Policy:
    max_evidence_age_seconds: int = DEFAULT_MAX_EVIDENCE_AGE_SECONDS
    max_future_skew_seconds: int = DEFAULT_MAX_FUTURE_SKEW_SECONDS


@dataclass(frozen=True)
class Context:
    offer_id: str
    counterparty: str
    thread_id: str
    owner_id: str
    prior_outbound_message_id: str
    prior_outbound_observed_at: datetime


@dataclass(frozen=True)
class Event:
    message_id: str
    thread_id: str
    counterparty: str
    observed_at: datetime
    offer_id: str
    classification: str
    classified_by: str
    classifier_id: str | None
    new_route: str | None

    def semantic_key(self) -> tuple[Any, ...]:
        return (
            self.message_id,
            self.thread_id,
            self.counterparty,
            _format_time(self.observed_at),
            self.offer_id,
            self.classification,
            self.classified_by,
            self.classifier_id,
            self.new_route,
        )


@dataclass(frozen=True)
class OwnerBinding:
    owner_id: str
    offer_id: str
    thread_id: str
    status: str
    observed_at: datetime


@dataclass(frozen=True)
class Evidence:
    captured_at: datetime
    provider_query_complete: bool
    ownership_query_complete: bool
    events: tuple[Event, ...]
    owner_bindings: tuple[OwnerBinding, ...]


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def load_json(path: str | os.PathLike[str]) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=_strict_object)


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise RouterError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str, *, maximum: int) -> list[Any]:
    if type(value) is not list:
        raise RouterError(f"{label} must be a list")
    if len(value) > maximum:
        raise RouterError(f"{label} exceeds {maximum} rows")
    return value


def _require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise RouterError(f"{label} must be a boolean")
    return value


def _require_text(value: Any, label: str, *, max_len: int = 512) -> str:
    if type(value) is not str:
        raise RouterError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise RouterError(f"{label} must not be empty")
    if len(text) > max_len:
        raise RouterError(f"{label} exceeds {max_len} characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise RouterError(f"{label} contains control characters")
    return text


def _optional_text(value: Any, label: str, *, max_len: int = 512) -> str | None:
    if value is None:
        return None
    return _require_text(value, label, max_len=max_len)


def normalize_email(value: Any, label: str = "email") -> str:
    text = _require_text(value, label, max_len=320)
    if text.count("@") != 1 or not _EMAIL_RE.fullmatch(text):
        raise RouterError(f"{label} must be a single email address")
    local, domain = text.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        raise RouterError(f"{label} must have a routable domain")
    return f"{local}@{domain.lower()}"


def _parse_time(value: Any, label: str) -> datetime:
    text = _require_text(value, label, max_len=64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RouterError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RouterError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _parse_context(raw: Any) -> Context:
    obj = _require_dict(raw, "context")
    if obj.get("schema") != CONTEXT_SCHEMA:
        raise RouterError(f"context.schema must be {CONTEXT_SCHEMA}")
    allowed = {
        "schema",
        "offer_id",
        "counterparty",
        "thread_id",
        "owner_id",
        "prior_outbound_message_id",
        "prior_outbound_observed_at",
    }
    extra = sorted(set(obj) - allowed)
    if extra:
        raise RouterError(f"context contains unknown fields: {', '.join(extra)}")
    return Context(
        offer_id=_require_text(obj.get("offer_id"), "context.offer_id"),
        counterparty=normalize_email(obj.get("counterparty"), "context.counterparty"),
        thread_id=_require_text(obj.get("thread_id"), "context.thread_id"),
        owner_id=_require_text(obj.get("owner_id"), "context.owner_id"),
        prior_outbound_message_id=_require_text(
            obj.get("prior_outbound_message_id"),
            "context.prior_outbound_message_id",
        ),
        prior_outbound_observed_at=_parse_time(
            obj.get("prior_outbound_observed_at"),
            "context.prior_outbound_observed_at",
        ),
    )


def _parse_event(raw: Any, index: int) -> Event:
    label = f"evidence.events[{index}]"
    obj = _require_dict(raw, label)
    allowed = {
        "message_id",
        "thread_id",
        "counterparty",
        "observed_at",
        "offer_id",
        "classification",
        "classified_by",
        "classifier_id",
        "new_route",
    }
    extra = sorted(set(obj) - allowed)
    if extra:
        raise RouterError(f"{label} contains unknown fields: {', '.join(extra)}")

    classification = _require_text(
        obj.get("classification"), f"{label}.classification", max_len=64
    )
    if classification not in CLASSIFICATIONS:
        raise RouterError(f"{label}.classification is unsupported")

    classified_by = _require_text(
        obj.get("classified_by"), f"{label}.classified_by", max_len=32
    )
    classifier_id = _optional_text(
        obj.get("classifier_id"), f"{label}.classifier_id"
    )
    new_route_raw = obj.get("new_route")
    new_route = None if new_route_raw is None else normalize_email(
        new_route_raw, f"{label}.new_route"
    )

    if classification in HUMAN_CLASSIFICATIONS:
        if classified_by != "human_operator":
            raise RouterError(
                f"{label} human classification requires classified_by=human_operator"
            )
        if classifier_id is None:
            raise RouterError(f"{label} human classification requires classifier_id")
    else:
        if classified_by != "provider":
            raise RouterError(
                f"{label} provider classification requires classified_by=provider"
            )
        if classifier_id is not None:
            raise RouterError(
                f"{label} provider classification must not set classifier_id"
            )

    if classification == "HUMAN_ROUTE_CHANGE":
        if new_route is None:
            raise RouterError(f"{label} HUMAN_ROUTE_CHANGE requires new_route")
    elif new_route is not None:
        raise RouterError(
            f"{label}.new_route is allowed only for HUMAN_ROUTE_CHANGE"
        )

    return Event(
        message_id=_require_text(obj.get("message_id"), f"{label}.message_id"),
        thread_id=_require_text(obj.get("thread_id"), f"{label}.thread_id"),
        counterparty=normalize_email(
            obj.get("counterparty"), f"{label}.counterparty"
        ),
        observed_at=_parse_time(obj.get("observed_at"), f"{label}.observed_at"),
        offer_id=_require_text(obj.get("offer_id"), f"{label}.offer_id"),
        classification=classification,
        classified_by=classified_by,
        classifier_id=classifier_id,
        new_route=new_route,
    )


def _parse_owner_binding(raw: Any, index: int) -> OwnerBinding:
    label = f"evidence.owner_bindings[{index}]"
    obj = _require_dict(raw, label)
    allowed = {"owner_id", "offer_id", "thread_id", "status", "observed_at"}
    extra = sorted(set(obj) - allowed)
    if extra:
        raise RouterError(f"{label} contains unknown fields: {', '.join(extra)}")
    status = _require_text(obj.get("status"), f"{label}.status", max_len=16)
    if status not in {"ACTIVE", "RELEASED"}:
        raise RouterError(f"{label}.status must be ACTIVE or RELEASED")
    return OwnerBinding(
        owner_id=_require_text(obj.get("owner_id"), f"{label}.owner_id"),
        offer_id=_require_text(obj.get("offer_id"), f"{label}.offer_id"),
        thread_id=_require_text(obj.get("thread_id"), f"{label}.thread_id"),
        status=status,
        observed_at=_parse_time(obj.get("observed_at"), f"{label}.observed_at"),
    )


def _parse_evidence(raw: Any) -> Evidence:
    obj = _require_dict(raw, "evidence")
    if obj.get("schema") != EVIDENCE_SCHEMA:
        raise RouterError(f"evidence.schema must be {EVIDENCE_SCHEMA}")
    allowed = {
        "schema",
        "captured_at",
        "provider_query_complete",
        "ownership_query_complete",
        "events",
        "owner_bindings",
    }
    extra = sorted(set(obj) - allowed)
    if extra:
        raise RouterError(f"evidence contains unknown fields: {', '.join(extra)}")
    event_rows = _require_list(
        obj.get("events"), "evidence.events", maximum=MAX_EVENTS
    )
    owner_rows = _require_list(
        obj.get("owner_bindings"),
        "evidence.owner_bindings",
        maximum=MAX_OWNER_BINDINGS,
    )
    return Evidence(
        captured_at=_parse_time(obj.get("captured_at"), "evidence.captured_at"),
        provider_query_complete=_require_bool(
            obj.get("provider_query_complete"),
            "evidence.provider_query_complete",
        ),
        ownership_query_complete=_require_bool(
            obj.get("ownership_query_complete"),
            "evidence.ownership_query_complete",
        ),
        events=tuple(_parse_event(row, index) for index, row in enumerate(event_rows)),
        owner_bindings=tuple(
            _parse_owner_binding(row, index)
            for index, row in enumerate(owner_rows)
        ),
    )


def _base_receipt(
    *,
    context: Context,
    evidence: Evidence,
    evaluated_at: datetime,
    action: str,
    basis: Iterable[str],
    relevant_events: Iterable[Event] = (),
    deduped_event_count: int = 0,
    ignored_pre_outbound_count: int = 0,
    candidate_new_route: str | None = None,
    do_not_resend: bool = False,
    hard_do_not_contact: bool = False,
) -> dict[str, Any]:
    events = tuple(relevant_events)
    event_ids = sorted({event.message_id for event in events})
    body: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "evaluated_at": _format_time(evaluated_at),
        "offer_id": context.offer_id,
        "counterparty": context.counterparty,
        "thread_id": context.thread_id,
        "owner_id": context.owner_id,
        "prior_outbound_message_id": context.prior_outbound_message_id,
        "prior_outbound_observed_at": _format_time(
            context.prior_outbound_observed_at
        ),
        "evidence_captured_at": _format_time(evidence.captured_at),
        "action": action,
        "basis": list(basis),
        "candidate_new_route": candidate_new_route,
        "do_not_resend": do_not_resend,
        "hard_do_not_contact": hard_do_not_contact,
        "relevant_message_ids": event_ids,
        "relevant_message_ids_sha256": hashlib.sha256(
            "\n".join(event_ids).encode("utf-8")
        ).hexdigest(),
        "evidence_counts": {
            "raw_events": len(evidence.events),
            "deduped_events": deduped_event_count,
            "ignored_pre_outbound_events": ignored_pre_outbound_count,
            "owner_bindings": len(evidence.owner_bindings),
        },
        "authority": {
            "owner_queue_custody_only": True,
            "side_effects_authorized": False,
            "reply_send_authorized": False,
            "resend_authorized": False,
            "payment_authorized": False,
            "contract_authorized": False,
            "revenue_recognized": False,
            "buyer_acceptance_inferred": False,
        },
    }
    body["receipt_sha256"] = _sha256_json(body)
    return body


def _hold(
    *,
    context: Context,
    evidence: Evidence,
    evaluated_at: datetime,
    reasons: Iterable[str],
    relevant_events: Iterable[Event] = (),
    deduped_event_count: int = 0,
    ignored_pre_outbound_count: int = 0,
) -> dict[str, Any]:
    return _base_receipt(
        context=context,
        evidence=evidence,
        evaluated_at=evaluated_at,
        action="HOLD",
        basis=reasons,
        relevant_events=relevant_events,
        deduped_event_count=deduped_event_count,
        ignored_pre_outbound_count=ignored_pre_outbound_count,
    )


def route_reply(
    context_raw: Any,
    evidence_raw: Any,
    *,
    evaluated_at: str | datetime,
    policy: Policy | None = None,
) -> dict[str, Any]:
    """Return a deterministic, side-effect-free reply custody receipt."""
    context = _parse_context(context_raw)
    evidence = _parse_evidence(evidence_raw)
    policy = policy or Policy()
    if isinstance(evaluated_at, str):
        now = _parse_time(evaluated_at, "evaluated_at")
    elif isinstance(evaluated_at, datetime):
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise RouterError("evaluated_at must include a timezone")
        now = evaluated_at.astimezone(timezone.utc)
    else:
        raise RouterError("evaluated_at must be a timestamp string or datetime")

    if (
        type(policy.max_evidence_age_seconds) is not int
        or policy.max_evidence_age_seconds < 0
        or policy.max_evidence_age_seconds > 86_400
    ):
        raise RouterError("policy.max_evidence_age_seconds is invalid")
    if (
        type(policy.max_future_skew_seconds) is not int
        or policy.max_future_skew_seconds < 0
        or policy.max_future_skew_seconds > 3_600
    ):
        raise RouterError("policy.max_future_skew_seconds is invalid")

    reasons: list[str] = []
    if not evidence.provider_query_complete:
        reasons.append("provider_query_incomplete")
    if not evidence.ownership_query_complete:
        reasons.append("ownership_query_incomplete")

    age = now - evidence.captured_at
    if age > timedelta(seconds=policy.max_evidence_age_seconds):
        reasons.append("evidence_snapshot_stale")
    if evidence.captured_at - now > timedelta(
        seconds=policy.max_future_skew_seconds
    ):
        reasons.append("evidence_snapshot_from_future")

    # Ownership snapshots are current-state rows: one row per owner. Duplicate
    # owners make the source ambiguous even when both rows happen to agree.
    owner_ids = [binding.owner_id for binding in evidence.owner_bindings]
    if len(owner_ids) != len(set(owner_ids)):
        reasons.append("duplicate_owner_binding")

    for binding in evidence.owner_bindings:
        if (
            binding.offer_id != context.offer_id
            or binding.thread_id != context.thread_id
        ):
            reasons.append("ownership_scope_mismatch")
            break
        if binding.observed_at - evidence.captured_at > timedelta(
            seconds=policy.max_future_skew_seconds
        ):
            reasons.append("owner_binding_after_snapshot")
            break

    active = [
        binding
        for binding in evidence.owner_bindings
        if binding.status == "ACTIVE"
        and binding.offer_id == context.offer_id
        and binding.thread_id == context.thread_id
    ]
    if len(active) == 0:
        reasons.append("no_active_owner")
    elif len(active) > 1:
        reasons.append("multiple_active_owners")
    elif active[0].owner_id != context.owner_id:
        reasons.append("active_owner_mismatch")

    # Dedupe exact provider replays by message id. A repeated id with any
    # semantic difference is evidence corruption/conflict and must fail closed.
    by_message: dict[str, Event] = {}
    conflict_ids: list[str] = []
    for event in evidence.events:
        prior = by_message.get(event.message_id)
        if prior is None:
            by_message[event.message_id] = event
        elif prior.semantic_key() != event.semantic_key():
            conflict_ids.append(event.message_id)
    if conflict_ids:
        reasons.append("conflicting_duplicate_message_id")

    deduped = tuple(
        sorted(
            by_message.values(),
            key=lambda item: (item.observed_at, item.message_id),
        )
    )

    for event in deduped:
        if (
            event.offer_id != context.offer_id
            or event.thread_id != context.thread_id
            or event.counterparty != context.counterparty
        ):
            reasons.append("provider_evidence_scope_mismatch")
            break
        if event.observed_at - evidence.captured_at > timedelta(
            seconds=policy.max_future_skew_seconds
        ):
            reasons.append("event_after_snapshot")
            break
        if event.observed_at - now > timedelta(
            seconds=policy.max_future_skew_seconds
        ):
            reasons.append("event_from_future")
            break
        if (
            event.classification == "HUMAN_ROUTE_CHANGE"
            and event.new_route == context.counterparty
        ):
            reasons.append("route_change_reuses_current_route")
            break

    pre_outbound = tuple(
        event
        for event in deduped
        if event.observed_at <= context.prior_outbound_observed_at
    )
    post_outbound = tuple(
        event
        for event in deduped
        if event.observed_at > context.prior_outbound_observed_at
    )

    # An unsubscribe observed before the stated outbound is a historical DNR
    # conflict; the router will not normalize around it.
    if any(
        event.classification == "HUMAN_UNSUBSCRIBE" for event in pre_outbound
    ):
        reasons.append("outbound_after_prior_unsubscribe")

    if reasons:
        return _hold(
            context=context,
            evidence=evidence,
            evaluated_at=now,
            reasons=sorted(set(reasons)),
            relevant_events=post_outbound,
            deduped_event_count=len(deduped),
            ignored_pre_outbound_count=len(pre_outbound),
        )

    if not post_outbound:
        return _base_receipt(
            context=context,
            evidence=evidence,
            evaluated_at=now,
            action="WAIT_NO_ACTION",
            basis=["no_new_inbound_evidence"],
            deduped_event_count=len(deduped),
            ignored_pre_outbound_count=len(pre_outbound),
        )

    unknown = [
        event for event in post_outbound if event.classification == "UNKNOWN"
    ]
    if unknown:
        return _hold(
            context=context,
            evidence=evidence,
            evaluated_at=now,
            reasons=["unclassified_inbound_evidence"],
            relevant_events=post_outbound,
            deduped_event_count=len(deduped),
            ignored_pre_outbound_count=len(pre_outbound),
        )

    humans = [
        event
        for event in post_outbound
        if event.classification in HUMAN_CLASSIFICATIONS
    ]
    failures = [
        event
        for event in post_outbound
        if event.classification == "DELIVERY_FAILURE"
    ]

    # A provider says the route failed while a human is also said to have
    # replied in the same bound thread. Do not guess which source is wrong.
    if humans and failures:
        return _hold(
            context=context,
            evidence=evidence,
            evaluated_at=now,
            reasons=["human_reply_conflicts_with_delivery_failure"],
            relevant_events=post_outbound,
            deduped_event_count=len(deduped),
            ignored_pre_outbound_count=len(pre_outbound),
        )

    if humans:
        latest_human = max(
            humans, key=lambda item: (item.observed_at, item.message_id)
        )
        unsubscribes = [
            event
            for event in humans
            if event.classification == "HUMAN_UNSUBSCRIBE"
        ]
        if unsubscribes and latest_human.classification != "HUMAN_UNSUBSCRIBE":
            return _hold(
                context=context,
                evidence=evidence,
                evaluated_at=now,
                reasons=["post_unsubscribe_human_requires_manual_override"],
                relevant_events=post_outbound,
                deduped_event_count=len(deduped),
                ignored_pre_outbound_count=len(pre_outbound),
            )

        classification = latest_human.classification
        if classification == "HUMAN_UNSUBSCRIBE":
            return _base_receipt(
                context=context,
                evidence=evidence,
                evaluated_at=now,
                action="CLOSE_DO_NOT_CONTACT",
                basis=["latest_human_reply_is_unsubscribe"],
                relevant_events=post_outbound,
                deduped_event_count=len(deduped),
                ignored_pre_outbound_count=len(pre_outbound),
                do_not_resend=True,
                hard_do_not_contact=True,
            )
        if classification == "HUMAN_DECLINED":
            return _base_receipt(
                context=context,
                evidence=evidence,
                evaluated_at=now,
                action="CLOSE_DO_NOT_CONTACT",
                basis=["latest_human_reply_declines_offer"],
                relevant_events=post_outbound,
                deduped_event_count=len(deduped),
                ignored_pre_outbound_count=len(pre_outbound),
                do_not_resend=True,
            )
        if classification in {
            "HUMAN_INTERESTED",
            "HUMAN_QUESTION",
            "HUMAN_ROUTE_CHANGE",
        }:
            basis_map = {
                "HUMAN_INTERESTED": "human_interest_requires_owner_reply",
                "HUMAN_QUESTION": "human_question_requires_owner_reply",
                "HUMAN_ROUTE_CHANGE": "human_route_change_requires_owner_verification",
            }
            return _base_receipt(
                context=context,
                evidence=evidence,
                evaluated_at=now,
                action="OWNER_REPLY_REQUIRED",
                basis=[basis_map[classification]],
                relevant_events=post_outbound,
                deduped_event_count=len(deduped),
                ignored_pre_outbound_count=len(pre_outbound),
                candidate_new_route=latest_human.new_route,
            )
        if classification == "HUMAN_ROUTING_ACK":
            return _base_receipt(
                context=context,
                evidence=evidence,
                evaluated_at=now,
                action="WAIT_NO_ACTION",
                basis=["human_routing_ack_is_not_buyer_interest"],
                relevant_events=post_outbound,
                deduped_event_count=len(deduped),
                ignored_pre_outbound_count=len(pre_outbound),
            )
        return _base_receipt(
            context=context,
            evidence=evidence,
            evaluated_at=now,
            action="OWNER_REVIEW_REQUIRED",
            basis=["human_reply_requires_manual_disposition"],
            relevant_events=post_outbound,
            deduped_event_count=len(deduped),
            ignored_pre_outbound_count=len(pre_outbound),
        )

    if failures:
        return _base_receipt(
            context=context,
            evidence=evidence,
            evaluated_at=now,
            action="ROUTE_REPAIR_REQUIRED",
            basis=["provider_reports_delivery_failure"],
            relevant_events=post_outbound,
            deduped_event_count=len(deduped),
            ignored_pre_outbound_count=len(pre_outbound),
            do_not_resend=True,
        )

    if any(
        event.classification == "OUT_OF_OFFICE" for event in post_outbound
    ):
        return _base_receipt(
            context=context,
            evidence=evidence,
            evaluated_at=now,
            action="WAIT_NO_ACTION",
            basis=["out_of_office_is_not_buyer_interest"],
            relevant_events=post_outbound,
            deduped_event_count=len(deduped),
            ignored_pre_outbound_count=len(pre_outbound),
        )

    if any(event.classification == "AUTO_ACK" for event in post_outbound):
        return _base_receipt(
            context=context,
            evidence=evidence,
            evaluated_at=now,
            action="WAIT_NO_ACTION",
            basis=["automated_acknowledgement_is_not_buyer_interest"],
            relevant_events=post_outbound,
            deduped_event_count=len(deduped),
            ignored_pre_outbound_count=len(pre_outbound),
        )

    return _base_receipt(
        context=context,
        evidence=evidence,
        evaluated_at=now,
        action="WAIT_NO_ACTION",
        basis=["provider_delivery_delay_or_nonactionable_evidence"],
        relevant_events=post_outbound,
        deduped_event_count=len(deduped),
        ignored_pre_outbound_count=len(pre_outbound),
    )


def write_receipt_atomic(
    receipt: dict[str, Any], path: str | os.PathLike[str]
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Route classified inbound commercial reply evidence into a "
            "fail-closed owner-custody receipt."
        )
    )
    parser.add_argument("--context", required=True, help="reply context JSON")
    parser.add_argument("--evidence", required=True, help="evidence snapshot JSON")
    parser.add_argument(
        "--evaluated-at",
        required=True,
        help="explicit timezone-aware ISO-8601 evaluation timestamp",
    )
    parser.add_argument("--output", help="optional atomic receipt output path")
    parser.add_argument(
        "--max-evidence-age-seconds",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-future-skew-seconds",
        type=int,
        default=DEFAULT_MAX_FUTURE_SKEW_SECONDS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        context = load_json(args.context)
        evidence = load_json(args.evidence)
        receipt = route_reply(
            context,
            evidence,
            evaluated_at=args.evaluated_at,
            policy=Policy(
                max_evidence_age_seconds=args.max_evidence_age_seconds,
                max_future_skew_seconds=args.max_future_skew_seconds,
            ),
        )
        if args.output:
            write_receipt_atomic(receipt, args.output)
        else:
            json.dump(
                receipt,
                sys.stdout,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
            sys.stdout.write("\n")
        return 0
    except (OSError, RouterError, json.JSONDecodeError) as exc:
        print(f"inbound-reply-router: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
