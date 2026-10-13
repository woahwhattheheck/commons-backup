#!/usr/bin/env python3
"""Deterministic buyer-neutral revenue route freshness proof gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PRODUCT = "revenue/route_freshness_gate"
OPERATION = "REVENUE-ROUTE-FRESHNESS-PROOF-GATE-ZQFV6R9-20260916"
DECISIONS = ("HARD_DNR", "DEAD_ROUTE", "HOLD_PROVIDER_AMBIGUOUS", "HOLD_COMPANY_PRIOR_TOUCH", "HOLD_STALE_ROUTE", "READY_FOR_MUSE_CENSUS")
PROVIDER_KINDS = ("SENT", "DELIVERED", "BOUNCE", "AMBIGUOUS", "AUTO_ACK", "HUMAN_REPLY", "HARD_DNR")
HUMAN_KINDS = frozenset({"HUMAN_REPLY"})
TERMINAL_RESOLVERS = frozenset({"BOUNCE", "HARD_DNR", "HUMAN_REPLY", "DELIVERED", "SENT"})
SOURCE_AUTHORITY = frozenset({"PRIMARY_SYSTEM", "PROVIDER_RECEIPT", "OPERATOR_RETAINED"})
ROUTE_KINDS = frozenset({"EMAIL", "PHONE", "PORTAL", "FORM", "OTHER"})
ROUTE_STATES = frozenset({"LIVE", "DEAD", "EXPIRED", "UNKNOWN"})
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
CONTACTISH_RE = re.compile(r"(?i)(@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|sk-[A-Za-z0-9]{8,}|\+\d{8,}|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)")
TOP_KEYS = {"schema_version", "evaluated_at", "organization_digest", "route", "source", "provider_history", "company_prior_touches", "muse_receipt_digest"}
ROUTE_KEYS = {"route_identity_digest", "route_kind", "route_state", "purpose_generation_digest", "alias_digests"}
SOURCE_KEYS = {"authority_class", "observed_at", "current_through", "source_digest"}
EVENT_KEYS = {"event_id", "kind", "occurred_at", "event_digest", "resolves_event_id", "purpose_generation_digest", "route_identity_digest"}
TOUCH_KEYS = {"touch_id", "occurred_at", "touch_digest", "route_identity_digest", "purpose_generation_digest", "current"}
AUTHORITY_FALSE = {"send_authorized": False, "provider_authorized": False, "contact_authorized": False, "payment_authorized": False, "revenue_authorized": False, "muse_election_requested": False}

class GateInputError(ValueError):
    pass

def _no_duplicate_object_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise GateInputError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out

def parse_json_text(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicate_object_keys)
    except (json.JSONDecodeError, GateInputError) as exc:
        raise GateInputError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise GateInputError("top-level JSON value must be an object")
    return value

def load_json(path: Path):
    try:
        return parse_json_text(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GateInputError(f"cannot read input: {exc}") from exc

def _exact(obj, expected, where):
    if not isinstance(obj, dict):
        raise GateInputError(f"{where} must be an object")
    missing, extra = sorted(expected - set(obj)), sorted(set(obj) - expected)
    if missing or extra:
        bits = []
        if missing:
            bits.append("missing=" + ",".join(missing))
        if extra:
            bits.append("extra=" + ",".join(extra))
        raise GateInputError(f"{where} keys mismatch ({'; '.join(bits)})")
    return obj

def _forbid_contactish(value, where):
    if CONTACTISH_RE.search(value):
        raise GateInputError(f"{where} must not contain raw contact/secret text")

def _stable_id(value, where):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise GateInputError(f"{where} must be a 1-128 character stable identifier")
    _forbid_contactish(value, where)
    return value

def _digest(value, where):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise GateInputError(f"{where} must be a lowercase sha256 hex digest")
    return value

def _optional_digest(value, where):
    return None if value is None else _digest(value, where)

def _optional_id(value, where):
    return None if value is None else _stable_id(value, where)

def _enum(value, allowed, where):
    if not isinstance(value, str) or value not in allowed:
        raise GateInputError(f"{where} must be one of {sorted(allowed)}")
    return value

def _bool(value, where):
    if not isinstance(value, bool):
        raise GateInputError(f"{where} must be a JSON boolean")
    return value

def _time(value, where):
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        raise GateInputError(f"{where} must be an RFC3339 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(candidate).astimezone(timezone.utc)
    except ValueError as exc:
        raise GateInputError(f"{where} must be an RFC3339 timestamp") from exc

def _canonical_dumps(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _parse_event(raw, index):
    obj = _exact(raw, EVENT_KEYS, f"provider_history[{index}]")
    return {
        "event_id": _stable_id(obj["event_id"], f"provider_history[{index}].event_id"),
        "kind": _enum(obj["kind"], PROVIDER_KINDS, f"provider_history[{index}].kind"),
        "occurred_at": _time(obj["occurred_at"], f"provider_history[{index}].occurred_at"),
        "occurred_at_raw": obj["occurred_at"],
        "event_digest": _digest(obj["event_digest"], f"provider_history[{index}].event_digest"),
        "resolves_event_id": _optional_id(obj["resolves_event_id"], f"provider_history[{index}].resolves_event_id"),
        "purpose_generation_digest": _digest(obj["purpose_generation_digest"], f"provider_history[{index}].purpose_generation_digest"),
        "route_identity_digest": _digest(obj["route_identity_digest"], f"provider_history[{index}].route_identity_digest"),
    }

def _parse_touch(raw, index):
    obj = _exact(raw, TOUCH_KEYS, f"company_prior_touches[{index}]")
    return {
        "touch_id": _stable_id(obj["touch_id"], f"company_prior_touches[{index}].touch_id"),
        "occurred_at": _time(obj["occurred_at"], f"company_prior_touches[{index}].occurred_at"),
        "occurred_at_raw": obj["occurred_at"],
        "touch_digest": _digest(obj["touch_digest"], f"company_prior_touches[{index}].touch_digest"),
        "route_identity_digest": _digest(obj["route_identity_digest"], f"company_prior_touches[{index}].route_identity_digest"),
        "purpose_generation_digest": _digest(obj["purpose_generation_digest"], f"company_prior_touches[{index}].purpose_generation_digest"),
        "current": _bool(obj["current"], f"company_prior_touches[{index}].current"),
    }

def _collapse_by_id(items, id_key, digest_key, label):
    seen = {}
    order = []
    for item in items:
        ident = item[id_key]
        if ident in seen:
            prev = seen[ident]
            if prev[digest_key] != item[digest_key] or prev["occurred_at_raw"] != item["occurred_at_raw"] or prev.get("kind") != item.get("kind"):
                raise GateInputError(f"{label} id {ident} conflicts across retained bytes")
            continue
        seen[ident] = item
        order.append(ident)
    return [seen[i] for i in order]

def compile_packet(raw, *, historical=False):
    obj = _exact(raw, TOP_KEYS, "packet")
    if isinstance(obj["schema_version"], bool) or obj["schema_version"] != SCHEMA_VERSION:
        raise GateInputError("schema_version must be integer 1")
    evaluated_at = _time(obj["evaluated_at"], "evaluated_at")
    organization_digest = _digest(obj["organization_digest"], "organization_digest")
    route_obj = _exact(obj["route"], ROUTE_KEYS, "route")
    source_obj = _exact(obj["source"], SOURCE_KEYS, "source")
    if not isinstance(obj["provider_history"], list):
        raise GateInputError("provider_history must be an array")
    if not isinstance(obj["company_prior_touches"], list):
        raise GateInputError("company_prior_touches must be an array")
    route = {
        "route_identity_digest": _digest(route_obj["route_identity_digest"], "route.route_identity_digest"),
        "route_kind": _enum(route_obj["route_kind"], ROUTE_KINDS, "route.route_kind"),
        "route_state": _enum(route_obj["route_state"], ROUTE_STATES, "route.route_state"),
        "purpose_generation_digest": _digest(route_obj["purpose_generation_digest"], "route.purpose_generation_digest"),
        "alias_digests": [],
    }
    if not isinstance(route_obj["alias_digests"], list):
        raise GateInputError("route.alias_digests must be an array")
    aliases = []
    seen_alias = set()
    for i, alias in enumerate(route_obj["alias_digests"]):
        digest = _digest(alias, f"route.alias_digests[{i}]")
        if digest not in seen_alias:
            aliases.append(digest)
            seen_alias.add(digest)
    route["alias_digests"] = aliases
    source = {
        "authority_class": _enum(source_obj["authority_class"], SOURCE_AUTHORITY, "source.authority_class"),
        "observed_at": _time(source_obj["observed_at"], "source.observed_at"),
        "current_through": _time(source_obj["current_through"], "source.current_through"),
        "source_digest": _digest(source_obj["source_digest"], "source.source_digest"),
    }
    events = _collapse_by_id([_parse_event(item, i) for i, item in enumerate(obj["provider_history"])], "event_id", "event_digest", "provider_history")
    touches = _collapse_by_id([_parse_touch(item, i) for i, item in enumerate(obj["company_prior_touches"])], "touch_id", "touch_digest", "company_prior_touches")
    muse_receipt_digest = _optional_digest(obj["muse_receipt_digest"], "muse_receipt_digest")
    for item in events:
        if item["occurred_at"] > evaluated_at:
            raise GateInputError(f"future provider event {item['event_id']}")
    for item in touches:
        if item["occurred_at"] > evaluated_at:
            raise GateInputError(f"future company prior touch {item['touch_id']}")
    if source["observed_at"] > evaluated_at or source["current_through"] > evaluated_at:
        raise GateInputError("future source timestamps")
    if source["observed_at"] > source["current_through"]:
        raise GateInputError("source observed_at after current_through")
    route_ids = {route["route_identity_digest"], *route["alias_digests"]}
    reasons = []
    decision = "READY_FOR_MUSE_CENSUS"
    if any(e["kind"] == "HARD_DNR" and e["route_identity_digest"] in route_ids for e in events):
        decision = "HARD_DNR"
        reasons.append("retained HARD_DNR event present on current route lineage")
    if decision == "READY_FOR_MUSE_CENSUS":
        bounce = [e for e in events if e["kind"] == "BOUNCE" and e["route_identity_digest"] in route_ids]
        if route["route_state"] == "DEAD" or bounce:
            decision = "DEAD_ROUTE"
            if route["route_state"] == "DEAD":
                reasons.append("route_state is DEAD")
            if bounce:
                reasons.append("provider history contains hard bounce")
    if decision == "READY_FOR_MUSE_CENSUS":
        unresolved = []
        for e in events:
            if e["kind"] != "AMBIGUOUS" or e["route_identity_digest"] not in route_ids:
                continue
            resolved = False
            for later in events:
                if later["event_id"] == e["event_id"] or later["occurred_at"] <= e["occurred_at"]:
                    continue
                if later["resolves_event_id"] == e["event_id"] and later["kind"] in TERMINAL_RESOLVERS:
                    resolved = True
                    break
            if not resolved:
                unresolved.append(e["event_id"])
        if unresolved:
            decision = "HOLD_PROVIDER_AMBIGUOUS"
            reasons.append("unresolved AMBIGUOUS provider history: " + ",".join(sorted(unresolved)))
    if decision == "READY_FOR_MUSE_CENSUS":
        blocking = []
        for touch in touches:
            if not touch["current"] or touch["route_identity_digest"] in route_ids:
                continue
            reopened = any(
                e["kind"] in HUMAN_KINDS and e["purpose_generation_digest"] == route["purpose_generation_digest"] and e["route_identity_digest"] in route_ids and e["occurred_at"] >= touch["occurred_at"]
                for e in events
            )
            if not reopened:
                blocking.append(touch["touch_id"])
        if blocking:
            decision = "HOLD_COMPANY_PRIOR_TOUCH"
            reasons.append("current company-level prior touch on another route: " + ",".join(sorted(blocking)))
    if decision == "READY_FOR_MUSE_CENSUS":
        stale = []
        if route["route_state"] in {"EXPIRED", "UNKNOWN"}:
            stale.append("route_state=" + route["route_state"])
        if source["current_through"] < evaluated_at:
            stale.append("source current_through is behind evaluated_at")
        latest_event = max((e["occurred_at"] for e in events), default=None)
        if latest_event is not None and latest_event > source["current_through"]:
            stale.append("provider event after source current_through")
        if stale:
            decision = "HOLD_STALE_ROUTE"
            reasons.extend(stale)
    if historical:
        if decision == "READY_FOR_MUSE_CENSUS":
            decision = "HOLD_STALE_ROUTE"
            reasons.append("historical evaluator cannot mint current readiness")
        else:
            reasons.append("historical evaluator is integrity-only")
    if muse_receipt_digest and decision != "READY_FOR_MUSE_CENSUS":
        reasons.append("muse_receipt_digest is trace metadata only and does not promote HOLD")
    if not reasons and decision == "READY_FOR_MUSE_CENSUS":
        reasons.append("no blocking predecessor in retained evidence")
    packet = {
        "product": PRODUCT,
        "operation": OPERATION,
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "reasons": reasons,
        "organization_digest": organization_digest,
        "route_identity_digest": route["route_identity_digest"],
        "route_kind": route["route_kind"],
        "purpose_generation_digest": route["purpose_generation_digest"],
        "evaluated_at": obj["evaluated_at"],
        "source_digest": source["source_digest"],
        "muse_receipt_digest": muse_receipt_digest,
        "historical": historical,
        "event_ids": [e["event_id"] for e in sorted(events, key=lambda x: (x["occurred_at_raw"], x["event_id"]))],
        "touch_ids": [t["touch_id"] for t in sorted(touches, key=lambda x: (x["occurred_at_raw"], x["touch_id"]))],
        **AUTHORITY_FALSE,
    }
    packet["packet_digest"] = _sha256_text(_canonical_dumps({k: v for k, v in packet.items() if k != "packet_digest"}))
    return packet

def render_markdown(packet):
    lines = ["# Route freshness proof", "", f"- product: `{packet['product']}`", f"- operation: `{packet['operation']}`", f"- decision: `{packet['decision']}`", f"- packet_digest: `{packet['packet_digest']}`", f"- evaluated_at: `{packet['evaluated_at']}`", f"- organization_digest: `{packet['organization_digest']}`", f"- route_identity_digest: `{packet['route_identity_digest']}`", f"- historical: `{str(packet['historical']).lower()}`", "", "## Reasons"]
    lines.extend(f"- {reason}" for reason in packet["reasons"])
    lines.extend(["", "## Authority ceiling", "- send_authorized: false", "- provider_authorized: false", "- contact_authorized: false", "- payment_authorized: false", "- revenue_authorized: false", "- muse_election_requested: false", ""])
    return "\n".join(lines)

def verify_packet(packet):
    if not isinstance(packet, dict):
        raise GateInputError("receipt must be an object")
    expected = dict(packet)
    digest = expected.pop("packet_digest", None)
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise GateInputError("packet_digest missing or malformed")
    if _sha256_text(_canonical_dumps(expected)) != digest:
        raise GateInputError("packet digest mismatch")
    if packet.get("decision") not in DECISIONS:
        raise GateInputError("unknown decision")
    for key, value in AUTHORITY_FALSE.items():
        if packet.get(key) is not value:
            raise GateInputError(f"{key} must remain false")

def main(argv=None):
    parser = argparse.ArgumentParser(prog="route_freshness_gate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("--input", required=True, type=Path)
    c.add_argument("--output", required=True, type=Path)
    c.add_argument("--markdown", type=Path, default=None)
    c.add_argument("--historical", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("--input", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "compile":
            packet = compile_packet(load_json(args.input), historical=args.historical)
            args.output.write_text(_canonical_dumps(packet) + "\n", encoding="utf-8")
            if args.markdown:
                args.markdown.write_text(render_markdown(packet), encoding="utf-8")
            print(packet["decision"])
            print(packet["packet_digest"])
            return 0
        raw = load_json(args.input)
        verify_packet(raw)
        print("OK")
        print(raw["packet_digest"])
        return 0
    except GateInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
