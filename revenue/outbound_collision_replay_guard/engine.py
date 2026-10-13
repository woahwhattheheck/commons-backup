"""Deterministic single-writer guard for outbound intents.

This module never sends email/DM, never contacts Muse, and never authenticates or
mints Muse authority.  It consumes retained evidence and emits a CAS-bound ledger
transition + receipt.  A caller must commit the returned ledger only if the
current durable ledger still has the exact input SHA-256 recorded in the receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LEDGER_SCHEMA = "outbound-collision-replay-guard/ledger/v1"
REQUEST_SCHEMA = "outbound-collision-replay-guard/request/v1"
RECEIPT_SCHEMA = "outbound-collision-replay-guard/receipt/v1"
MUSE_SCHEMA = "outbound-collision-replay-guard/muse-evidence/v1"
ATTEMPT_SCHEMA = "outbound-collision-replay-guard/send-attempt/v1"
RESULT_SCHEMA = "outbound-collision-replay-guard/send-result/v1"
TRUTH_BOUNDARY = "COORDINATION_EVIDENCE_ONLY_NO_SEND_AUTHORITY"

STATES = {
    "CLAIMED",
    "YIELD_EXISTING",
    "WAIT_MUSE",
    "READY_SINGLE_WRITER",
    "SENT_TERMINAL",
    "RELEASED_UNSENT",
    "HOLD_AMBIGUOUS_COUNTERPARTY",
}
OPERATIONS = {
    "CLAIM",
    "HEARTBEAT",
    "APPLY_MUSE",
    "RECORD_SEND_ATTEMPT",
    "RECORD_SEND_RESULT",
    "RELEASE",
    "RECOVER",
}
THREAD_MODES = {"REPLY", "NEW_THREAD"}
RESOLUTION = {"EXACT", "AMBIGUOUS"}
RESULT_STATUSES = {"ACCEPTED", "REJECTED", "UNKNOWN"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,199}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MAX_FILE = 4 * 1024 * 1024


class GuardError(ValueError):
    pass


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise GuardError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_number(value):
    raise GuardError(f"non-integer JSON number forbidden: {value}")


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_json(raw: bytes, label: str = "input") -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise GuardError(f"{label}: bytes required")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise GuardError(f"{label}: BOM forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_float=_bad_number,
            parse_constant=_bad_number,
        )
    except GuardError:
        raise
    except Exception as exc:
        raise GuardError(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(value, dict):
        raise GuardError(f"{label}: object required")
    return value


def _keys(value: Any, wanted: list[str], where: str) -> None:
    if not isinstance(value, dict) or set(value) != set(wanted):
        raise GuardError(f"{where}: keys mismatch")


def _string(value: Any, where: str, *, token: bool = False, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise GuardError(f"{where}: invalid string")
    if any(ord(ch) < 32 for ch in value):
        raise GuardError(f"{where}: control character")
    if token and not TOKEN_RE.fullmatch(value):
        raise GuardError(f"{where}: invalid token")
    return value


def _optional_string(value: Any, where: str, *, token: bool = False, limit: int = 4096) -> str | None:
    if value is None:
        return None
    return _string(value, where, token=token, limit=limit)


def _integer(value: Any, where: str, lo: int = 0, hi: int = 10**12) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise GuardError(f"{where}: integer required")
    return value


def _boolean(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise GuardError(f"{where}: bool required")
    return value


def _sha(value: Any, where: str) -> str:
    value = _string(value, where, limit=64)
    if not SHA256_RE.fullmatch(value):
        raise GuardError(f"{where}: sha256 required")
    return value


def _timestamp(value: Any, where: str) -> str:
    value = _string(value, where, limit=20)
    if not UTC_RE.fullmatch(value):
        raise GuardError(f"{where}: UTC second timestamp required")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise GuardError(f"{where}: invalid timestamp") from exc
    return value


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _enum(value: Any, choices: set[str], where: str) -> str:
    value = _string(value, where, token=True, limit=80)
    if value not in choices:
        raise GuardError(f"{where}: unsupported value")
    return value


def _list_strings(value: Any, where: str, *, max_items: int = 32) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise GuardError(f"{where}: list required")
    out = [_string(item, f"{where}[{i}]", token=True, limit=200) for i, item in enumerate(value)]
    if len(out) != len(set(out)):
        raise GuardError(f"{where}: duplicate item")
    return sorted(out)


def authority_flags() -> dict[str, bool]:
    return {
        "external_send_authorized": False,
        "email_or_dm_authorized": False,
        "provider_mutation_authorized": False,
        "muse_authority_minted": False,
        "counterparty_interest_inferred": False,
        "payment_or_revenue_recognized": False,
    }


def empty_ledger() -> dict[str, Any]:
    return {"schema": LEDGER_SCHEMA, "records": []}


def _intent(value: Any) -> dict[str, Any]:
    _keys(
        value,
        [
            "counterparty_key",
            "counterparty_resolution",
            "observed_aliases",
            "provider",
            "thread_scope_key",
            "thread_mode",
            "purpose_key",
            "body_sha256",
        ],
        "request.intent",
    )
    counterparty = _string(value["counterparty_key"], "request.intent.counterparty_key", token=True)
    provider = _string(value["provider"], "request.intent.provider", token=True)
    thread_scope = _string(value["thread_scope_key"], "request.intent.thread_scope_key", token=True)
    purpose = _string(value["purpose_key"], "request.intent.purpose_key", token=True)
    resolution = _enum(value["counterparty_resolution"], RESOLUTION, "request.intent.counterparty_resolution")
    mode = _enum(value["thread_mode"], THREAD_MODES, "request.intent.thread_mode")
    aliases = _list_strings(value["observed_aliases"], "request.intent.observed_aliases")
    body_sha = _sha(value["body_sha256"], "request.intent.body_sha256")
    fingerprint_payload = {
        "counterparty_key": counterparty,
        "provider": provider,
        "thread_scope_key": thread_scope,
        "purpose_key": purpose,
    }
    route_payload = {"counterparty_key": counterparty, "provider": provider, "purpose_key": purpose}
    return {
        "counterparty_key": counterparty,
        "counterparty_resolution": resolution,
        "observed_aliases": aliases,
        "provider": provider,
        "thread_scope_key": thread_scope,
        "thread_mode": mode,
        "purpose_key": purpose,
        "body_sha256": body_sha,
        "fingerprint": sha256(canonical_json(fingerprint_payload)),
        "route_key": sha256(canonical_json(route_payload)),
    }


def _normalize_muse(value: Any, now: str) -> dict[str, Any] | None:
    if value is None:
        return None
    _keys(
        value,
        [
            "schema",
            "receipt_id",
            "fingerprint",
            "claimant_id",
            "session_id",
            "generation",
            "body_sha256",
            "selected",
            "observed_at",
            "expires_at",
            "source_uri",
            "source_sha256",
        ],
        "request.muse",
    )
    if value["schema"] != MUSE_SCHEMA:
        raise GuardError("request.muse: unsupported schema")
    observed = _timestamp(value["observed_at"], "request.muse.observed_at")
    expires = _timestamp(value["expires_at"], "request.muse.expires_at")
    if _dt(observed) > _dt(now):
        raise GuardError("request.muse.observed_at: future evidence")
    if _dt(expires) < _dt(observed):
        raise GuardError("request.muse.expires_at: before observed_at")
    return {
        "schema": MUSE_SCHEMA,
        "receipt_id": _string(value["receipt_id"], "request.muse.receipt_id", token=True),
        "fingerprint": _sha(value["fingerprint"], "request.muse.fingerprint"),
        "claimant_id": _string(value["claimant_id"], "request.muse.claimant_id", token=True),
        "session_id": _string(value["session_id"], "request.muse.session_id", token=True),
        "generation": _integer(value["generation"], "request.muse.generation", 1, 10**9),
        "body_sha256": _sha(value["body_sha256"], "request.muse.body_sha256"),
        "selected": _boolean(value["selected"], "request.muse.selected"),
        "observed_at": observed,
        "expires_at": expires,
        "source_uri": _string(value["source_uri"], "request.muse.source_uri", limit=2048),
        "source_sha256": _sha(value["source_sha256"], "request.muse.source_sha256"),
    }


def _normalize_attempt(value: Any, now: str) -> dict[str, Any] | None:
    if value is None:
        return None
    _keys(
        value,
        [
            "schema",
            "attempt_id",
            "fingerprint",
            "generation",
            "body_sha256",
            "attempted_at",
            "provider_request_id",
            "source_uri",
            "source_sha256",
        ],
        "request.send_attempt",
    )
    if value["schema"] != ATTEMPT_SCHEMA:
        raise GuardError("request.send_attempt: unsupported schema")
    attempted = _timestamp(value["attempted_at"], "request.send_attempt.attempted_at")
    if _dt(attempted) > _dt(now):
        raise GuardError("request.send_attempt.attempted_at: future evidence")
    return {
        "schema": ATTEMPT_SCHEMA,
        "attempt_id": _string(value["attempt_id"], "request.send_attempt.attempt_id", token=True),
        "fingerprint": _sha(value["fingerprint"], "request.send_attempt.fingerprint"),
        "generation": _integer(value["generation"], "request.send_attempt.generation", 1, 10**9),
        "body_sha256": _sha(value["body_sha256"], "request.send_attempt.body_sha256"),
        "attempted_at": attempted,
        "provider_request_id": _string(value["provider_request_id"], "request.send_attempt.provider_request_id", token=True),
        "source_uri": _string(value["source_uri"], "request.send_attempt.source_uri", limit=2048),
        "source_sha256": _sha(value["source_sha256"], "request.send_attempt.source_sha256"),
    }


def _normalize_result(value: Any, now: str) -> dict[str, Any] | None:
    if value is None:
        return None
    _keys(
        value,
        [
            "schema",
            "result_id",
            "attempt_id",
            "fingerprint",
            "generation",
            "body_sha256",
            "status",
            "observed_at",
            "provider_message_id",
            "source_uri",
            "source_sha256",
        ],
        "request.send_result",
    )
    if value["schema"] != RESULT_SCHEMA:
        raise GuardError("request.send_result: unsupported schema")
    observed = _timestamp(value["observed_at"], "request.send_result.observed_at")
    if _dt(observed) > _dt(now):
        raise GuardError("request.send_result.observed_at: future evidence")
    return {
        "schema": RESULT_SCHEMA,
        "result_id": _string(value["result_id"], "request.send_result.result_id", token=True),
        "attempt_id": _string(value["attempt_id"], "request.send_result.attempt_id", token=True),
        "fingerprint": _sha(value["fingerprint"], "request.send_result.fingerprint"),
        "generation": _integer(value["generation"], "request.send_result.generation", 1, 10**9),
        "body_sha256": _sha(value["body_sha256"], "request.send_result.body_sha256"),
        "status": _enum(value["status"], RESULT_STATUSES, "request.send_result.status"),
        "observed_at": observed,
        "provider_message_id": _optional_string(value["provider_message_id"], "request.send_result.provider_message_id", token=True),
        "source_uri": _string(value["source_uri"], "request.send_result.source_uri", limit=2048),
        "source_sha256": _sha(value["source_sha256"], "request.send_result.source_sha256"),
    }


def normalize_request(value: dict[str, Any]) -> dict[str, Any]:
    _keys(
        value,
        [
            "schema",
            "evaluation_time",
            "operation",
            "expected_ledger_sha256",
            "claimant_id",
            "session_id",
            "lease_ttl_seconds",
            "generation",
            "intent",
            "muse",
            "send_attempt",
            "send_result",
        ],
        "request",
    )
    if value["schema"] != REQUEST_SCHEMA:
        raise GuardError("request: unsupported schema")
    now = _timestamp(value["evaluation_time"], "request.evaluation_time")
    generation = value["generation"]
    if generation is not None:
        generation = _integer(generation, "request.generation", 1, 10**9)
    return {
        "evaluation_time": now,
        "operation": _enum(value["operation"], OPERATIONS, "request.operation"),
        "expected_ledger_sha256": _sha(value["expected_ledger_sha256"], "request.expected_ledger_sha256"),
        "claimant_id": _string(value["claimant_id"], "request.claimant_id", token=True),
        "session_id": _string(value["session_id"], "request.session_id", token=True),
        "lease_ttl_seconds": _integer(value["lease_ttl_seconds"], "request.lease_ttl_seconds", 60, 86400),
        "generation": generation,
        "intent": _intent(value["intent"]),
        "muse": _normalize_muse(value["muse"], now),
        "send_attempt": _normalize_attempt(value["send_attempt"], now),
        "send_result": _normalize_result(value["send_result"], now),
    }


def normalize_ledger(value: dict[str, Any]) -> dict[str, Any]:
    _keys(value, ["schema", "records"], "ledger")
    if value["schema"] != LEDGER_SCHEMA:
        raise GuardError("ledger: unsupported schema")
    if not isinstance(value["records"], list) or len(value["records"]) > 10000:
        raise GuardError("ledger.records: list required")
    records = []
    seen = set()
    for i, record in enumerate(value["records"]):
        where = f"ledger.records[{i}]"
        _keys(
            record,
            [
                "fingerprint",
                "route_key",
                "counterparty_key",
                "provider",
                "thread_scope_key",
                "thread_mode",
                "purpose_key",
                "body_sha256",
                "claimant_id",
                "session_id",
                "generation",
                "lease_expires_at",
                "state",
                "muse",
                "send_attempt",
                "send_result",
                "updated_at",
            ],
            where,
        )
        fp = _sha(record["fingerprint"], where + ".fingerprint")
        if fp in seen:
            raise GuardError("ledger.records: duplicate fingerprint")
        seen.add(fp)
        updated = _timestamp(record["updated_at"], where + ".updated_at")
        normalized = {
            "fingerprint": fp,
            "route_key": _sha(record["route_key"], where + ".route_key"),
            "counterparty_key": _string(record["counterparty_key"], where + ".counterparty_key", token=True),
            "provider": _string(record["provider"], where + ".provider", token=True),
            "thread_scope_key": _string(record["thread_scope_key"], where + ".thread_scope_key", token=True),
            "thread_mode": _enum(record["thread_mode"], THREAD_MODES, where + ".thread_mode"),
            "purpose_key": _string(record["purpose_key"], where + ".purpose_key", token=True),
            "body_sha256": _sha(record["body_sha256"], where + ".body_sha256"),
            "claimant_id": _string(record["claimant_id"], where + ".claimant_id", token=True),
            "session_id": _string(record["session_id"], where + ".session_id", token=True),
            "generation": _integer(record["generation"], where + ".generation", 1, 10**9),
            "lease_expires_at": _timestamp(record["lease_expires_at"], where + ".lease_expires_at"),
            "state": _enum(record["state"], STATES, where + ".state"),
            "muse": _normalize_muse(record["muse"], updated) if record["muse"] else None,
            "send_attempt": _normalize_attempt(record["send_attempt"], updated) if record["send_attempt"] else None,
            "send_result": _normalize_result(record["send_result"], updated) if record["send_result"] else None,
            "updated_at": updated,
        }
        records.append(normalized)
    records.sort(key=lambda r: r["fingerprint"])
    return {"schema": LEDGER_SCHEMA, "records": records}


def _lease_expired(record: dict[str, Any], now: str) -> bool:
    return _dt(record["lease_expires_at"]) < _dt(now)


def _holder(record: dict[str, Any], request: dict[str, Any]) -> bool:
    return record["claimant_id"] == request["claimant_id"] and record["session_id"] == request["session_id"]


def _pending_or_unknown(record: dict[str, Any]) -> bool:
    if record["send_attempt"] is None:
        return False
    if record["send_result"] is None:
        return True
    return record["send_result"]["status"] == "UNKNOWN"


def _new_record(request: dict[str, Any], generation: int) -> dict[str, Any]:
    intent = request["intent"]
    return {
        "fingerprint": intent["fingerprint"],
        "route_key": intent["route_key"],
        "counterparty_key": intent["counterparty_key"],
        "provider": intent["provider"],
        "thread_scope_key": intent["thread_scope_key"],
        "thread_mode": intent["thread_mode"],
        "purpose_key": intent["purpose_key"],
        "body_sha256": intent["body_sha256"],
        "claimant_id": request["claimant_id"],
        "session_id": request["session_id"],
        "generation": generation,
        "lease_expires_at": _ts(_dt(request["evaluation_time"]) + timedelta(seconds=request["lease_ttl_seconds"])),
        "state": "CLAIMED",
        "muse": None,
        "send_attempt": None,
        "send_result": None,
        "updated_at": request["evaluation_time"],
    }


def _same_route_collision(records: list[dict[str, Any]], intent: dict[str, Any]) -> dict[str, Any] | None:
    for record in records:
        if record["fingerprint"] == intent["fingerprint"]:
            continue
        if record["route_key"] != intent["route_key"]:
            continue
        if record["state"] == "RELEASED_UNSENT":
            continue
        return record
    return None


def _receipt(before_raw: bytes, request_raw: bytes, after_raw: bytes, decision: str, mutation: bool, reasons: list[str], record: dict[str, Any] | None) -> bytes:
    value = {
        "schema": RECEIPT_SCHEMA,
        "truth_boundary": TRUTH_BOUNDARY,
        "before_ledger_sha256": sha256(before_raw),
        "request_sha256": sha256(request_raw),
        "after_ledger_sha256": sha256(after_raw),
        "decision_state": decision,
        "mutation": mutation,
        "reasons": reasons,
        "fingerprint": record["fingerprint"] if record else None,
        "generation": record["generation"] if record else None,
        "authority": authority_flags(),
        "cas_contract": "commit after_ledger only if durable current ledger SHA256 still equals before_ledger_sha256",
    }
    return canonical_json(value)


def transition(ledger_raw: bytes, request_raw: bytes) -> tuple[bytes, bytes]:
    before_obj = normalize_ledger(load_json(ledger_raw, "ledger"))
    before_raw = canonical_json(before_obj)
    if bytes(ledger_raw) != before_raw:
        raise GuardError("ledger: input must be canonical JSON bytes")
    request_obj = normalize_request(load_json(request_raw, "request"))
    request_canonical = canonical_json(load_json(request_raw, "request"))
    if bytes(request_raw) != request_canonical:
        raise GuardError("request: input must be canonical JSON bytes")
    if request_obj["expected_ledger_sha256"] != sha256(before_raw):
        raise GuardError("request.expected_ledger_sha256: stale ledger precondition")

    records = [dict(r) for r in before_obj["records"]]
    intent = request_obj["intent"]
    now = request_obj["evaluation_time"]
    operation = request_obj["operation"]
    existing = next((r for r in records if r["fingerprint"] == intent["fingerprint"]), None)
    mutation = False
    reasons: list[str] = []
    decision = "CLAIMED"
    output_record: dict[str, Any] | None = existing

    if intent["counterparty_resolution"] != "EXACT":
        decision = "HOLD_AMBIGUOUS_COUNTERPARTY"
        reasons.append("counterparty identity is not exact; no lease was created or changed")
    elif operation == "CLAIM" and existing is None:
        related = _same_route_collision(records, intent)
        if related is not None:
            if related["thread_mode"] != intent["thread_mode"] or related["thread_scope_key"] != intent["thread_scope_key"]:
                decision = "HOLD_AMBIGUOUS_COUNTERPARTY"
                reasons.append("reply/new-thread or thread-scope collision exists for the same counterparty/provider/purpose")
            else:
                decision = "YIELD_EXISTING"
                reasons.append("related active/terminal route already exists")
            output_record = related
        else:
            created = _new_record(request_obj, 1)
            records.append(created)
            records.sort(key=lambda r: r["fingerprint"])
            existing = created
            output_record = created
            mutation = True
            decision = "CLAIMED"
            reasons.append("new single-writer lease created")
    elif existing is None:
        decision = "YIELD_EXISTING"
        reasons.append("operation requires an existing exact intent lease")
    else:
        output_record = existing
        if existing["state"] == "SENT_TERMINAL":
            decision = "SENT_TERMINAL"
            reasons.append("provider-accepted send is terminal; replay cannot reopen")
        elif operation == "CLAIM":
            if existing["state"] == "RELEASED_UNSENT":
                replacement = _new_record(request_obj, existing["generation"] + 1)
                idx = records.index(existing)
                records[idx] = replacement
                existing = replacement
                output_record = replacement
                mutation = True
                decision = "CLAIMED"
                reasons.append("explicitly released unsent lease reopened at next generation")
            elif _holder(existing, request_obj) and not _lease_expired(existing, now):
                if existing["body_sha256"] == intent["body_sha256"]:
                    decision = existing["state"] if existing["state"] in {"CLAIMED", "WAIT_MUSE", "READY_SINGLE_WRITER"} else "CLAIMED"
                    reasons.append("idempotent same-holder claim")
                elif existing["send_attempt"] is not None:
                    decision = "CLAIMED"
                    reasons.append("changed-body retry blocked because a send attempt already exists")
                else:
                    existing["body_sha256"] = intent["body_sha256"]
                    existing["generation"] += 1
                    existing["muse"] = None
                    existing["state"] = "WAIT_MUSE"
                    existing["lease_expires_at"] = _ts(_dt(now) + timedelta(seconds=request_obj["lease_ttl_seconds"]))
                    existing["updated_at"] = now
                    mutation = True
                    decision = "WAIT_MUSE"
                    reasons.append("body changed; generation advanced and prior Muse evidence invalidated")
            elif not _lease_expired(existing, now):
                decision = "YIELD_EXISTING"
                reasons.append("live lease belongs to another claimant/session")
            elif _pending_or_unknown(existing):
                decision = "YIELD_EXISTING"
                reasons.append("expired holder has unresolved provider send attempt; reconcile before takeover")
            else:
                replacement = _new_record(request_obj, existing["generation"] + 1)
                idx = records.index(existing)
                records[idx] = replacement
                existing = replacement
                output_record = replacement
                mutation = True
                decision = "CLAIMED"
                reasons.append("expired safe lease reclaimed at next generation")
        elif operation == "RECOVER":
            if not _lease_expired(existing, now):
                decision = "YIELD_EXISTING"
                reasons.append("recovery forbidden while prior lease is live")
            else:
                existing["claimant_id"] = request_obj["claimant_id"]
                existing["session_id"] = request_obj["session_id"]
                existing["generation"] += 1
                existing["lease_expires_at"] = _ts(_dt(now) + timedelta(seconds=request_obj["lease_ttl_seconds"]))
                existing["muse"] = None
                existing["state"] = "CLAIMED"
                existing["updated_at"] = now
                mutation = True
                decision = "CLAIMED"
                if _pending_or_unknown(existing):
                    reasons.append("dead-claimant recovery retained unresolved provider attempt; sending remains blocked")
                else:
                    reasons.append("expired claimant recovered at next generation; fresh Muse evidence required")
        elif not _holder(existing, request_obj):
            decision = "YIELD_EXISTING"
            reasons.append("operation caller is not the exact lease holder")
        elif request_obj["generation"] != existing["generation"]:
            decision = "YIELD_EXISTING"
            reasons.append("generation mismatch; stale caller cannot mutate current lease")
        elif operation == "HEARTBEAT":
            if _lease_expired(existing, now):
                decision = "YIELD_EXISTING"
                reasons.append("expired lease must be reclaimed/recovered, not heartbeated")
            else:
                existing["lease_expires_at"] = _ts(_dt(now) + timedelta(seconds=request_obj["lease_ttl_seconds"]))
                existing["updated_at"] = now
                mutation = True
                decision = existing["state"] if existing["state"] in {"CLAIMED", "WAIT_MUSE", "READY_SINGLE_WRITER"} else "CLAIMED"
                reasons.append("lease heartbeat extended")
        elif operation == "APPLY_MUSE":
            muse = request_obj["muse"]
            if _lease_expired(existing, now):
                decision = "WAIT_MUSE"
                reasons.append("lease expired before Muse evidence application")
            elif muse is None:
                decision = "WAIT_MUSE"
                reasons.append("Muse evidence absent")
            else:
                exact = (
                    muse["selected"]
                    and muse["fingerprint"] == existing["fingerprint"]
                    and muse["claimant_id"] == existing["claimant_id"]
                    and muse["session_id"] == existing["session_id"]
                    and muse["generation"] == existing["generation"]
                    and muse["body_sha256"] == existing["body_sha256"]
                    and _dt(muse["expires_at"]) >= _dt(now)
                )
                if not exact:
                    decision = "WAIT_MUSE"
                    reasons.append("Muse evidence is stale, denied, or mismatched to exact lease generation/body")
                elif _pending_or_unknown(existing):
                    decision = "CLAIMED"
                    reasons.append("provider result is unresolved; fresh Muse evidence cannot authorize a retry")
                else:
                    existing["muse"] = muse
                    existing["state"] = "READY_SINGLE_WRITER"
                    existing["updated_at"] = now
                    mutation = True
                    decision = "READY_SINGLE_WRITER"
                    reasons.append("exact retained Muse selection bound to holder, generation, fingerprint, and body")
        elif operation == "RECORD_SEND_ATTEMPT":
            attempt = request_obj["send_attempt"]
            muse = existing["muse"]
            muse_valid = muse is not None and muse["selected"] and _dt(muse["expires_at"]) >= _dt(now)
            if existing["state"] != "READY_SINGLE_WRITER" or not muse_valid:
                decision = "WAIT_MUSE"
                reasons.append("send attempt rejected because lease is not currently READY_SINGLE_WRITER")
            elif attempt is None:
                decision = "READY_SINGLE_WRITER"
                reasons.append("send-attempt evidence absent")
            elif not (
                attempt["fingerprint"] == existing["fingerprint"]
                and attempt["generation"] == existing["generation"]
                and attempt["body_sha256"] == existing["body_sha256"]
            ):
                decision = "READY_SINGLE_WRITER"
                reasons.append("send-attempt evidence mismatches exact lease/generation/body")
            elif existing["send_attempt"] is not None:
                if existing["send_attempt"] == attempt:
                    decision = "CLAIMED"
                    reasons.append("idempotent replay of already-recorded send attempt")
                else:
                    decision = "CLAIMED"
                    reasons.append("second send attempt blocked until first provider outcome is reconciled")
            else:
                existing["send_attempt"] = attempt
                existing["state"] = "CLAIMED"
                existing["updated_at"] = now
                mutation = True
                decision = "CLAIMED"
                reasons.append("send attempt recorded; no retry is ready until provider result is reconciled")
        elif operation == "RECORD_SEND_RESULT":
            result = request_obj["send_result"]
            attempt = existing["send_attempt"]
            if attempt is None:
                decision = "CLAIMED"
                reasons.append("cannot record provider result without an exact prior send attempt")
            elif result is None:
                decision = "CLAIMED"
                reasons.append("send-result evidence absent")
            elif not (
                result["attempt_id"] == attempt["attempt_id"]
                and result["fingerprint"] == existing["fingerprint"]
                and result["generation"] == existing["generation"]
                and result["body_sha256"] == existing["body_sha256"]
            ):
                decision = "CLAIMED"
                reasons.append("provider result mismatches exact attempt/lease/generation/body")
            elif existing["send_result"] is not None and existing["send_result"] != result:
                decision = existing["state"]
                reasons.append("conflicting provider result cannot replace retained result")
            else:
                existing["send_result"] = result
                existing["updated_at"] = now
                mutation = existing["send_result"] == result
                if result["status"] == "ACCEPTED":
                    existing["state"] = "SENT_TERMINAL"
                    decision = "SENT_TERMINAL"
                    reasons.append("provider accepted exact send attempt; intent is terminal")
                elif result["status"] == "REJECTED":
                    existing["state"] = "WAIT_MUSE"
                    existing["muse"] = None
                    decision = "WAIT_MUSE"
                    reasons.append("provider explicitly rejected attempt; any retry requires fresh Muse evidence")
                else:
                    existing["state"] = "CLAIMED"
                    decision = "CLAIMED"
                    reasons.append("provider outcome unknown; fail closed and do not retry")
        elif operation == "RELEASE":
            if _pending_or_unknown(existing):
                decision = "CLAIMED"
                reasons.append("release blocked while provider send outcome is unresolved")
            elif existing["send_result"] and existing["send_result"]["status"] == "ACCEPTED":
                existing["state"] = "SENT_TERMINAL"
                decision = "SENT_TERMINAL"
                reasons.append("accepted send cannot be released into a duplicate lane")
            else:
                existing["state"] = "RELEASED_UNSENT"
                existing["muse"] = None
                existing["updated_at"] = now
                mutation = True
                decision = "RELEASED_UNSENT"
                reasons.append("lease released without accepted send")
        else:
            raise GuardError(f"operation not implemented: {operation}")

    after_obj = {"schema": LEDGER_SCHEMA, "records": sorted(records, key=lambda r: r["fingerprint"])}
    after_raw = canonical_json(after_obj)
    receipt_raw = _receipt(before_raw, request_raw, after_raw, decision, mutation, reasons, output_record)
    return after_raw, receipt_raw


def verify_transition(ledger_raw: bytes, request_raw: bytes, after_raw: bytes, receipt_raw: bytes) -> str:
    expected_after, expected_receipt = transition(ledger_raw, request_raw)
    if bytes(after_raw) != expected_after:
        raise GuardError("transition verify: after ledger mismatch")
    if bytes(receipt_raw) != expected_receipt:
        raise GuardError("transition verify: receipt mismatch")
    receipt = load_json(receipt_raw, "receipt")
    if receipt.get("authority") != authority_flags():
        raise GuardError("transition verify: authority mismatch")
    return "EXACT_OUTBOUND_GUARD_TRANSITION_MATCH"


def _read_regular(path: Path, label: str) -> bytes:
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise GuardError(f"{label}: cannot stat") from exc
    if not stat.S_ISREG(st.st_mode):
        raise GuardError(f"{label}: regular file required")
    if st.st_size > MAX_FILE:
        raise GuardError(f"{label}: file too large")
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise GuardError(f"{label}: file too large")
    st2 = os.lstat(path)
    if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (st2.st_dev, st2.st_ino, st2.st_size, st2.st_mtime_ns):
        raise GuardError(f"{label}: changed during read")
    return raw


def _publish_pair(first: Path, first_raw: bytes, second: Path, second_raw: bytes) -> None:
    if first.parent != second.parent:
        raise GuardError("outputs must share one directory")
    for path in (first, second):
        if os.path.lexists(path):
            raise GuardError(f"output exists: {path}")
    parent = first.parent
    parent.mkdir(parents=True, exist_ok=True)
    temps = []
    created = []
    try:
        for raw in (first_raw, second_raw):
            fd, temp_name = tempfile.mkstemp(prefix=".outbound-guard-", dir=parent)
            temps.append(Path(temp_name))
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        for temp, dest in zip(temps, (first, second)):
            os.link(temp, dest)
            created.append(dest)
    except Exception:
        for dest in created:
            try:
                dest.unlink()
            except OSError:
                pass
        raise
    finally:
        for temp in temps:
            try:
                temp.unlink()
            except OSError:
                pass


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outbound-collision-replay-guard")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_transition = sub.add_parser("transition")
    p_transition.add_argument("ledger")
    p_transition.add_argument("request")
    p_transition.add_argument("--ledger-out", required=True)
    p_transition.add_argument("--receipt", required=True)
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("ledger")
    p_verify.add_argument("request")
    p_verify.add_argument("after")
    p_verify.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "transition":
            ledger = _read_regular(Path(args.ledger), "ledger")
            request = _read_regular(Path(args.request), "request")
            after, receipt = transition(ledger, request)
            _publish_pair(Path(args.ledger_out), after, Path(args.receipt), receipt)
            print(load_json(receipt, "receipt")["decision_state"])
            return 0
        verdict = verify_transition(
            _read_regular(Path(args.ledger), "ledger"),
            _read_regular(Path(args.request), "request"),
            _read_regular(Path(args.after), "after"),
            _read_regular(Path(args.receipt), "receipt"),
        )
        print(verdict)
        return 0
    except GuardError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
