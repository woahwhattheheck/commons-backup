#!/usr/bin/env python3
"""Canonical v2 Muse publication-election evidence compiler.

This module never sends outbound messages and never authenticates Slack itself.
A trusted adapter must supply complete raw Muse-DM readback. Even a valid
SELECTED receipt is coordination evidence only; it never authorizes a provider
mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping

REQUEST_SCHEMA = "outbound-muse-publication-election-request/v2"
SNAPSHOT_SCHEMA = "outbound-muse-publication-election-snapshot/v2"
RECEIPT_SCHEMA = "outbound-muse-publication-election-receipt/v2"
LEASE_RECEIPT_SCHEMA = "outbound-send-lease-receipt/v3"
LEASE_BINDING_SCHEMA = "outbound-lease-public-binding/v1"
PUBLICATION_KEY_SCHEMA = "outbound-publication-key/v2"
SELECTION_BINDING_SCHEMA = "outbound-muse-selection-binding/v2"
CANDIDATE_GENERATION_SCHEMA = "outbound-muse-candidate-generation/v2"

MUSE_USER_ID = "U0C0TKRTQHZ"
MUSE_DM_CONVERSATION_ID = "D0C1U7TUZEC"
RESPONSE_WINDOW_SECONDS = 600
COLLISION_LOOKBACK_SECONDS = 600
REQUEST_TRANSPORT_SKEW_SECONDS = 60
SNAPSHOT_FRESHNESS_SECONDS = 120
FUTURE_SKEW_SECONDS = 30
SELECTION_FRESHNESS_SECONDS = 600
MAX_MESSAGES = 256
ROUTE_KINDS = frozenset({"EMAIL", "CONTACT_FORM", "DIRECT_MESSAGE", "PORTAL_MESSAGE"})

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SLACK_ID_RE = re.compile(r"^[A-Z][A-Z0-9]{2,31}$")
_SLACK_TS_RE = re.compile(r"^[0-9]{10,}(?:\.[0-9]{1,6})?$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$")
_DECISION_RE = re.compile(
    r"^(SELECTED|NOT_SELECTED|CANCELLED) "
    r"([A-Za-z0-9][A-Za-z0-9._:-]{7,159}) "
    r"([0-9a-f]{64}) ([0-9a-f]{64})$"
)


class MuseElectionV2Error(ValueError):
    pass


def _strict_pairs(pairs):
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise MuseElectionV2Error(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def parse_json_bytes(raw: bytes, label: str) -> Any:
    if type(raw) is not bytes:
        raise MuseElectionV2Error(f"{label}: bytes required")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MuseElectionV2Error(f"{label}: UTF-8 JSON required") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                MuseElectionV2Error(f"{label}: non-finite number {token}")
            ),
        )
    except MuseElectionV2Error:
        raise
    except json.JSONDecodeError as exc:
        raise MuseElectionV2Error(f"{label}: invalid JSON: {exc.msg}") from exc


def _canon_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MuseElectionV2Error("value is not canonical-JSON serializable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon_bytes(value)).hexdigest()


def _obj(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise MuseElectionV2Error(f"{label}: object required")
    return value


def _arr(value: Any, label: str, *, max_items: int = MAX_MESSAGES) -> list[Any]:
    if type(value) is not list:
        raise MuseElectionV2Error(f"{label}: array required")
    if len(value) > max_items:
        raise MuseElectionV2Error(f"{label}: exceeds {max_items} items")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        missing = sorted(fields - set(value))
        extra = sorted(set(value) - fields)
        raise MuseElectionV2Error(f"{label}: exact fields required; missing={missing}; extra={extra}")


def _text(value: Any, label: str, *, max_len: int = 256, multiline: bool = False) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise MuseElectionV2Error(f"{label}: nonempty bounded string required")
    for ch in value:
        code = ord(ch)
        if code == 0x7F or (code < 0x20 and not (multiline and ch == "\n")):
            raise MuseElectionV2Error(f"{label}: forbidden control character")
    return value


def _hex64(value: Any, label: str) -> str:
    value = _text(value, label, max_len=64)
    if not _HEX64_RE.fullmatch(value):
        raise MuseElectionV2Error(f"{label}: expected lowercase SHA-256 hex")
    return value


def _git_sha(value: Any, label: str) -> str:
    value = _text(value, label, max_len=64)
    if not _GIT_SHA_RE.fullmatch(value):
        raise MuseElectionV2Error(f"{label}: expected lowercase 40/64 hex Git object id")
    return value


def _slack_id(value: Any, label: str) -> str:
    value = _text(value, label, max_len=32)
    if not _SLACK_ID_RE.fullmatch(value):
        raise MuseElectionV2Error(f"{label}: canonical Slack identifier required")
    return value


def _request_id(value: Any, label: str = "request_id") -> str:
    value = _text(value, label, max_len=160)
    if not _REQUEST_ID_RE.fullmatch(value):
        raise MuseElectionV2Error(f"{label}: expected 8-160 safe token characters")
    return value


def _utc(value: Any, label: str) -> datetime:
    text = _text(value, label, max_len=32)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise MuseElectionV2Error(f"{label}: expected UTC RFC3339 seconds") from exc
    return parsed


def _fmt(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slack_epoch(value: Any, label: str) -> Decimal:
    text = _text(value, label, max_len=32)
    if not _SLACK_TS_RE.fullmatch(text):
        raise MuseElectionV2Error(f"{label}: canonical Slack timestamp required")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise MuseElectionV2Error(f"{label}: invalid Slack timestamp") from exc
    if parsed <= 0:
        raise MuseElectionV2Error(f"{label}: positive Slack timestamp required")
    return parsed


def _slack_dt(value: Any, label: str) -> datetime:
    return datetime.fromtimestamp(float(_slack_epoch(value, label)), tz=timezone.utc)


def _normalize_lease_binding(raw: Mapping[str, Any]) -> dict[str, str]:
    binding = _obj(raw, "candidate.lease_binding")
    fields = {
        "schema_version", "receipt_schema", "claimant", "claim_id", "seam_sha256",
        "lease_ref", "lease_commit_sha", "claim_capability_sha256", "receipt_sha256",
    }
    _exact(binding, fields, "candidate.lease_binding")
    if binding["schema_version"] != LEASE_BINDING_SCHEMA:
        raise MuseElectionV2Error(
            f"candidate.lease_binding.schema_version: expected {LEASE_BINDING_SCHEMA}"
        )
    if binding["receipt_schema"] != LEASE_RECEIPT_SCHEMA:
        raise MuseElectionV2Error(
            f"candidate.lease_binding.receipt_schema: expected {LEASE_RECEIPT_SCHEMA}"
        )
    seam = _hex64(binding["seam_sha256"], "candidate.lease_binding.seam_sha256")
    lease_ref = _text(binding["lease_ref"], "candidate.lease_binding.lease_ref", max_len=512)
    if lease_ref != "refs/heads/outbound-lease-v3/" + seam:
        raise MuseElectionV2Error(
            "candidate.lease_binding.lease_ref: must exactly match the v3 seam"
        )
    return {
        "schema_version": LEASE_BINDING_SCHEMA,
        "receipt_schema": LEASE_RECEIPT_SCHEMA,
        "claimant": _text(binding["claimant"], "candidate.lease_binding.claimant", max_len=120),
        "claim_id": _text(binding["claim_id"], "candidate.lease_binding.claim_id", max_len=160),
        "seam_sha256": seam,
        "lease_ref": lease_ref,
        "lease_commit_sha": _git_sha(
            binding["lease_commit_sha"], "candidate.lease_binding.lease_commit_sha"
        ),
        "claim_capability_sha256": _hex64(
            binding["claim_capability_sha256"],
            "candidate.lease_binding.claim_capability_sha256",
        ),
        "receipt_sha256": _hex64(
            binding["receipt_sha256"], "candidate.lease_binding.receipt_sha256"
        ),
    }


def lease_binding_from_v3_receipt(receipt: Mapping[str, Any]) -> dict[str, str]:
    """Extract the public binding from an already verified v3 lease receipt.

    Callers MUST first run connector_capability_lease.verify_receipt(receipt).
    This helper intentionally does not duplicate that module's full verifier;
    provider-boundary possession remains an independent mandatory check.
    """
    value = _obj(receipt, "v3 lease receipt")
    required = {
        "schema", "claimant", "claim_id", "seam_sha256", "lease_ref",
        "lease_commit_sha", "claim_capability_sha256", "receipt_sha256",
    }
    missing = sorted(required - set(value))
    if missing:
        raise MuseElectionV2Error(f"v3 lease receipt: missing binding fields {missing}")
    binding = {
        "schema_version": LEASE_BINDING_SCHEMA,
        "receipt_schema": value["schema"],
        "claimant": value["claimant"],
        "claim_id": value["claim_id"],
        "seam_sha256": value["seam_sha256"],
        "lease_ref": value["lease_ref"],
        "lease_commit_sha": value["lease_commit_sha"],
        "claim_capability_sha256": value["claim_capability_sha256"],
        "receipt_sha256": value["receipt_sha256"],
    }
    return _normalize_lease_binding(binding)


def normalize_candidate(raw: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _obj(raw, "candidate")
    fields = {
        "buyer_scope_sha256", "recipient_fingerprint", "offer_scope_sha256", "route_kind",
        "intent_sha256", "body_sha256", "claimant", "operation_id", "lease_binding",
    }
    _exact(candidate, fields, "candidate")
    route = _text(candidate["route_kind"], "candidate.route_kind", max_len=32)
    if route not in ROUTE_KINDS:
        raise MuseElectionV2Error("candidate.route_kind: unsupported route")
    claimant = _text(candidate["claimant"], "candidate.claimant", max_len=120)
    lease_binding = _normalize_lease_binding(candidate["lease_binding"])
    if lease_binding["claimant"] != claimant:
        raise MuseElectionV2Error("candidate.lease_binding.claimant must equal candidate.claimant")
    return {
        "buyer_scope_sha256": _hex64(candidate["buyer_scope_sha256"], "candidate.buyer_scope_sha256"),
        "recipient_fingerprint": _hex64(candidate["recipient_fingerprint"], "candidate.recipient_fingerprint"),
        "offer_scope_sha256": _hex64(candidate["offer_scope_sha256"], "candidate.offer_scope_sha256"),
        "route_kind": route,
        "intent_sha256": _hex64(candidate["intent_sha256"], "candidate.intent_sha256"),
        "body_sha256": _hex64(candidate["body_sha256"], "candidate.body_sha256"),
        "claimant": claimant,
        "operation_id": _text(candidate["operation_id"], "candidate.operation_id", max_len=200),
        "lease_binding": lease_binding,
    }


def publication_key(candidate: Mapping[str, Any]) -> str:
    c = normalize_candidate(candidate)
    return _digest({
        "schema_version": PUBLICATION_KEY_SCHEMA,
        "buyer_scope_sha256": c["buyer_scope_sha256"],
        "recipient_fingerprint": c["recipient_fingerprint"],
        "offer_scope_sha256": c["offer_scope_sha256"],
        "route_kind": c["route_kind"],
    })


def candidate_digest(
    candidate: Mapping[str, Any],
    *,
    request_id: str,
    requested_at: str,
) -> str:
    """Bind normalized candidate bytes to one canonical request generation."""
    c = normalize_candidate(candidate)
    rid = _request_id(request_id, "candidate.request_id")
    requested = _fmt(_utc(requested_at, "candidate.requested_at"))
    return _digest({
        "schema_version": CANDIDATE_GENERATION_SCHEMA,
        "candidate": c,
        "request_id": rid,
        "requested_at": requested,
    })


def lease_binding_digest(candidate: Mapping[str, Any]) -> str:
    c = normalize_candidate(candidate)
    return _digest(c["lease_binding"])


def _request_message(*, request_id: str, publication_key_sha256: str, candidate_sha256: str, claimant: str, operation_id: str) -> str:
    return (
        "MUSE PUBLICATION ELECTION v2\n"
        f"request_id={request_id}\n"
        f"publication_key={publication_key_sha256}\n"
        f"candidate_sha256={candidate_sha256}\n"
        f"claimant={claimant}\n"
        f"operation_id={operation_id}\n"
        "Select at most one candidate for this publication_key.\n"
        "Reply exactly one line: SELECTED <request_id> <publication_key> <candidate_sha256> "
        "or NOT_SELECTED <request_id> <publication_key> <candidate_sha256> "
        "or CANCELLED <request_id> <publication_key> <candidate_sha256>."
    )


def _decision_message(kind: str, request_id: str, publication_key_sha256: str, candidate_sha256: str) -> str:
    if kind not in {"SELECTED", "NOT_SELECTED", "CANCELLED"}:
        raise MuseElectionV2Error("decision kind invalid")
    return f"{kind} {request_id} {publication_key_sha256} {candidate_sha256}"


def prepare_request(candidate: Mapping[str, Any], *, request_id: str, requested_at: str) -> dict[str, Any]:
    c = normalize_candidate(candidate)
    rid = _request_id(request_id)
    requested = _utc(requested_at, "requested_at")
    pub = publication_key(c)
    cand = candidate_digest(
        c,
        request_id=rid,
        requested_at=_fmt(requested),
    )
    message = _request_message(
        request_id=rid,
        publication_key_sha256=pub,
        candidate_sha256=cand,
        claimant=c["claimant"],
        operation_id=c["operation_id"],
    )
    payload = {
        "schema_version": REQUEST_SCHEMA,
        "request_id": rid,
        "candidate": c,
        "publication_key": pub,
        "candidate_sha256": cand,
        "lease_binding_sha256": lease_binding_digest(c),
        "requested_at": _fmt(requested),
        "response_deadline_at": _fmt(requested + timedelta(seconds=RESPONSE_WINDOW_SECONDS)),
        "muse_user_id": MUSE_USER_ID,
        "muse_dm_conversation_id": MUSE_DM_CONVERSATION_ID,
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "external_send_authorized": False,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "request_sha256": _digest(payload), "message": message}


def _validate_request(raw: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    request = _obj(raw, "request")
    _exact(request, {"payload", "request_sha256", "message"}, "request")
    payload = _obj(request["payload"], "request.payload")
    fields = {
        "schema_version", "request_id", "candidate", "publication_key", "candidate_sha256",
        "lease_binding_sha256", "requested_at", "response_deadline_at", "muse_user_id",
        "muse_dm_conversation_id", "message_sha256", "external_send_authorized", "side_effects_authorized",
    }
    _exact(payload, fields, "request.payload")
    if payload["schema_version"] != REQUEST_SCHEMA:
        raise MuseElectionV2Error("request: unsupported schema")
    c = normalize_candidate(payload["candidate"])
    rid = _request_id(payload["request_id"], "request.request_id")
    requested = _utc(payload["requested_at"], "request.requested_at")
    pub = _hex64(payload["publication_key"], "request.publication_key")
    cand = _hex64(payload["candidate_sha256"], "request.candidate_sha256")
    lease_binding = _hex64(payload["lease_binding_sha256"], "request.lease_binding_sha256")
    if (
        publication_key(c) != pub
        or candidate_digest(c, request_id=rid, requested_at=_fmt(requested)) != cand
        or lease_binding_digest(c) != lease_binding
    ):
        raise MuseElectionV2Error("request: candidate/publication/lease digest mismatch")
    deadline = _utc(payload["response_deadline_at"], "request.response_deadline_at")
    if deadline != requested + timedelta(seconds=RESPONSE_WINDOW_SECONDS):
        raise MuseElectionV2Error("request: response deadline mismatch")
    if payload["muse_user_id"] != MUSE_USER_ID or payload["muse_dm_conversation_id"] != MUSE_DM_CONVERSATION_ID:
        raise MuseElectionV2Error("request: pinned Muse route mismatch")
    if payload["external_send_authorized"] is not False or payload["side_effects_authorized"] is not False:
        raise MuseElectionV2Error("request may never authorize side effects")
    message = _text(request["message"], "request.message", max_len=4096, multiline=True)
    expected = _request_message(
        request_id=rid,
        publication_key_sha256=pub,
        candidate_sha256=cand,
        claimant=c["claimant"],
        operation_id=c["operation_id"],
    )
    if message != expected:
        raise MuseElectionV2Error("request: exact message mismatch")
    if hashlib.sha256(message.encode("utf-8")).hexdigest() != _hex64(payload["message_sha256"], "request.message_sha256"):
        raise MuseElectionV2Error("request: message digest mismatch")
    request_sha = _hex64(request["request_sha256"], "request.request_sha256")
    if _digest(payload) != request_sha:
        raise MuseElectionV2Error("request: digest mismatch")
    return payload, request_sha, message


def _normalize_message(raw: Mapping[str, Any], index: int) -> dict[str, str]:
    label = f"snapshot.messages[{index}]"
    msg = _obj(raw, label)
    _exact(msg, {"message_ts", "author_user_id", "text"}, label)
    return {
        "message_ts": _text(msg["message_ts"], label + ".message_ts", max_len=32),
        "author_user_id": _slack_id(msg["author_user_id"], label + ".author_user_id"),
        "text": _text(msg["text"], label + ".text", max_len=4096, multiline=True),
    }


def normalize_snapshot(raw: Mapping[str, Any]) -> dict[str, Any]:
    snap = _obj(raw, "snapshot")
    fields = {"schema_version", "complete", "channel_id", "coverage_started_at", "captured_at", "messages"}
    _exact(snap, fields, "snapshot")
    if snap["schema_version"] != SNAPSHOT_SCHEMA:
        raise MuseElectionV2Error("snapshot: unsupported schema")
    if type(snap["complete"]) is not bool:
        raise MuseElectionV2Error("snapshot.complete: boolean required")
    channel = _slack_id(snap["channel_id"], "snapshot.channel_id")
    coverage = _utc(snap["coverage_started_at"], "snapshot.coverage_started_at")
    captured = _utc(snap["captured_at"], "snapshot.captured_at")
    messages = [_normalize_message(v, i) for i, v in enumerate(_arr(snap["messages"], "snapshot.messages"))]
    seen: dict[str, dict[str, str]] = {}
    for msg in messages:
        _slack_epoch(msg["message_ts"], "snapshot.message_ts")
        prior = seen.get(msg["message_ts"])
        if prior is not None and prior != msg:
            raise MuseElectionV2Error(f"snapshot: conflicting message_ts {msg['message_ts']}")
        seen[msg["message_ts"]] = msg
    deduped = sorted(seen.values(), key=lambda x: (_slack_epoch(x["message_ts"], "message_ts"), x["author_user_id"], x["text"]))
    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "complete": snap["complete"],
        "channel_id": channel,
        "coverage_started_at": _fmt(coverage),
        "captured_at": _fmt(captured),
        "messages": deduped,
    }


def _parse_decision(text: str) -> tuple[str, str, str, str] | None:
    match = _DECISION_RE.fullmatch(text)
    if not match:
        return None
    kind, rid, pub, cand = match.groups()
    return kind, rid, pub, cand


def _prior_payload(raw: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if type(raw) is not dict or set(raw) != {"payload", "receipt_sha256"}:
        return None
    payload = raw.get("payload")
    if type(payload) is not dict or payload.get("schema_version") != RECEIPT_SCHEMA:
        return None
    try:
        claimed = _hex64(raw.get("receipt_sha256"), "prior.receipt_sha256")
        if _digest(payload) != claimed:
            return None
        if not verify_receipt(raw):
            return None
    except MuseElectionV2Error:
        return None
    return payload


def compile_receipt(
    request: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    observed_at: str,
    prior_receipts: Iterable[Mapping[str, Any]] = (),
    ledger_complete: bool,
) -> dict[str, Any]:
    req, request_sha, request_message = _validate_request(request)
    snap = normalize_snapshot(snapshot)
    observed = _utc(observed_at, "observed_at")
    requested = _utc(req["requested_at"], "request.requested_at")
    deadline = _utc(req["response_deadline_at"], "request.response_deadline_at")
    coverage = _utc(snap["coverage_started_at"], "snapshot.coverage_started_at")
    captured = _utc(snap["captured_at"], "snapshot.captured_at")
    future = observed + timedelta(seconds=FUTURE_SKEW_SECONDS)
    reasons: list[str] = []

    if type(ledger_complete) is not bool or ledger_complete is not True:
        reasons.append("PRIOR_RECEIPT_LEDGER_INCOMPLETE")
    if snap["complete"] is not True:
        reasons.append("SNAPSHOT_INCOMPLETE")
    if snap["channel_id"] != MUSE_DM_CONVERSATION_ID:
        reasons.append("WRONG_MUSE_DM_CONVERSATION")
    if coverage > requested - timedelta(seconds=COLLISION_LOOKBACK_SECONDS):
        reasons.append("COLLISION_LOOKBACK_INCOMPLETE")
    if captured < requested:
        reasons.append("SNAPSHOT_PRECEDES_REQUEST")
    if captured > future:
        reasons.append("SNAPSHOT_IN_FUTURE")
    if observed - captured > timedelta(seconds=SNAPSHOT_FRESHNESS_SECONDS):
        reasons.append("SNAPSHOT_STALE")

    request_matches: list[dict[str, str]] = []
    decisions: list[tuple[dict[str, str], tuple[str, str, str, str]]] = []
    for msg in snap["messages"]:
        msg_time = _slack_dt(msg["message_ts"], "message.message_ts")
        if msg_time < coverage or msg_time > captured:
            reasons.append(f"MESSAGE_OUTSIDE_SNAPSHOT:{msg['message_ts']}")
        if msg_time > future:
            reasons.append(f"MESSAGE_IN_FUTURE:{msg['message_ts']}")
        if msg["text"] == request_message:
            request_matches.append(msg)
        parsed = _parse_decision(msg["text"])
        if parsed is not None and parsed[2] == req["publication_key"]:
            decisions.append((msg, parsed))

    if len(request_matches) != 1:
        reasons.append("EXACT_REQUEST_MESSAGE_COUNT_NOT_ONE")
        request_event = None
    else:
        request_event = request_matches[0]
        request_ts = _slack_dt(request_event["message_ts"], "request_message_ts")
        if request_event["author_user_id"] == MUSE_USER_ID:
            reasons.append("REQUEST_SELF_AUTHORED_BY_MUSE")
        if request_ts < requested or request_ts > requested + timedelta(seconds=REQUEST_TRANSPORT_SKEW_SECONDS):
            reasons.append("REQUEST_TRANSPORT_TIME_MISMATCH")

    muse_decisions: list[tuple[dict[str, str], tuple[str, str, str, str]]] = []
    for msg, parsed in decisions:
        if msg["author_user_id"] != MUSE_USER_ID:
            reasons.append(f"DECISION_NOT_FROM_MUSE:{msg['message_ts']}")
            continue
        muse_decisions.append((msg, parsed))

    selected_events = [(msg, p) for msg, p in muse_decisions if p[0] == "SELECTED"]
    distinct_selected = {p[3] for _, p in selected_events}
    if len(distinct_selected) > 1:
        reasons.append("MULTIPLE_DISTINCT_WINNERS")

    exact_decisions = [(msg, p) for msg, p in muse_decisions if p[1] == req["request_id"] and p[3] == req["candidate_sha256"]]
    wrong_echo = [(msg, p) for msg, p in muse_decisions if p[1] == req["request_id"] and p[3] != req["candidate_sha256"]]
    if wrong_echo:
        reasons.append("REQUEST_ID_REBOUND_TO_DIFFERENT_CANDIDATE")

    if request_event is not None:
        request_ts = _slack_dt(request_event["message_ts"], "request_message_ts")
        for msg, _ in exact_decisions:
            dt = _slack_dt(msg["message_ts"], "decision_message_ts")
            if dt <= request_ts:
                reasons.append(f"DECISION_NOT_AFTER_REQUEST:{msg['message_ts']}")
            if dt > deadline:
                reasons.append(f"DECISION_AFTER_DEADLINE:{msg['message_ts']}")

    if any(p[0] == "SELECTED" and p[3] == req["candidate_sha256"] and p[1] != req["request_id"] for _, p in muse_decisions):
        reasons.append("SAME_CANDIDATE_SELECTED_FOR_DIFFERENT_REQUEST")

    valid_prior_payloads: list[Mapping[str, Any]] = []
    for prior in prior_receipts:
        payload = _prior_payload(prior)
        if payload is None:
            reasons.append("PRIOR_RECEIPT_LEDGER_INVALID")
        else:
            valid_prior_payloads.append(payload)
    prior_response_ts = {p.get("selection_message_ts") for p in valid_prior_payloads if p.get("selection_message_ts")}
    if any(p.get("request_sha256") == request_sha for p in valid_prior_payloads):
        reasons.append("REQUEST_EVIDENCE_REPLAY")
    if any(msg["message_ts"] in prior_response_ts for msg, p in exact_decisions if p[0] == "SELECTED"):
        reasons.append("SELECTION_EVIDENCE_REPLAY")

    decision = "HOLD"
    selected_event: tuple[dict[str, str], tuple[str, str, str, str]] | None = None
    winning_event: tuple[dict[str, str], tuple[str, str, str, str]] | None = None

    if not reasons:
        exact_sorted = sorted(exact_decisions, key=lambda x: _slack_epoch(x[0]["message_ts"], "decision_message_ts"))
        other_selected = [(msg, p) for msg, p in selected_events if p[3] != req["candidate_sha256"]]
        if exact_sorted:
            latest = exact_sorted[-1]
            kind = latest[1][0]
            if kind == "SELECTED":
                selected_at = _slack_dt(latest[0]["message_ts"], "selection_message_ts")
                if observed - selected_at > timedelta(seconds=SELECTION_FRESHNESS_SECONDS):
                    reasons.append("MUSE_SELECTION_STALE")
                elif other_selected:
                    reasons.append("COMPETING_WINNER")
                else:
                    decision = "SELECTED"
                    selected_event = latest
                    winning_event = latest
            else:
                decision = "NOT_SELECTED"
        elif other_selected:
            decision = "NOT_SELECTED"
            winning_event = sorted(other_selected, key=lambda x: _slack_epoch(x[0]["message_ts"], "winner_message_ts"))[-1]
        else:
            reasons.append("NO_MUSE_DECISION")

    if reasons:
        decision = "HOLD"
        selected_event = None
        winning_event = None

    snapshot_sha = _digest(snap)
    lease_binding = req["lease_binding_sha256"]
    selection_binding = None
    selection_message_ts = None
    selected_at = None
    if selected_event is not None:
        selection_message_ts = selected_event[0]["message_ts"]
        selected_at = _fmt(_slack_dt(selection_message_ts, "selection_message_ts"))
        selection_binding = _digest({
            "schema_version": SELECTION_BINDING_SCHEMA,
            "request_sha256": request_sha,
            "request_id": req["request_id"],
            "publication_key": req["publication_key"],
            "candidate_sha256": req["candidate_sha256"],
            "claimant": req["candidate"]["claimant"],
            "operation_id": req["candidate"]["operation_id"],
            "request_message_ts": request_event["message_ts"] if request_event else None,
            "selection_message_ts": selection_message_ts,
            "selected_at": selected_at,
            "lease_binding_sha256": lease_binding,
            "muse_user_id": MUSE_USER_ID,
            "muse_dm_conversation_id": MUSE_DM_CONVERSATION_ID,
        })

    winner_request_id = winning_event[1][1] if winning_event else None
    winner_candidate_sha = winning_event[1][3] if winning_event else None
    winner_message_ts = winning_event[0]["message_ts"] if winning_event else None

    payload = {
        "schema_version": RECEIPT_SCHEMA,
        "request_sha256": request_sha,
        "request_id": req["request_id"],
        "publication_key": req["publication_key"],
        "candidate_sha256": req["candidate_sha256"],
        "claimant": req["candidate"]["claimant"],
        "operation_id": req["candidate"]["operation_id"],
        "lease_binding_sha256": lease_binding,
        "snapshot_sha256": snapshot_sha,
        "decision": decision,
        "reasons": sorted(set(reasons)),
        "compiled_at": _fmt(observed),
        "request_message_ts": request_event["message_ts"] if request_event else None,
        "selection_message_ts": selection_message_ts,
        "selected_at": selected_at,
        "selection_binding_sha256": selection_binding,
        "winner_request_id": winner_request_id,
        "winner_candidate_sha256": winner_candidate_sha,
        "winner_message_ts": winner_message_ts,
        "muse_user_id": MUSE_USER_ID,
        "muse_dm_conversation_id": MUSE_DM_CONVERSATION_ID,
        "requires_current_worker_lease_possession": True,
        "requires_fresh_provider_preflight": True,
        "external_send_authorized": False,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": _digest(payload)}


def verify_receipt(raw: Mapping[str, Any]) -> bool:
    try:
        receipt = _obj(raw, "receipt")
        _exact(receipt, {"payload", "receipt_sha256"}, "receipt")
        payload = _obj(receipt["payload"], "receipt.payload")
        fields = {
            "schema_version", "request_sha256", "request_id", "publication_key", "candidate_sha256", "claimant",
            "operation_id", "lease_binding_sha256", "snapshot_sha256", "decision", "reasons",
            "compiled_at", "request_message_ts", "selection_message_ts", "selected_at",
            "selection_binding_sha256", "winner_request_id", "winner_candidate_sha256", "winner_message_ts",
            "muse_user_id", "muse_dm_conversation_id", "requires_current_worker_lease_possession",
            "requires_fresh_provider_preflight", "external_send_authorized", "side_effects_authorized",
        }
        _exact(payload, fields, "receipt.payload")
        if payload["schema_version"] != RECEIPT_SCHEMA:
            return False
        for key in ("request_sha256", "publication_key", "candidate_sha256", "lease_binding_sha256", "snapshot_sha256"):
            _hex64(payload[key], f"receipt.{key}")
        _request_id(payload["request_id"], "receipt.request_id")
        _text(payload["claimant"], "receipt.claimant", max_len=120)
        _text(payload["operation_id"], "receipt.operation_id", max_len=200)
        _utc(payload["compiled_at"], "receipt.compiled_at")
        if payload["decision"] not in {"SELECTED", "NOT_SELECTED", "HOLD"}:
            return False
        reasons = _arr(payload["reasons"], "receipt.reasons", max_items=128)
        if any(type(x) is not str or not x for x in reasons) or reasons != sorted(set(reasons)):
            return False
        if payload["muse_user_id"] != MUSE_USER_ID or payload["muse_dm_conversation_id"] != MUSE_DM_CONVERSATION_ID:
            return False
        if payload["requires_current_worker_lease_possession"] is not True or payload["requires_fresh_provider_preflight"] is not True:
            return False
        if payload["external_send_authorized"] is not False or payload["side_effects_authorized"] is not False:
            return False
        if payload["request_message_ts"] is not None:
            _slack_epoch(payload["request_message_ts"], "receipt.request_message_ts")

        if payload["decision"] == "SELECTED":
            if reasons:
                return False
            selection_ts = _text(payload["selection_message_ts"], "receipt.selection_message_ts", max_len=32)
            _slack_epoch(selection_ts, "receipt.selection_message_ts")
            selected_at = _fmt(_utc(payload["selected_at"], "receipt.selected_at"))
            claimed_binding = _hex64(payload["selection_binding_sha256"], "receipt.selection_binding_sha256")
            if payload["winner_request_id"] != payload["request_id"] or payload["winner_candidate_sha256"] != payload["candidate_sha256"] or payload["winner_message_ts"] != selection_ts:
                return False
            _request_id(payload["winner_request_id"], "receipt.winner_request_id")
            expected = _digest({
                "schema_version": SELECTION_BINDING_SCHEMA,
                "request_sha256": payload["request_sha256"],
                "request_id": payload["request_id"],
                "publication_key": payload["publication_key"],
                "candidate_sha256": payload["candidate_sha256"],
                "claimant": payload["claimant"],
                "operation_id": payload["operation_id"],
                "request_message_ts": payload["request_message_ts"],
                "selection_message_ts": selection_ts,
                "selected_at": selected_at,
                "lease_binding_sha256": payload["lease_binding_sha256"],
                "muse_user_id": MUSE_USER_ID,
                "muse_dm_conversation_id": MUSE_DM_CONVERSATION_ID,
            })
            if claimed_binding != expected:
                return False
        else:
            if any(payload[k] is not None for k in ("selection_message_ts", "selected_at", "selection_binding_sha256")):
                return False
            if payload["decision"] == "HOLD" and not reasons:
                return False
            if payload["decision"] == "NOT_SELECTED" and reasons:
                return False
            if payload["winner_request_id"] is not None:
                _request_id(payload["winner_request_id"], "receipt.winner_request_id")
            if payload["winner_candidate_sha256"] is not None:
                _hex64(payload["winner_candidate_sha256"], "receipt.winner_candidate_sha256")
            if payload["winner_message_ts"] is not None:
                _slack_epoch(payload["winner_message_ts"], "receipt.winner_message_ts")
        claimed = _hex64(receipt["receipt_sha256"], "receipt.receipt_sha256")
        return _digest(payload) == claimed
    except (MuseElectionV2Error, TypeError, ValueError):
        return False


def verify_selected_binding(request: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    try:
        req, request_sha, _ = _validate_request(request)
        if not verify_receipt(receipt):
            return False
        payload = _obj(receipt["payload"], "receipt.payload")
        return (
            payload["decision"] == "SELECTED"
            and payload["request_sha256"] == request_sha
            and payload["request_id"] == req["request_id"]
            and payload["publication_key"] == req["publication_key"]
            and payload["candidate_sha256"] == req["candidate_sha256"]
            and payload["claimant"] == req["candidate"]["claimant"]
            and payload["operation_id"] == req["candidate"]["operation_id"]
            and payload["lease_binding_sha256"] == req["lease_binding_sha256"]
            and payload["requires_current_worker_lease_possession"] is True
            and payload["requires_fresh_provider_preflight"] is True
            and payload["external_send_authorized"] is False
            and payload["side_effects_authorized"] is False
        )
    except MuseElectionV2Error:
        return False


def _read_json(path: str, label: str) -> Any:
    raw = Path(path).read_bytes()
    if len(raw) > 2_000_000:
        raise MuseElectionV2Error(f"{label}: file too large")
    return parse_json_bytes(raw, label)


def _write_json(value: Any) -> None:
    sys.stdout.buffer.write(_canon_bytes(value))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    for name in ("buyer-scope-sha256", "recipient-fingerprint", "offer-scope-sha256", "intent-sha256", "body-sha256"):
        prep.add_argument("--" + name, required=True)
    prep.add_argument("--route-kind", required=True)
    prep.add_argument("--claimant", required=True)
    prep.add_argument("--operation-id", required=True)
    prep.add_argument("--lease-binding", required=True)
    prep.add_argument("--request-id", required=True)
    prep.add_argument("--requested-at", required=True)
    comp = sub.add_parser("compile")
    comp.add_argument("--request", required=True)
    comp.add_argument("--snapshot", required=True)
    comp.add_argument("--observed-at", required=True)
    comp.add_argument("--prior-ledger")
    comp.add_argument("--ledger-complete", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt", required=True)
    verify.add_argument("--request")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            lease_binding = _read_json(args.lease_binding, "lease binding")
            candidate = {
                "buyer_scope_sha256": args.buyer_scope_sha256,
                "recipient_fingerprint": args.recipient_fingerprint,
                "offer_scope_sha256": args.offer_scope_sha256,
                "route_kind": args.route_kind,
                "intent_sha256": args.intent_sha256,
                "body_sha256": args.body_sha256,
                "claimant": args.claimant,
                "operation_id": args.operation_id,
                "lease_binding": lease_binding,
            }
            _write_json(prepare_request(candidate, request_id=args.request_id, requested_at=args.requested_at))
            return 0
        if args.command == "compile":
            request = _read_json(args.request, "request")
            snapshot = _read_json(args.snapshot, "snapshot")
            prior: list[Mapping[str, Any]] = []
            if args.prior_ledger:
                ledger = _read_json(args.prior_ledger, "prior ledger")
                if type(ledger) is not list:
                    raise MuseElectionV2Error("prior ledger: array required")
                prior = ledger
            receipt = compile_receipt(
                request,
                snapshot,
                observed_at=args.observed_at,
                prior_receipts=prior,
                ledger_complete=args.ledger_complete,
            )
            _write_json(receipt)
            return {"SELECTED": 0, "NOT_SELECTED": 3, "HOLD": 4}[receipt["payload"]["decision"]]
        receipt = _read_json(args.receipt, "receipt")
        ok = verify_receipt(receipt)
        if ok and args.request:
            ok = verify_selected_binding(_read_json(args.request, "request"), receipt)
        _write_json({"valid": ok})
        return 0 if ok else 2
    except (MuseElectionV2Error, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
