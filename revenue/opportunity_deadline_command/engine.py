#!/usr/bin/env python3
"""Deterministic, offline operating calendar for evidence-bound opportunities.

This module is deliberately non-mutating: it validates normalized opportunity/source
records, computes conservative owner-review states, and emits byte-stable projections.
It never contacts a buyer/provider, submits a response, registers for an event, or
asserts award/revenue authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit

INPUT_VERSION = "opportunity-deadline-command-input/v1"
POLICY_VERSION = "opportunity-deadline-command-policy/v1"
RESULT_VERSION = "opportunity-deadline-command-result/v1"

ROUTE_STATES = {"PRIME", "TEAMING", "PARTNER_REQUIRED", "HOLD", "NO_BID", "UNKNOWN"}
PACKET_STATES = {
    "COMPLETE",
    "MISSING_CONTROLLING_PACKET",
    "ADDENDA_UNCHECKED",
    "PARTIAL",
    "NOT_APPLICABLE",
}
SOURCE_AUTHORITIES = {"OFFICIAL", "SECONDARY"}
DEADLINE_KINDS = {
    "QUESTION",
    "CONFERENCE",
    "RESPONSE",
    "MARKET_ENGAGEMENT",
    "REGISTRATION",
    "ADDENDA_CHECK",
}
OPERATING_STATES = {
    "SOURCE_RECOVERY_REQUIRED",
    "ADDENDA_REVIEW_REQUIRED",
    "QUESTION_WINDOW_OPEN",
    "CONFERENCE_ACTION_REVIEW",
    "REGISTRATION_ACTION_REVIEW",
    "RESPONSE_DUE_SOON",
    "RESPONSE_WINDOW_OPEN",
    "NOT_YET_OPEN",
    "EXPIRED",
    "TERMINAL_NO_BID",
    "HOLD",
}
PRIORITIES = {"CRITICAL", "HIGH", "NORMAL", "TERMINAL", "HOLD"}
AUTHORITY_CEILING = (
    "OWNER REVIEW ONLY; NO CONTACT, REGISTRATION, QUESTION, SUBMISSION, SIGNATURE, "
    "PRICING, CONTRACT, SPEND, PAYMENT, AWARD, CASH, OR REVENUE AUTHORITY"
)
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_OPPORTUNITIES = 1000
MAX_SOURCES = 64
MAX_DEADLINES = 32
MAX_LIST_ITEMS = 64
MAX_TEXT = 240
MAX_URL = 1024
SAFE_INTEGER = 9_007_199_254_740_991
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,119}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_TEXT_RE = re.compile(
    r"(?i)(?:\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|\bsk-[A-Za-z0-9_-]{12,}|"
    r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*\S+)"
)
SECRET_QUERY_KEYS = {
    "access_token", "token", "api_key", "apikey", "key", "secret", "client_secret", "password"
}


class EvidenceError(ValueError):
    """Fail-closed validation, verification, or publication error."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EvidenceError(f"non-finite JSON number: {token}")
            ),
        )
    except EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON: {exc.msg}") from exc


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or type(value) in {bool, str, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise EvidenceError(f"{path}: non-finite float")
        return
    if type(value) is list:
        for i, item in enumerate(value):
            _validate_json_value(item, f"{path}[{i}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise EvidenceError(f"{path}: non-string object key")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise EvidenceError(f"{path}: unsupported type {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    _validate_json_value(value, "$")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{path}: expected object")
    return value


def _expect_list(value: Any, path: str, *, max_items: int = MAX_LIST_ITEMS) -> list[Any]:
    if type(value) is not list:
        raise EvidenceError(f"{path}: expected array")
    if len(value) > max_items:
        raise EvidenceError(f"{path}: too many items")
    return value


def _expect_keys(obj: Mapping[str, Any], required: set[str], optional: set[str], path: str) -> None:
    keys = set(obj)
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional)
    if missing:
        raise EvidenceError(f"{path}: missing fields {missing}")
    if unknown:
        raise EvidenceError(f"{path}: unknown fields {unknown}")


def _safe_text(value: Any, path: str, *, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str:
        raise EvidenceError(f"{path}: expected string")
    if not value or value != value.strip():
        raise EvidenceError(f"{path}: empty or surrounding whitespace")
    if len(value) > max_len:
        raise EvidenceError(f"{path}: too long")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise EvidenceError(f"{path}: control character")
    if SECRET_TEXT_RE.search(value):
        raise EvidenceError(f"{path}: secret-shaped text")
    return value


def _identifier(value: Any, path: str) -> str:
    text = _safe_text(value, path, max_len=120)
    if not ID_RE.fullmatch(text):
        raise EvidenceError(f"{path}: unsafe identifier")
    return text


def _sha256(value: Any, path: str) -> str:
    text = _safe_text(value, path, max_len=64)
    if not SHA_RE.fullmatch(text):
        raise EvidenceError(f"{path}: expected lowercase sha256")
    return text


def _positive_int(value: Any, path: str, *, maximum: int = SAFE_INTEGER, allow_zero: bool = False) -> int:
    if type(value) is not int:
        raise EvidenceError(f"{path}: expected integer")
    minimum = 0 if allow_zero else 1
    if value < minimum or value > maximum:
        raise EvidenceError(f"{path}: integer out of range")
    return value


def _bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise EvidenceError(f"{path}: expected boolean")
    return value


def _utc(value: Any, path: str) -> datetime:
    text = _safe_text(value, path, max_len=32)
    if not text.endswith("Z"):
        raise EvidenceError(f"{path}: expected canonical UTC ending Z")
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{path}: invalid UTC instant") from exc
    if dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise EvidenceError(f"{path}: expected UTC")
    canonical = dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if canonical != text:
        raise EvidenceError(f"{path}: expected canonical whole-second UTC")
    return dt


def _utc_text(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _https_url(value: Any, path: str) -> str:
    text = _safe_text(value, path, max_len=MAX_URL)
    parts = urlsplit(text)
    if parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None:
        raise EvidenceError(f"{path}: expected public HTTPS URL without credentials")
    if parts.fragment:
        raise EvidenceError(f"{path}: URL fragments are not accepted")
    for key, _value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SECRET_QUERY_KEYS:
            raise EvidenceError(f"{path}: secret-shaped URL query")
    return text


def _enum(value: Any, allowed: set[str], path: str) -> str:
    text = _safe_text(value, path, max_len=64)
    if text not in allowed:
        raise EvidenceError(f"{path}: unsupported value {text}")
    return text


def _validate_policy(raw: Any) -> dict[str, Any]:
    obj = _expect_dict(raw, "$policy")
    _expect_keys(
        obj,
        {
            "schema_version",
            "max_source_age_minutes",
            "critical_window_minutes",
            "high_window_minutes",
            "addenda_review_window_minutes",
        },
        set(),
        "$policy",
    )
    if obj["schema_version"] != POLICY_VERSION:
        raise EvidenceError("$policy.schema_version: unsupported schema")
    max_age = _positive_int(obj["max_source_age_minutes"], "$policy.max_source_age_minutes")
    critical = _positive_int(obj["critical_window_minutes"], "$policy.critical_window_minutes")
    high = _positive_int(obj["high_window_minutes"], "$policy.high_window_minutes")
    addenda = _positive_int(obj["addenda_review_window_minutes"], "$policy.addenda_review_window_minutes")
    if critical > high:
        raise EvidenceError("$policy: critical_window_minutes must be <= high_window_minutes")
    if high > 525_600 or max_age > 525_600 or addenda > 525_600:
        raise EvidenceError("$policy: minute windows may not exceed one year")
    return {
        "schema_version": POLICY_VERSION,
        "max_source_age_minutes": max_age,
        "critical_window_minutes": critical,
        "high_window_minutes": high,
        "addenda_review_window_minutes": addenda,
    }


def _validate_source(raw: Any, path: str, *, as_of_dt: datetime) -> dict[str, Any]:
    obj = _expect_dict(raw, path)
    _expect_keys(
        obj,
        {"source_id", "authority", "captured_at", "sha256", "url", "label", "generation"},
        set(),
        path,
    )
    source_id = _identifier(obj["source_id"], f"{path}.source_id")
    authority = _enum(obj["authority"], SOURCE_AUTHORITIES, f"{path}.authority")
    captured_dt = _utc(obj["captured_at"], f"{path}.captured_at")
    if captured_dt > as_of_dt:
        raise EvidenceError(f"{path}.captured_at: future source evidence")
    return {
        "source_id": source_id,
        "authority": authority,
        "captured_at": _utc_text(captured_dt),
        "sha256": _sha256(obj["sha256"], f"{path}.sha256"),
        "url": _https_url(obj["url"], f"{path}.url"),
        "label": _safe_text(obj["label"], f"{path}.label", max_len=160),
        "generation": _positive_int(obj["generation"], f"{path}.generation", maximum=1_000_000),
    }


def _validate_deadline(raw: Any, path: str, source_ix: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    obj = _expect_dict(raw, path)
    _expect_keys(
        obj,
        {"deadline_id", "kind", "at", "source_id", "generation"},
        {"opens_at", "supersedes_deadline_id"},
        path,
    )
    deadline_id = _identifier(obj["deadline_id"], f"{path}.deadline_id")
    kind = _enum(obj["kind"], DEADLINE_KINDS, f"{path}.kind")
    at_dt = _utc(obj["at"], f"{path}.at")
    source_id = _identifier(obj["source_id"], f"{path}.source_id")
    if source_id not in source_ix:
        raise EvidenceError(f"{path}.source_id: unknown source")
    generation = _positive_int(obj["generation"], f"{path}.generation", maximum=1_000_000)
    out: dict[str, Any] = {
        "deadline_id": deadline_id,
        "kind": kind,
        "at": _utc_text(at_dt),
        "source_id": source_id,
        "generation": generation,
    }
    if "opens_at" in obj:
        opens_dt = _utc(obj["opens_at"], f"{path}.opens_at")
        if opens_dt > at_dt:
            raise EvidenceError(f"{path}: opens_at must not be after deadline")
        out["opens_at"] = _utc_text(opens_dt)
    if "supersedes_deadline_id" in obj:
        out["supersedes_deadline_id"] = _identifier(
            obj["supersedes_deadline_id"], f"{path}.supersedes_deadline_id"
        )
    return out


def _unique_index(rows: Sequence[dict[str, Any]], key: str, path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = row[key]
        if item in out:
            raise EvidenceError(f"{path}: duplicate {key} {item}")
        out[item] = row
    return out


def _validate_deadline_graph(
    deadlines: Sequence[dict[str, Any]],
    source_ix: Mapping[str, dict[str, Any]],
    path: str,
) -> list[dict[str, Any]]:
    ix = _unique_index(deadlines, "deadline_id", path)
    superseded: set[str] = set()
    for deadline in deadlines:
        prior_id = deadline.get("supersedes_deadline_id")
        if prior_id is None:
            continue
        if prior_id == deadline["deadline_id"] or prior_id not in ix:
            raise EvidenceError(f"{path}: invalid supersedes_deadline_id {prior_id}")
        prior = ix[prior_id]
        if prior["kind"] != deadline["kind"]:
            raise EvidenceError(f"{path}: deadline supersession must preserve kind")
        if deadline["generation"] <= prior["generation"]:
            raise EvidenceError(f"{path}: superseding deadline generation must increase")
        if prior_id in superseded:
            raise EvidenceError(f"{path}: deadline may be superseded by only one direct successor")
        prior_source = source_ix[prior["source_id"]]
        successor_source = source_ix[deadline["source_id"]]
        if successor_source["authority"] != "OFFICIAL":
            raise EvidenceError(f"{path}: superseding deadline must bind OFFICIAL source evidence")
        if successor_source["generation"] <= prior_source["generation"]:
            raise EvidenceError(f"{path}: superseding deadline source generation must increase")
        superseded.add(prior_id)

    effective = [row for row in deadlines if row["deadline_id"] not in superseded]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in effective:
        by_kind.setdefault(row["kind"], []).append(row)
    ambiguous = sorted(kind for kind, rows in by_kind.items() if len(rows) > 1)
    if ambiguous:
        raise EvidenceError(f"{path}: ambiguous effective deadline kinds {ambiguous}")

    response_rows = by_kind.get("RESPONSE", []) + by_kind.get("MARKET_ENGAGEMENT", [])
    if len(response_rows) > 1:
        raise EvidenceError(f"{path}: RESPONSE and MARKET_ENGAGEMENT cannot both be effective")
    if response_rows:
        response_dt = _utc(response_rows[0]["at"], f"{path}.response.at")
        for kind in ("QUESTION", "REGISTRATION", "ADDENDA_CHECK"):
            for row in by_kind.get(kind, []):
                if _utc(row["at"], f"{path}.{kind}.at") > response_dt:
                    raise EvidenceError(f"{path}: {kind} deadline may not follow response deadline")
    return effective


def _normalize_opportunity(raw: Any, i: int, *, as_of_dt: datetime) -> dict[str, Any]:
    path = f"$.opportunities[{i}]"
    obj = _expect_dict(raw, path)
    _expect_keys(
        obj,
        {
            "opportunity_id",
            "buyer",
            "solicitation_id",
            "title",
            "owner_ref",
            "route_state",
            "source_set_complete",
            "controlling_source_id",
            "packet_state",
            "sources",
            "deadlines",
            "blocker_codes",
            "owner_action_refs",
        },
        set(),
        path,
    )
    sources_raw = _expect_list(obj["sources"], f"{path}.sources", max_items=MAX_SOURCES)
    if not sources_raw:
        raise EvidenceError(f"{path}.sources: at least one source required")
    sources = [
        _validate_source(item, f"{path}.sources[{j}]", as_of_dt=as_of_dt)
        for j, item in enumerate(sources_raw)
    ]
    source_ix = _unique_index(sources, "source_id", f"{path}.sources")
    controlling_source_id = _identifier(obj["controlling_source_id"], f"{path}.controlling_source_id")
    if controlling_source_id not in source_ix:
        raise EvidenceError(f"{path}.controlling_source_id: unknown source")

    deadlines_raw = _expect_list(obj["deadlines"], f"{path}.deadlines", max_items=MAX_DEADLINES)
    deadlines = [
        _validate_deadline(item, f"{path}.deadlines[{j}]", source_ix)
        for j, item in enumerate(deadlines_raw)
    ]
    effective = _validate_deadline_graph(deadlines, source_ix, f"{path}.deadlines")

    blockers = [
        _identifier(item, f"{path}.blocker_codes[{j}]")
        for j, item in enumerate(
            _expect_list(obj["blocker_codes"], f"{path}.blocker_codes", max_items=MAX_LIST_ITEMS)
        )
    ]
    if len(set(blockers)) != len(blockers):
        raise EvidenceError(f"{path}.blocker_codes: duplicate code")
    actions = [
        _identifier(item, f"{path}.owner_action_refs[{j}]")
        for j, item in enumerate(
            _expect_list(obj["owner_action_refs"], f"{path}.owner_action_refs", max_items=MAX_LIST_ITEMS)
        )
    ]
    if len(set(actions)) != len(actions):
        raise EvidenceError(f"{path}.owner_action_refs: duplicate ref")

    return {
        "opportunity_id": _identifier(obj["opportunity_id"], f"{path}.opportunity_id"),
        "buyer": _safe_text(obj["buyer"], f"{path}.buyer", max_len=160),
        "solicitation_id": _safe_text(obj["solicitation_id"], f"{path}.solicitation_id", max_len=120),
        "title": _safe_text(obj["title"], f"{path}.title", max_len=200),
        "owner_ref": _identifier(obj["owner_ref"], f"{path}.owner_ref"),
        "route_state": _enum(obj["route_state"], ROUTE_STATES, f"{path}.route_state"),
        "source_set_complete": _bool(obj["source_set_complete"], f"{path}.source_set_complete"),
        "controlling_source_id": controlling_source_id,
        "packet_state": _enum(obj["packet_state"], PACKET_STATES, f"{path}.packet_state"),
        "sources": sorted(sources, key=lambda row: row["source_id"]),
        "deadlines": sorted(deadlines, key=lambda row: row["deadline_id"]),
        "effective_deadlines": sorted(effective, key=lambda row: (row["at"], row["deadline_id"])),
        "blocker_codes": sorted(blockers),
        "owner_action_refs": sorted(actions),
    }


def _normalize_input(raw: Any, *, as_of_dt: datetime) -> dict[str, Any]:
    root = _expect_dict(raw, "$")
    _expect_keys(root, {"schema_version", "opportunities"}, set(), "$")
    if root["schema_version"] != INPUT_VERSION:
        raise EvidenceError("$.schema_version: unsupported schema")
    rows_raw = _expect_list(root["opportunities"], "$.opportunities", max_items=MAX_OPPORTUNITIES)
    rows = [_normalize_opportunity(item, i, as_of_dt=as_of_dt) for i, item in enumerate(rows_raw)]
    _unique_index(rows, "opportunity_id", "$.opportunities")
    return {"schema_version": INPUT_VERSION, "opportunities": sorted(rows, key=lambda row: row["opportunity_id"])}


def _ceil_minutes(seconds: float) -> int:
    if seconds >= 0:
        return int(math.ceil(seconds / 60.0))
    return -int(math.ceil((-seconds) / 60.0))


def _minutes_until(at_text: str, as_of_dt: datetime) -> int:
    return _ceil_minutes((_utc(at_text, "$deadline").timestamp() - as_of_dt.timestamp()))


def _source_age_minutes(source: Mapping[str, Any], as_of_dt: datetime) -> int:
    captured = _utc(source["captured_at"], "$source.captured_at")
    return _ceil_minutes((as_of_dt - captured).total_seconds())


def _priority_for(state: str, remaining: int | None, policy: Mapping[str, Any]) -> str:
    if state in {"HOLD", "SOURCE_RECOVERY_REQUIRED", "ADDENDA_REVIEW_REQUIRED"}:
        return "HOLD"
    if state in {"EXPIRED", "TERMINAL_NO_BID"}:
        return "TERMINAL"
    if remaining is not None and remaining <= policy["critical_window_minutes"]:
        return "CRITICAL"
    if remaining is not None and remaining <= policy["high_window_minutes"]:
        return "HIGH"
    return "NORMAL"


def _classify(op: Mapping[str, Any], policy: Mapping[str, Any], *, as_of_dt: datetime) -> dict[str, Any]:
    source_ix = {row["source_id"]: row for row in op["sources"]}
    effective = list(op["effective_deadlines"])
    controlling = source_ix[op["controlling_source_id"]]

    deadline_projection = []
    for deadline in effective:
        source = source_ix[deadline["source_id"]]
        deadline_projection.append(
            {
                "deadline_id": deadline["deadline_id"],
                "kind": deadline["kind"],
                "at": deadline["at"],
                "opens_at": deadline.get("opens_at"),
                "source_id": deadline["source_id"],
                "source_authority": source["authority"],
                "generation": deadline["generation"],
            }
        )
    deadline_projection.sort(key=lambda row: (row["at"], row["deadline_id"]))

    authoritative_future = [
        row for row in effective
        if source_ix[row["source_id"]]["authority"] == "OFFICIAL"
        and _utc(row["at"], "$deadline.at") > as_of_dt
    ]
    all_future = [row for row in effective if _utc(row["at"], "$deadline.at") > as_of_dt]
    authoritative_future.sort(key=lambda row: (row["at"], row["deadline_id"]))
    all_future.sort(key=lambda row: (row["at"], row["deadline_id"]))

    next_deadline = authoritative_future[0] if authoritative_future else None
    remaining = _minutes_until(next_deadline["at"], as_of_dt) if next_deadline else None

    state: str
    reason_codes: list[str] = []
    if op["route_state"] == "NO_BID":
        state = "TERMINAL_NO_BID"
        reason_codes.append("ROUTE_NO_BID")
    elif op["route_state"] in {"HOLD", "UNKNOWN"}:
        state = "HOLD"
        reason_codes.append("ROUTE_NOT_ACTIONABLE")
    elif not op["source_set_complete"]:
        state = "SOURCE_RECOVERY_REQUIRED"
        reason_codes.append("SOURCE_SET_INCOMPLETE")
    elif controlling["authority"] != "OFFICIAL":
        state = "SOURCE_RECOVERY_REQUIRED"
        reason_codes.append("CONTROLLING_SOURCE_NOT_OFFICIAL")
    elif op["packet_state"] in {"MISSING_CONTROLLING_PACKET", "PARTIAL"}:
        state = "SOURCE_RECOVERY_REQUIRED"
        reason_codes.append(op["packet_state"])
    elif any(source_ix[row["source_id"]]["authority"] != "OFFICIAL" for row in effective):
        state = "SOURCE_RECOVERY_REQUIRED"
        reason_codes.append("DEADLINE_NOT_OFFICIAL")
    else:
        used_source_ids = {op["controlling_source_id"]} | {row["source_id"] for row in effective}
        stale = sorted(
            source_id for source_id in used_source_ids
            if _source_age_minutes(source_ix[source_id], as_of_dt) > policy["max_source_age_minutes"]
        )
        if stale:
            state = "SOURCE_RECOVERY_REQUIRED"
            reason_codes.append("STALE_OFFICIAL_SOURCE")
        elif not effective:
            state = "SOURCE_RECOVERY_REQUIRED"
            reason_codes.append("NO_DECLARED_DEADLINE")
        elif not all_future:
            state = "EXPIRED"
            reason_codes.append("NO_FUTURE_DEADLINE")
        elif next_deadline is None:
            state = "SOURCE_RECOVERY_REQUIRED"
            reason_codes.append("NO_OFFICIAL_FUTURE_DEADLINE")
        else:
            response = next(
                (
                    row for row in effective
                    if row["kind"] in {"RESPONSE", "MARKET_ENGAGEMENT"}
                    and _utc(row["at"], "$response.at") > as_of_dt
                ),
                None,
            )
            response_remaining = _minutes_until(response["at"], as_of_dt) if response else None
            if (
                op["packet_state"] == "ADDENDA_UNCHECKED"
                and response_remaining is not None
                and response_remaining <= policy["addenda_review_window_minutes"]
            ):
                state = "ADDENDA_REVIEW_REQUIRED"
                reason_codes.append("ADDENDA_UNCHECKED_NEAR_RESPONSE")
            elif next_deadline.get("opens_at") is not None and _utc(next_deadline["opens_at"], "$opens_at") > as_of_dt:
                state = "NOT_YET_OPEN"
                reason_codes.append("NEXT_WINDOW_NOT_OPEN")
            elif next_deadline["kind"] == "QUESTION":
                state = "QUESTION_WINDOW_OPEN"
            elif next_deadline["kind"] == "CONFERENCE":
                state = "CONFERENCE_ACTION_REVIEW"
            elif next_deadline["kind"] == "REGISTRATION":
                state = "REGISTRATION_ACTION_REVIEW"
            elif next_deadline["kind"] == "ADDENDA_CHECK":
                state = "ADDENDA_REVIEW_REQUIRED"
            elif next_deadline["kind"] in {"RESPONSE", "MARKET_ENGAGEMENT"}:
                if remaining is not None and remaining <= policy["critical_window_minutes"]:
                    state = "RESPONSE_DUE_SOON"
                else:
                    state = "RESPONSE_WINDOW_OPEN"
            else:
                raise EvidenceError(f"unsupported effective deadline kind: {next_deadline['kind']}")

    if state not in OPERATING_STATES:
        raise EvidenceError(f"internal operating state error: {state}")
    priority = _priority_for(state, remaining, policy)
    if priority not in PRIORITIES:
        raise EvidenceError(f"internal priority error: {priority}")

    next_projection = None
    if next_deadline is not None:
        src = source_ix[next_deadline["source_id"]]
        next_projection = {
            "deadline_id": next_deadline["deadline_id"],
            "kind": next_deadline["kind"],
            "at": next_deadline["at"],
            "minutes_remaining": remaining,
            "source_id": next_deadline["source_id"],
            "source_authority": src["authority"],
            "source_sha256": src["sha256"],
            "source_url": src["url"],
        }

    return {
        "opportunity_id": op["opportunity_id"],
        "buyer": op["buyer"],
        "solicitation_id": op["solicitation_id"],
        "title": op["title"],
        "owner_ref": op["owner_ref"],
        "route_state": op["route_state"],
        "packet_state": op["packet_state"],
        "operating_state": state,
        "priority": priority,
        "reason_codes": sorted(set(reason_codes)),
        "blocker_codes": list(op["blocker_codes"]),
        "owner_action_refs": list(op["owner_action_refs"]),
        "controlling_source": {
            "source_id": controlling["source_id"],
            "authority": controlling["authority"],
            "captured_at": controlling["captured_at"],
            "sha256": controlling["sha256"],
            "url": controlling["url"],
        },
        "next_deadline": next_projection,
        "deadlines": deadline_projection,
    }


def _queue_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    state = row["operating_state"]
    next_at = row["next_deadline"]["at"] if row["next_deadline"] else "9999-12-31T23:59:59Z"
    if state in {"HOLD", "SOURCE_RECOVERY_REQUIRED", "ADDENDA_REVIEW_REQUIRED"}:
        bucket = 0
    elif state not in {"EXPIRED", "TERMINAL_NO_BID"}:
        bucket = 1
    else:
        bucket = 2
    return (bucket, next_at, row["opportunity_id"])


def compile_portfolio(raw_input: Any, raw_policy: Any, *, as_of: str) -> dict[str, Any]:
    as_of_dt = _utc(as_of, "$as_of")
    policy = _validate_policy(raw_policy)
    normalized = _normalize_input(raw_input, as_of_dt=as_of_dt)
    rows = [_classify(op, policy, as_of_dt=as_of_dt) for op in normalized["opportunities"]]
    rows.sort(key=_queue_key)

    counts_by_state: dict[str, int] = {}
    counts_by_priority: dict[str, int] = {}
    for row in rows:
        counts_by_state[row["operating_state"]] = counts_by_state.get(row["operating_state"], 0) + 1
        counts_by_priority[row["priority"]] = counts_by_priority.get(row["priority"], 0) + 1

    manifest_core = {
        "result_version": RESULT_VERSION,
        "as_of": _utc_text(as_of_dt),
        "input_sha256": digest(normalized),
        "policy_sha256": digest(policy),
        "rows_sha256": digest(rows),
        "counts": {
            "total": len(rows),
            "by_state": dict(sorted(counts_by_state.items())),
            "by_priority": dict(sorted(counts_by_priority.items())),
        },
        "authority": {
            "owner_review_only": True,
            "contact_authorized": False,
            "registration_authorized": False,
            "question_authorized": False,
            "submission_authorized": False,
            "signature_authorized": False,
            "pricing_commitment_authorized": False,
            "contract_authorized": False,
            "spend_authorized": False,
            "payment_authorized": False,
            "award_assertion_authorized": False,
            "revenue_recognition_authorized": False,
        },
    }
    manifest = dict(manifest_core)
    manifest["receipt_sha256"] = digest(manifest_core)
    return {"manifest": manifest, "rows": rows}


def verify_result(
    raw_input: Any,
    raw_policy: Any,
    result: Any,
    *,
    current_as_of: str,
) -> bool:
    obj = _expect_dict(result, "$result")
    _expect_keys(obj, {"manifest", "rows"}, set(), "$result")
    manifest = _expect_dict(obj["manifest"], "$result.manifest")
    required_manifest = {
        "result_version", "as_of", "input_sha256", "policy_sha256", "rows_sha256",
        "counts", "authority", "receipt_sha256"
    }
    _expect_keys(manifest, required_manifest, set(), "$result.manifest")
    if manifest["result_version"] != RESULT_VERSION:
        raise EvidenceError("$result.manifest.result_version: unsupported schema")
    original_as_of = _safe_text(manifest["as_of"], "$result.manifest.as_of", max_len=32)
    current_dt = _utc(current_as_of, "$current_as_of")
    original_dt = _utc(original_as_of, "$result.manifest.as_of")
    if original_dt > current_dt:
        raise EvidenceError("result evaluation time is in the future")

    expected = compile_portfolio(raw_input, raw_policy, as_of=original_as_of)
    if canonical_bytes(expected) != canonical_bytes(result):
        raise EvidenceError("result mismatch: inputs/policy/as_of do not reproduce supplied result")

    core = {key: value for key, value in manifest.items() if key != "receipt_sha256"}
    if _sha256(manifest["receipt_sha256"], "$result.manifest.receipt_sha256") != digest(core):
        raise EvidenceError("receipt digest mismatch")

    current = compile_portfolio(raw_input, raw_policy, as_of=_utc_text(current_dt))

    def semantic_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        deadline = row["next_deadline"]
        deadline_key = None if deadline is None else (
            deadline["deadline_id"], deadline["kind"], deadline["at"],
            deadline["source_id"], deadline["source_authority"], deadline["source_sha256"],
        )
        return (row["opportunity_id"], row["operating_state"], row["priority"], deadline_key)

    original_semantics = [semantic_key(row) for row in result["rows"]]
    current_semantics = [semantic_key(row) for row in current["rows"]]
    if original_semantics != current_semantics:
        raise EvidenceError("result is no longer current at trusted verification time")
    return True


def _md(value: Any) -> str:
    if value is None:
        return "—"
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def markdown_projection(result: Mapping[str, Any]) -> str:
    manifest = _expect_dict(result.get("manifest"), "$result.manifest")
    rows = _expect_list(result.get("rows"), "$result.rows", max_items=MAX_OPPORTUNITIES)
    lines = [
        "# Opportunity Deadline Command Center",
        "",
        f"Evaluated: `{_md(manifest['as_of'])}`  ",
        f"Receipt: `{_md(manifest['receipt_sha256'])}`  ",
        f"Authority: **{AUTHORITY_CEILING}**",
        "",
        "| Priority | State | Opportunity | Buyer | Route | Next deadline | Minutes | Owner |",
        "| --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in rows:
        deadline = row.get("next_deadline")
        deadline_text = "—" if deadline is None else f"{deadline['kind']} @ {deadline['at']}"
        minutes = "—" if deadline is None else str(deadline["minutes_remaining"])
        lines.append(
            "| " + " | ".join(
                [
                    _md(row["priority"]),
                    _md(row["operating_state"]),
                    _md(row["opportunity_id"]),
                    _md(row["buyer"]),
                    _md(row["route_state"]),
                    _md(deadline_text),
                    _md(minutes),
                    _md(row["owner_ref"]),
                ]
            ) + " |"
        )
    lines += ["", "Calendar and queue rows are owner-review reminders only; they do not authorize external action.", ""]
    return "\n".join(lines)


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_time(utc_text: str) -> str:
    dt = _utc(utc_text, "$ics.time")
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _ics_fold(line: str) -> str:
    """Fold content lines to 75 UTF-8 octets without splitting a character."""
    parts: list[str] = []
    current: list[str] = []
    octets = 0
    for character in line:
        width = len(character.encode("utf-8"))
        if octets + width > 75:
            parts.append("".join(current))
            current = [" "]
            octets = 1
        current.append(character)
        octets += width
    parts.append("".join(current))
    return "\r\n".join(parts)


def ics_projection(result: Mapping[str, Any]) -> str:
    manifest = _expect_dict(result.get("manifest"), "$result.manifest")
    rows = _expect_list(result.get("rows"), "$result.rows", max_items=MAX_OPPORTUNITIES)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Commons//Opportunity Deadline Command Center//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    dtstamp = _ics_time(manifest["as_of"])
    for row in sorted(rows, key=lambda item: item["opportunity_id"]):
        for deadline in row.get("deadlines", []):
            if deadline["source_authority"] != "OFFICIAL":
                continue
            # There is exactly one effective deadline per kind. Amendments
            # revise that event instead of creating a second calendar entry.
            uid_seed = f"opportunity-deadline-v2|{row['opportunity_id']}|{deadline['kind']}"
            uid = hashlib.sha256(uid_seed.encode("utf-8")).hexdigest() + "@commons.local"
            summary = f"[{deadline['kind']}] {row['buyer']} — {row['solicitation_id']}"
            description = (
                f"Owner review deadline for {row['opportunity_id']}. Source {deadline['source_id']}. "
                + AUTHORITY_CEILING
            )
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"SEQUENCE:{deadline['generation'] - 1}",
                    f"DTSTAMP:{dtstamp}",
                    f"DTSTART:{_ics_time(deadline['at'])}",
                    f"SUMMARY:{_ics_escape(summary)}",
                    f"DESCRIPTION:{_ics_escape(description)}",
                    "TRANSP:TRANSPARENT",
                    "END:VEVENT",
                ]
            )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"


def read_bounded_json(path: str | os.PathLike[str]) -> Any:
    p = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(p, flags)
    except OSError as exc:
        raise EvidenceError(f"cannot open ordinary input file without following symlinks: {p}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise EvidenceError(f"input must be an ordinary regular file: {p}")
        if st.st_size > MAX_FILE_BYTES:
            raise EvidenceError(f"input file exceeds {MAX_FILE_BYTES} bytes: {p}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(64 * 1024, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise EvidenceError(f"input file grew beyond {MAX_FILE_BYTES} bytes: {p}")
        data = b"".join(chunks)
    except EvidenceError:
        raise
    except OSError as exc:
        raise EvidenceError(f"cannot read input file: {p}") from exc
    finally:
        os.close(fd)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"input file is not UTF-8: {p}") from exc
    return loads_strict(text)


def _same_file_identity(path: Path, opened: os.stat_result) -> bool:
    try:
        current = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(current.st_mode)
        and current.st_dev == opened.st_dev
        and current.st_ino == opened.st_ino
    )


def write_new_file(path: str | os.PathLike[str], data: bytes) -> None:
    p = Path(path)
    parent = p.parent
    try:
        parent_st = parent.stat()
    except OSError as exc:
        raise EvidenceError(f"cannot stat output parent: {parent}") from exc
    if not stat.S_ISDIR(parent_st.st_mode):
        raise EvidenceError(f"output parent is not a directory: {parent}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(p, flags, 0o600)
    except OSError as exc:
        raise EvidenceError(f"refusing to overwrite/follow output path: {p}") from exc
    opened = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            if _same_file_identity(p, opened):
                p.unlink(missing_ok=True)
        finally:
            raise


def _system_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _preflight_output_paths(paths: Sequence[str | os.PathLike[str]]) -> None:
    destinations: set[str] = set()
    for value in paths:
        path = Path(value)
        try:
            parent = path.parent.stat()
            if not stat.S_ISDIR(parent.st_mode):
                raise EvidenceError(f"output parent is not a directory: {path.parent}")
            try:
                path.lstat()
            except FileNotFoundError:
                pass
            else:
                raise EvidenceError(f"output path already exists: {path}")
            destination = os.path.normcase(str(path.resolve()))
        except OSError as exc:
            raise EvidenceError(f"cannot prepare output path: {path}: {exc}") from exc
        if destination in destinations:
            raise EvidenceError(f"output paths identify the same destination: {path}")
        destinations.add(destination)


def _command_compile(args: argparse.Namespace) -> int:
    raw_input = read_bounded_json(args.input)
    raw_policy = read_bounded_json(args.policy)
    as_of = _system_now()
    result = compile_portfolio(raw_input, raw_policy, as_of=as_of)
    outputs = [
        (args.json_out, canonical_bytes(result) + b"\n"),
        (args.markdown_out, markdown_projection(result).encode("utf-8")),
        (args.ics_out, ics_projection(result).encode("utf-8")),
    ]
    _preflight_output_paths([path for path, _ in outputs])
    for path, data in outputs:
        write_new_file(path, data)
    print(result["manifest"]["receipt_sha256"])
    return 0


def _command_verify(args: argparse.Namespace) -> int:
    raw_input = read_bounded_json(args.input)
    raw_policy = read_bounded_json(args.policy)
    result = read_bounded_json(args.result)
    verify_result(raw_input, raw_policy, result, current_as_of=_system_now())
    print("verified")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile", help="compile a current owner-review portfolio")
    compile_cmd.add_argument("--input", required=True)
    compile_cmd.add_argument("--policy", required=True)
    compile_cmd.add_argument("--json-out", required=True)
    compile_cmd.add_argument("--markdown-out", required=True)
    compile_cmd.add_argument("--ics-out", required=True)
    compile_cmd.set_defaults(func=_command_compile)

    verify_cmd = sub.add_parser("verify", help="verify exact bytes and current semantics")
    verify_cmd.add_argument("--input", required=True)
    verify_cmd.add_argument("--policy", required=True)
    verify_cmd.add_argument("--result", required=True)
    verify_cmd.set_defaults(func=_command_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (EvidenceError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
