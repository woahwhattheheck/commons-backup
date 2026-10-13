#!/usr/bin/env python3
"""Fail-closed route freshness evidence gate for revenue outreach.

This module never authorizes or performs an outbound send. It compiles
receipt-backed route evidence into one bounded decision that must still pass a
fresh Muse/single-writer census before any external mutation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

INPUT_SCHEMA = "revenue-route-evidence/v1"
OUTPUT_SCHEMA = "revenue-route-freshness-decision/v1"
READY_FOR_MUSE_CENSUS = "READY_FOR_MUSE_CENSUS"
HOLD_STALE_ROUTE = "HOLD_STALE_ROUTE"
HOLD_COMPANY_PRIOR_TOUCH = "HOLD_COMPANY_PRIOR_TOUCH"
HARD_DNR = "HARD_DNR"
DEAD_ROUTE = "DEAD_ROUTE"
DECISIONS = {READY_FOR_MUSE_CENSUS, HOLD_STALE_ROUTE, HOLD_COMPANY_PRIOR_TOUCH, HARD_DNR, DEAD_ROUTE}
ROUTE_KINDS = {"email", "url", "phone", "handle"}
SOURCE_CLASSES = {"FIRST_PARTY", "SECONDARY", "UNKNOWN"}
PROVIDER_KINDS = {"SENT", "DELIVERY_ACCEPTED", "SOFT_DELAY", "HARD_BOUNCE", "HUMAN_REPLY", "AUTO_ACK", "PROPOSAL_SENT"}
OUTBOUND_PROVIDER_KINDS = {"SENT", "DELIVERY_ACCEPTED", "SOFT_DELAY", "PROPOSAL_SENT"}
TOUCH_KINDS = {"OUTBOUND_SENT", "PROPOSAL_SENT", "PRIME_CONTACTED", "BUYER_CONTACTED"}
MUSE_STATUSES = {"CLEAR", "SELECT", "HOLD", "COLLISION"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9]{7,20}$")


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class RouteKey:
    kind: str
    value: str

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.value}"


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise EvidenceError(f"{field} must be a string")
    value = unicodedata.normalize("NFKC", value).strip()
    if not value:
        raise EvidenceError(f"{field} must not be empty")
    return value


def _key_text(value: Any, field: str) -> str:
    return _text(value, field).casefold()


def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise EvidenceError(f"{field} must be a boolean")
    return value


def _int(value: Any, field: str, lo: int, hi: int) -> int:
    if type(value) is not int:  # bool is intentionally rejected
        raise EvidenceError(f"{field} must be an integer")
    if not lo <= value <= hi:
        raise EvidenceError(f"{field} must be between {lo} and {hi}")
    return value


def _parse_ts(value: Any, field: str) -> dt.datetime:
    raw = _text(value, field)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise EvidenceError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _ts_out(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_route(kind: Any, value: Any) -> RouteKey:
    kind_s = _key_text(kind, "route.kind")
    if kind_s not in ROUTE_KINDS:
        raise EvidenceError(f"route.kind must be one of {sorted(ROUTE_KINDS)}")
    raw = _text(value, "route.value")
    if kind_s == "email":
        if not _EMAIL_RE.fullmatch(raw):
            raise EvidenceError("route.value is not a single email address")
        local, domain = raw.rsplit("@", 1)
        if "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise EvidenceError("route.value email domain is malformed")
        value_s = f"{local.casefold()}@{domain.casefold()}"
    elif kind_s == "url":
        parsed = urlsplit(raw)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            raise EvidenceError("route.value URL must use http/https and include a host")
        if parsed.username is not None or parsed.password is not None:
            raise EvidenceError("route.value URL must not contain credentials")
        scheme = parsed.scheme.casefold()
        host = parsed.hostname.casefold()
        try:
            port = parsed.port
        except ValueError as exc:
            raise EvidenceError("route.value URL port is malformed") from exc
        default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        netloc = host if port is None or default else f"{host}:{port}"
        value_s = urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
    elif kind_s == "phone":
        compact = re.sub(r"[\s().-]+", "", raw)
        if not _PHONE_RE.fullmatch(compact):
            raise EvidenceError("route.value phone must contain 7-20 digits with optional leading +")
        value_s = compact
    else:
        value_s = raw.casefold()
    return RouteKey(kind_s, value_s)


def _record_route(record: Mapping[str, Any], prefix: str) -> RouteKey:
    if "route_kind" not in record or "route_value" not in record:
        raise EvidenceError(f"{prefix} requires route_kind and route_value")
    return canonical_route(record["route_kind"], record["route_value"])


def _observed(value: Any, field: str, as_of: dt.datetime) -> dt.datetime:
    parsed = _parse_ts(value, field)
    if parsed > as_of:
        raise EvidenceError(f"{field} must not be in the future relative to as_of")
    return parsed


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def compile_decision(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise EvidenceError("top-level payload must be an object")
    if payload.get("schema") != INPUT_SCHEMA:
        raise EvidenceError(f"schema must equal {INPUT_SCHEMA!r}")

    as_of = _parse_ts(payload.get("as_of"), "as_of")
    max_age = _int(payload.get("max_route_age_days", 30), "max_route_age_days", 1, 365)
    seat = _key_text(payload.get("seat"), "seat")
    buyer = _key_text(payload.get("buyer_scope"), "buyer_scope")
    offer = _key_text(payload.get("offer_key"), "offer_key")
    purpose = _key_text(payload.get("purpose_key"), "purpose_key")

    route_obj = payload.get("route")
    if not isinstance(route_obj, Mapping):
        raise EvidenceError("route must be an object")
    route = canonical_route(route_obj.get("kind"), route_obj.get("value"))
    source_url = canonical_route("url", route_obj.get("source_url")).value
    source_class = _text(route_obj.get("source_class"), "route.source_class").upper()
    if source_class not in SOURCE_CLASSES:
        raise EvidenceError(f"route.source_class must be one of {sorted(SOURCE_CLASSES)}")
    route_observed = _observed(route_obj.get("observed_at"), "route.observed_at", as_of)

    provider_events = payload.get("provider_events", [])
    company_touches = payload.get("company_touches", [])
    dnr_records = payload.get("dnr", [])
    muse_leases = payload.get("muse_leases", [])
    for name, rows in (("provider_events", provider_events), ("company_touches", company_touches), ("dnr", dnr_records), ("muse_leases", muse_leases)):
        if not isinstance(rows, list):
            raise EvidenceError(f"{name} must be an array")

    ids: set[str] = set()
    provider: List[Dict[str, Any]] = []
    touches: List[Dict[str, Any]] = []
    dnrs: List[Dict[str, Any]] = []
    leases: List[Dict[str, Any]] = []

    def take_id(row: Mapping[str, Any], prefix: str) -> str:
        rid = _text(row.get("id"), f"{prefix}.id")
        if rid in ids:
            raise EvidenceError(f"duplicate evidence id: {rid}")
        ids.add(rid)
        return rid

    for i, row in enumerate(provider_events):
        prefix = f"provider_events[{i}]"
        if not isinstance(row, Mapping):
            raise EvidenceError(f"{prefix} must be an object")
        rid = take_id(row, prefix)
        kind = _text(row.get("kind"), f"{prefix}.kind").upper()
        if kind not in PROVIDER_KINDS:
            raise EvidenceError(f"{prefix}.kind unsupported")
        provider.append({
            "id": rid,
            "kind": kind,
            "observed": _observed(row.get("observed_at"), f"{prefix}.observed_at", as_of),
            "route": _record_route(row, prefix),
            "buyer": _key_text(row.get("buyer_scope"), f"{prefix}.buyer_scope"),
        })

    for i, row in enumerate(company_touches):
        prefix = f"company_touches[{i}]"
        if not isinstance(row, Mapping):
            raise EvidenceError(f"{prefix} must be an object")
        rid = take_id(row, prefix)
        kind = _text(row.get("kind"), f"{prefix}.kind").upper()
        if kind not in TOUCH_KINDS:
            raise EvidenceError(f"{prefix}.kind unsupported")
        touches.append({
            "id": rid,
            "kind": kind,
            "observed": _observed(row.get("observed_at"), f"{prefix}.observed_at", as_of),
            "buyer": _key_text(row.get("buyer_scope"), f"{prefix}.buyer_scope"),
            "offer": _key_text(row.get("offer_key"), f"{prefix}.offer_key"),
            "purpose": _key_text(row.get("purpose_key"), f"{prefix}.purpose_key"),
        })

    for i, row in enumerate(dnr_records):
        prefix = f"dnr[{i}]"
        if not isinstance(row, Mapping):
            raise EvidenceError(f"{prefix} must be an object")
        rid = take_id(row, prefix)
        scope = _text(row.get("scope"), f"{prefix}.scope").upper()
        if scope not in {"COMPANY", "EXACT_ROUTE", "BUYER_OFFER_PURPOSE"}:
            raise EvidenceError(f"{prefix}.scope unsupported")
        rec: Dict[str, Any] = {
            "id": rid,
            "active": _bool(row.get("active"), f"{prefix}.active"),
            "scope": scope,
            "buyer": _key_text(row.get("buyer_scope"), f"{prefix}.buyer_scope"),
            "observed": _observed(row.get("observed_at"), f"{prefix}.observed_at", as_of),
        }
        if scope == "EXACT_ROUTE":
            rec["route"] = _record_route(row, prefix)
        if scope == "BUYER_OFFER_PURPOSE":
            rec["offer"] = _key_text(row.get("offer_key"), f"{prefix}.offer_key")
            rec["purpose"] = _key_text(row.get("purpose_key"), f"{prefix}.purpose_key")
        dnrs.append(rec)

    for i, row in enumerate(muse_leases):
        prefix = f"muse_leases[{i}]"
        if not isinstance(row, Mapping):
            raise EvidenceError(f"{prefix} must be an object")
        rid = take_id(row, prefix)
        status = _text(row.get("status"), f"{prefix}.status").upper()
        if status not in MUSE_STATUSES:
            raise EvidenceError(f"{prefix}.status unsupported")
        observed = _observed(row.get("observed_at"), f"{prefix}.observed_at", as_of)
        expires = _parse_ts(row.get("expires_at"), f"{prefix}.expires_at")
        if expires < observed:
            raise EvidenceError(f"{prefix}.expires_at precedes observed_at")
        leases.append({
            "id": rid, "status": status,
            "seat": _key_text(row.get("seat"), f"{prefix}.seat"),
            "buyer": _key_text(row.get("buyer_scope"), f"{prefix}.buyer_scope"),
            "offer": _key_text(row.get("offer_key"), f"{prefix}.offer_key"),
            "purpose": _key_text(row.get("purpose_key"), f"{prefix}.purpose_key"),
            "route": _record_route(row, prefix), "observed": observed, "expires": expires,
        })

    evidence_view = {
        "schema": INPUT_SCHEMA, "as_of": _ts_out(as_of), "max_route_age_days": max_age,
        "seat": seat, "buyer_scope": buyer, "offer_key": offer, "purpose_key": purpose,
        "route": {"key": route.key, "source_url": source_url, "source_class": source_class, "observed_at": _ts_out(route_observed)},
        "provider_events": [{"id": r["id"], "kind": r["kind"], "observed_at": _ts_out(r["observed"]), "route_key": r["route"].key, "buyer_scope": r["buyer"]} for r in provider],
        "company_touches": [{"id": r["id"], "kind": r["kind"], "observed_at": _ts_out(r["observed"]), "buyer_scope": r["buyer"], "offer_key": r["offer"], "purpose_key": r["purpose"]} for r in touches],
        "dnr": [{"id": r["id"], "active": r["active"], "scope": r["scope"], "buyer_scope": r["buyer"], "observed_at": _ts_out(r["observed"]), **({"route_key": r["route"].key} if "route" in r else {}), **({"offer_key": r["offer"], "purpose_key": r["purpose"]} if "offer" in r else {})} for r in dnrs],
        "muse_leases": [{"id": r["id"], "status": r["status"], "seat": r["seat"], "buyer_scope": r["buyer"], "offer_key": r["offer"], "purpose_key": r["purpose"], "route_key": r["route"].key, "observed_at": _ts_out(r["observed"]), "expires_at": _ts_out(r["expires"])} for r in leases],
    }

    decision = READY_FOR_MUSE_CENSUS
    reasons: List[str] = []
    evidence_ids: List[str] = []

    # Explicit DNR has highest authority.
    for rec in dnrs:
        if not rec["active"] or rec["buyer"] != buyer:
            continue
        matches = rec["scope"] == "COMPANY"
        if rec["scope"] == "EXACT_ROUTE":
            matches = rec["route"] == route
        elif rec["scope"] == "BUYER_OFFER_PURPOSE":
            matches = rec["offer"] == offer and rec["purpose"] == purpose
        if matches:
            decision = HARD_DNR
            reasons.append(f"ACTIVE_DNR_{rec['scope']}")
            evidence_ids.append(rec["id"])

    # Permanent provider failure only kills the exact canonical route.
    if decision == READY_FOR_MUSE_CENSUS:
        bounces = [r for r in provider if r["kind"] == "HARD_BOUNCE" and r["route"] == route]
        if bounces:
            decision = DEAD_ROUTE
            reasons.append("EXACT_ROUTE_HARD_BOUNCE")
            evidence_ids.extend(r["id"] for r in bounces)

    # Existing outbound history holds at company scope unless a later genuine
    # human inbound event proves a new event boundary. Auto-acks never release.
    if decision == READY_FOR_MUSE_CENSUS:
        outbound: List[Tuple[dt.datetime, str]] = []
        outbound.extend((r["observed"], r["id"]) for r in provider if r["buyer"] == buyer and r["kind"] in OUTBOUND_PROVIDER_KINDS)
        outbound.extend((r["observed"], r["id"]) for r in touches if r["buyer"] == buyer)
        humans = [r["observed"] for r in provider if r["buyer"] == buyer and r["kind"] == "HUMAN_REPLY"]
        latest_human = max(humans) if humans else None
        blocking = [(when, rid) for when, rid in outbound if latest_human is None or latest_human <= when]
        if blocking:
            decision = HOLD_COMPANY_PRIOR_TOUCH
            reasons.append("COMPANY_PRIOR_TOUCH_WITHOUT_LATER_HUMAN_REPLY")
            evidence_ids.extend(rid for _, rid in blocking)

    # A live exact-key Muse lease is already a single-writer claim. This layer
    # cannot turn CLEAR/SELECT into send permission, even for the same seat.
    if decision == READY_FOR_MUSE_CENSUS:
        live = [r for r in leases if r["buyer"] == buyer and r["offer"] == offer and r["purpose"] == purpose and r["route"] == route and r["expires"] >= as_of]
        if live:
            decision = HOLD_COMPANY_PRIOR_TOUCH
            reasons.extend(f"ACTIVE_MUSE_{status}" for status in sorted({r["status"] for r in live}))
            evidence_ids.extend(r["id"] for r in live)

    # Freshness is computed from timestamp evidence, never a free-form "current" label.
    if decision == READY_FOR_MUSE_CENSUS:
        if source_class != "FIRST_PARTY":
            decision = HOLD_STALE_ROUTE
            reasons.append("NON_FIRST_PARTY_ROUTE_SOURCE")
        elif as_of - route_observed > dt.timedelta(days=max_age):
            decision = HOLD_STALE_ROUTE
            reasons.append("ROUTE_SOURCE_TOO_OLD")

    if decision == HARD_DNR:
        next_step = "STOP_DNR"
    elif decision == DEAD_ROUTE:
        next_step = "DO_NOT_USE_ROUTE_REVERIFY_BEFORE_ANY_ALTERNATE"
    elif decision == HOLD_COMPANY_PRIOR_TOUCH:
        next_step = "WAIT_FOR_GENUINE_EVENT_OR_EXPLICIT_RELEASE_THEN_RECENSUS"
    elif decision == HOLD_STALE_ROUTE:
        next_step = "REFRESH_FIRST_PARTY_ROUTE_EVIDENCE"
    else:
        next_step = "REQUEST_FRESH_MUSE_CENSUS"
        reasons.append("FRESH_FIRST_PARTY_ROUTE_NO_BLOCKING_RECEIPTS")

    result = {
        "schema": OUTPUT_SCHEMA,
        "decision": decision,
        "send_authorized": False,
        "buyer_scope": buyer,
        "offer_key": offer,
        "purpose_key": purpose,
        "route_key": route.key,
        "as_of": _ts_out(as_of),
        "route_observed_at": _ts_out(route_observed),
        "route_source_url": source_url,
        "route_source_class": source_class,
        "max_route_age_days": max_age,
        "reason_codes": reasons,
        "evidence_ids": sorted(set(evidence_ids)),
        "next_step": next_step,
        "input_digest_sha256": _digest(evidence_view),
    }
    if result["decision"] not in DECISIONS or result["send_authorized"] is not False:
        raise RuntimeError("internal fail-closed invariant violated")
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="revenue-route-evidence/v1 JSON file")
    args = parser.parse_args(argv)
    try:
        with open(args.input, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        result = compile_decision(payload)
    except (EvidenceError, OSError, json.JSONDecodeError) as exc:
        print(f"route-evidence-error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
