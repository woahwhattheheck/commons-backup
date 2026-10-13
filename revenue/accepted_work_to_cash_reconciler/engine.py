from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from revenue.revenue_funnel_control.engine import (
    FunnelError,
    compile_bundle as compile_funnel_bundle,
    verify_bundle as verify_funnel_bundle,
)

SCHEMA = "TJL_ACCEPTED_WORK_TO_CASH_V1"
BUNDLE_SCHEMA = "TJL_ACCEPTED_WORK_TO_CASH_BUNDLE_V1"
TRUTH_BOUNDARY = "COMPOSED_RETAINED_EVIDENCE_NOT_PROVIDER_AUTHENTICATED"
ROUTE_SOURCE_CLASSES = frozenset(
    {"BUYER_MESSAGE", "SPONSOR_MESSAGE", "PROVIDER_DIRECTORY", "ORGANIZER_RULES"}
)
EXTERNAL_ACCEPTANCE_CLASSES = frozenset({"BUYER_MESSAGE", "SPONSOR_MESSAGE"})
_AUTHORITY_ITEMS = (
    ("external_send", False),
    ("muse_selection", False),
    ("invoice_creation", False),
    ("provider_mutation", False),
    ("payment_movement", False),
    ("receivable_establishment", False),
    ("accounting_assertion", False),
    ("revenue_recognition", False),
)


class ReconcilerError(ValueError):
    pass


def _authority(_items=_AUTHORITY_ITEMS) -> dict[str, bool]:
    return dict(_items)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ReconcilerError(f"not canonical JSON: {exc}") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _exact(value: Any, keys: set[str] | frozenset[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise ReconcilerError(f"{where}: exact object required")
    have, want = set(value), set(keys)
    if have != want:
        raise ReconcilerError(
            f"{where}: exact keys required; missing={sorted(want-have)}; extra={sorted(have-want)}"
        )
    return value


def _text(value: Any, where: str, maximum: int = 512) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise ReconcilerError(f"{where}: bounded nonempty string required")
    if any(ord(ch) < 32 for ch in value):
        raise ReconcilerError(f"{where}: control characters forbidden")
    return value


def _sha(value: Any, where: str) -> str:
    text = _text(value, where, 64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ReconcilerError(f"{where}: lowercase sha256 required")
    return text


def _time(value: Any, where: str) -> datetime:
    if type(value) is not str or not value.endswith("Z") or "." in value:
        raise ReconcilerError(f"{where}: whole-second UTC RFC3339 Z required")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReconcilerError(f"{where}: invalid timestamp") from exc


def _contact_state(events: list[dict[str, Any]]) -> str:
    relevant = [
        e for e in events
        if e.get("kind") in {"INBOUND_RECEIVED", "OUTBOUND_SENT", "DNR", "COLLISION_HOLD"}
    ]
    if not relevant:
        return "NO_ACTIVE_HOLD"
    latest_at = max(e["observed_at"] for e in relevant)
    kinds = {e["kind"] for e in relevant if e["observed_at"] == latest_at}
    # Same-second ordering cannot be recovered from lexical event ids. Holds win.
    if "DNR" in kinds:
        return "HARD_DNR"
    if "COLLISION_HOLD" in kinds:
        return "COLLISION_HOLD"
    if {"INBOUND_RECEIVED", "OUTBOUND_SENT"} <= kinds:
        return "AMBIGUOUS_SAME_TIME_CONTACT"
    if "INBOUND_RECEIVED" in kinds:
        return "NEW_INBOUND"
    if "OUTBOUND_SENT" in kinds:
        return "WAIT_EXTERNAL"
    return "NO_ACTIVE_HOLD"


def _acceptance_basis(events: list[dict[str, Any]]) -> str:
    accepted = [e for e in events if e.get("kind") == "ACCEPTED"]
    if any(e.get("source_class") in EXTERNAL_ACCEPTANCE_CLASSES for e in accepted):
        return "EXTERNAL_ACCEPTANCE_EVIDENCE"
    if accepted:
        return "RETAINED_ACCEPTANCE_NOT_EXTERNAL"
    if any(e.get("kind") == "MERGED" for e in events):
        return "MERGED_WORK_ONLY"
    return "NONE"


def _validate_route(raw: Any, ids: set[str], evaluation_at: datetime) -> dict[str, Any]:
    keys = {
        "opportunity_id", "recipient", "purpose", "observed_at",
        "source_class", "ref", "sha256",
    }
    row = _exact(raw, keys, "route")
    oid = _text(row["opportunity_id"], "route.opportunity_id", 120)
    if oid not in ids:
        raise ReconcilerError(f"route {oid}: unknown opportunity")
    observed = _time(row["observed_at"], f"{oid}.route.observed_at")
    if observed > evaluation_at:
        raise ReconcilerError(f"route {oid}: future evidence")
    source_class = _text(row["source_class"], f"{oid}.route.source_class", 40)
    if source_class not in ROUTE_SOURCE_CLASSES:
        raise ReconcilerError(f"route {oid}: unsupported route source class")
    return {
        "opportunity_id": oid,
        "recipient": _text(row["recipient"], f"{oid}.route.recipient", 320),
        "purpose": _text(row["purpose"], f"{oid}.route.purpose", 320),
        "observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_class": source_class,
        "ref": _text(row["ref"], f"{oid}.route.ref", 512),
        "sha256": _sha(row["sha256"], f"{oid}.route.sha256"),
    }


def _validate_confirmation(
    raw: Any, opportunities: dict[str, dict[str, Any]], evaluation_at: datetime
) -> dict[str, Any]:
    keys = {
        "opportunity_id", "payment_event_id", "observed_at",
        "provider_ref", "provider_sha256",
    }
    row = _exact(raw, keys, "payment_confirmation")
    oid = _text(row["opportunity_id"], "payment_confirmation.opportunity_id", 120)
    if oid not in opportunities:
        raise ReconcilerError(f"payment confirmation {oid}: unknown opportunity")
    event_id = _text(row["payment_event_id"], f"{oid}.payment_event_id", 120)
    payments = {
        e["id"]: e for e in opportunities[oid]["events"] if e["kind"] == "PAYMENT_RECEIVED"
    }
    if event_id not in payments:
        raise ReconcilerError(f"{oid}: confirmation does not bind a PAYMENT_RECEIVED event")
    payment = payments[event_id]
    observed = _time(row["observed_at"], f"{oid}.payment_confirmation.observed_at")
    if observed < _time(payment["observed_at"], f"{oid}.{event_id}.observed_at"):
        raise ReconcilerError(f"{oid}: provider confirmation predates payment event")
    if observed > evaluation_at:
        raise ReconcilerError(f"{oid}: future provider confirmation")
    provider_ref = _text(row["provider_ref"], f"{oid}.provider_ref", 512)
    provider_sha = _sha(row["provider_sha256"], f"{oid}.provider_sha256")
    if provider_ref == payment["ref"] and provider_sha == payment["sha256"]:
        raise ReconcilerError(
            f"{oid}: copied retained payment evidence is not a separate confirmation"
        )
    return {
        "opportunity_id": oid,
        "payment_event_id": event_id,
        "observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provider_ref": provider_ref,
        "provider_sha256": provider_sha,
        "authentication": "RETAINED_ASSERTION_NOT_PROVIDER_AUTHENTICATED",
    }


def _cash_state(
    opportunity: dict[str, Any],
    confirmations: dict[tuple[str, str], dict[str, Any]],
) -> str:
    payments = [e for e in opportunity["events"] if e["kind"] == "PAYMENT_RECEIVED"]
    if not payments:
        return "NO_PAYMENT_EVIDENCE"
    n = sum((opportunity["id"], e["id"]) in confirmations for e in payments)
    if n == len(payments):
        return "RETAINED_CONFIRMATIONS_COMPLETE_UNAUTHENTICATED"
    if n:
        return "RETAINED_CONFIRMATIONS_PARTIAL_UNAUTHENTICATED"
    return "RETAINED_PAYMENT_EVENTS_UNCONFIRMED"


def _public_route(route: dict[str, Any] | None) -> dict[str, Any] | None:
    if route is None:
        return None
    return {key: route[key] for key in (
        "recipient", "purpose", "observed_at", "source_class", "ref", "sha256"
    )}


def _terminal(
    opportunity: dict[str, Any],
    route: dict[str, Any] | None,
    cash_state: str,
) -> tuple[str, str, int]:
    stage = opportunity["stage"]
    contact = _contact_state(opportunity["events"])
    acceptance = _acceptance_basis(opportunity["events"])
    target = opportunity["settlement_target_cents"]

    if stage == "PAID":
        # This generation has no provider-authenticated cash evidence boundary.
        # Retained confirmation assertions can enrich review context but can never
        # turn an upstream retained PAYMENT_RECEIVED assertion into terminal truth.
        return "VERIFY_PROVIDER_CASH", "CASH_EVIDENCE", 0
    if stage in {"OVERPAID_RECONCILE", "PARTIALLY_PAID", "PAYMENT_RECORDED_TARGET_UNKNOWN"}:
        return "RECONCILE_PAYMENT_EVIDENCE", "CASH_EVIDENCE", 0
    if stage == "INVOICED_OR_AWARDED":
        if target == 0:
            return "DONE_ZERO_VALUE", "CLOSED_ZERO_VALUE", 90
        mapping = {
            "NEW_INBOUND": "INBOUND_REVIEW",
            "HARD_DNR": "INBOUND_ONLY",
            "COLLISION_HOLD": "HOLD_COLLISION",
            "AMBIGUOUS_SAME_TIME_CONTACT": "HOLD_CONTACT_AMBIGUITY",
            "WAIT_EXTERNAL": "WAIT_EXTERNAL",
        }
        if contact in mapping:
            return mapping[contact], "SETTLEMENT_INSTRUMENT", 1
        if route is None:
            return "ROUTE_EVIDENCE_REQUIRED", "SETTLEMENT_INSTRUMENT", 1
        return "MUSE_REQUIRED", "SETTLEMENT_INSTRUMENT", 1
    if stage == "ACCEPTED_OR_MERGED":
        if acceptance == "EXTERNAL_ACCEPTANCE_EVIDENCE":
            return "OWNER_INVOICE_PREPARATION_REVIEW", "EXTERNAL_ACCEPTANCE", 2
        return "ACCEPTANCE_EVIDENCE_REQUIRED", "MERGED_OR_UNAUTHENTICATED_ACCEPTANCE", 3
    if stage == "PROPOSED_OR_CLAIMED":
        mapping = {
            "NEW_INBOUND": "INBOUND_REVIEW",
            "HARD_DNR": "INBOUND_ONLY",
            "COLLISION_HOLD": "HOLD_COLLISION",
            "AMBIGUOUS_SAME_TIME_CONTACT": "HOLD_CONTACT_AMBIGUITY",
        }
        return mapping.get(contact, "WAIT_EXTERNAL"), "CLAIM_PENDING", 4
    if stage == "QUALIFIED":
        mapping = {
            "NEW_INBOUND": "INBOUND_REVIEW",
            "HARD_DNR": "INBOUND_ONLY",
            "COLLISION_HOLD": "HOLD_COLLISION",
            "AMBIGUOUS_SAME_TIME_CONTACT": "HOLD_CONTACT_AMBIGUITY",
            "WAIT_EXTERNAL": "WAIT_EXTERNAL",
        }
        if contact in mapping:
            return mapping[contact], "QUALIFIED", 5
        if route is None:
            return "ROUTE_EVIDENCE_REQUIRED", "QUALIFIED", 5
        return "MUSE_REQUIRED", "QUALIFIED", 5
    return "QUALIFICATION_REVIEW", "EARLY_STAGE", 6


def compile_packet(document: Any) -> dict[str, Any]:
    doc = _exact(
        document, {"schema", "funnel_input", "routes", "payment_confirmations"}, "document"
    )
    if doc["schema"] != SCHEMA:
        raise ReconcilerError("document.schema: unsupported")
    try:
        upstream = compile_funnel_bundle(doc["funnel_input"])
    except FunnelError as exc:
        raise ReconcilerError(f"funnel_input: {exc}") from exc
    if not verify_funnel_bundle(upstream):
        raise ReconcilerError("funnel_bundle: semantic verification failed")
    packet = upstream["packet"]
    if type(packet) is not dict:
        raise ReconcilerError("funnel_bundle.packet: object required")
    if packet.get("truth_boundary") != "RETAINED_EVIDENCE_INPUT_NOT_PROVIDER_AUTHENTICATED":
        raise ReconcilerError("funnel_bundle.packet: unexpected truth boundary")
    if packet.get("authority") != {
        "external_send": False, "muse_selection": False, "provider_mutation": False,
        "invoice_creation": False, "payment_movement": False,
        "receivable_establishment": False, "revenue_recognition": False,
    }:
        raise ReconcilerError("funnel_bundle.packet: upstream authority widened")

    evaluation_at = _time(packet.get("evaluation_at"), "funnel.evaluation_at")
    raw_opportunities = packet.get("opportunities")
    if type(raw_opportunities) is not list:
        raise ReconcilerError("funnel.opportunities: array required")
    opportunities: dict[str, dict[str, Any]] = {}
    for opportunity in raw_opportunities:
        if type(opportunity) is not dict:
            raise ReconcilerError("funnel opportunity: object required")
        oid = _text(opportunity.get("id"), "funnel opportunity id", 120)
        if oid in opportunities:
            raise ReconcilerError("funnel: duplicate opportunity id")
        opportunities[oid] = opportunity

    if type(doc["routes"]) is not list:
        raise ReconcilerError("routes: array required")
    routes = [_validate_route(r, set(opportunities), evaluation_at) for r in doc["routes"]]
    route_ids = [r["opportunity_id"] for r in routes]
    if len(route_ids) != len(set(route_ids)):
        raise ReconcilerError("duplicate route for opportunity")
    route_bindings = [(r["source_class"], r["ref"], r["sha256"]) for r in routes]
    if len(route_bindings) != len(set(route_bindings)):
        raise ReconcilerError("duplicate route evidence binding")
    routes.sort(key=lambda r: r["opportunity_id"])
    routes_by_id = {r["opportunity_id"]: r for r in routes}

    if type(doc["payment_confirmations"]) is not list:
        raise ReconcilerError("payment_confirmations: array required")
    confirmations = [
        _validate_confirmation(r, opportunities, evaluation_at)
        for r in doc["payment_confirmations"]
    ]
    keys = [(r["opportunity_id"], r["payment_event_id"]) for r in confirmations]
    if len(keys) != len(set(keys)):
        raise ReconcilerError("duplicate payment confirmation")
    bindings = [(r["provider_ref"], r["provider_sha256"]) for r in confirmations]
    if len(bindings) != len(set(bindings)):
        raise ReconcilerError("duplicate provider confirmation binding")
    confirmations.sort(key=lambda r: (r["opportunity_id"], r["payment_event_id"]))
    confirmations_by_event = {
        (r["opportunity_id"], r["payment_event_id"]): r for r in confirmations
    }

    items: list[dict[str, Any]] = []
    for oid in sorted(opportunities):
        opportunity = opportunities[oid]
        route = _public_route(routes_by_id.get(oid))
        cash_state = _cash_state(opportunity, confirmations_by_event)
        action, band, priority = _terminal(opportunity, route, cash_state)
        item = {
            "opportunity_id": oid,
            "title": opportunity["title"],
            "lane": opportunity["lane"],
            "currency": opportunity["currency"],
            "stage": opportunity["stage"],
            "acceptance_basis": _acceptance_basis(opportunity["events"]),
            "contact_state": _contact_state(opportunity["events"]),
            "cash_state": cash_state,
            "settlement_target_cents": opportunity["settlement_target_cents"],
            "payment_received_cents": opportunity["payment_received_cents"],
            "route": route,
            "terminal_action": action,
            "realizability_band": band,
            "realizability_priority": priority,
            "evidence_root_sha256": _digest({
                "upstream_evidence_root_sha256": opportunity["evidence_root_sha256"],
                "route": route,
                "payment_confirmations": [
                    r for r in confirmations if r["opportunity_id"] == oid
                ],
            }),
            "muse_packet": None,
        }
        if action == "MUSE_REQUIRED":
            if route is None:
                raise ReconcilerError(f"{oid}: MUSE_REQUIRED without route")
            item["muse_packet"] = {
                "recipient": route["recipient"],
                "purpose": route["purpose"],
                "authority": "REQUEST_ARBITRATION_ONLY_NOT_SEND_AUTHORITY",
            }
        items.append(item)

    open_queue = [
        item["opportunity_id"]
        for item in sorted(
            (i for i in items if not i["terminal_action"].startswith("DONE_")),
            key=lambda i: (i["realizability_priority"], i["opportunity_id"]),
        )
    ]
    counts: dict[str, int] = {}
    for item in items:
        counts[item["terminal_action"]] = counts.get(item["terminal_action"], 0) + 1
    return {
        "schema": SCHEMA,
        "evaluation_at": evaluation_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "truth_boundary": TRUTH_BOUNDARY,
        "upstream_funnel_bundle_sha256": _digest(upstream),
        "authority": _authority(),
        "items": items,
        "open_queue": open_queue,
        "summary": {
            "item_count": len(items),
            "open_count": len(open_queue),
            "terminal_action_counts": dict(sorted(counts.items())),
            "queue_uses_headline_amount": False,
            "live_provider_query_performed": False,
            "provider_confirmation_is_retained_evidence_not_authentication": True,
            "provider_authenticated_payment_evidence_available": False,
            "terminal_paid_requires_provider_authenticated_evidence": True,
        },
    }


def compile_bundle(document: Any) -> dict[str, Any]:
    packet = compile_packet(document)
    normalized = json.loads(_canonical(document).decode("utf-8"))
    return {
        "schema": BUNDLE_SCHEMA,
        "input": normalized,
        "packet": packet,
        "receipt": {
            "schema": BUNDLE_SCHEMA,
            "input_sha256": _digest(normalized),
            "packet_sha256": _digest(packet),
            "authority": _authority(),
        },
    }


def verify_bundle(bundle: Any) -> bool:
    if type(bundle) is not dict or set(bundle) != {"schema", "input", "packet", "receipt"}:
        return False
    if any(type(k) is not str for k in bundle) or bundle.get("schema") != BUNDLE_SCHEMA:
        return False
    receipt = bundle.get("receipt")
    if type(receipt) is not dict or set(receipt) != {
        "schema", "input_sha256", "packet_sha256", "authority"
    }:
        return False
    if receipt.get("schema") != BUNDLE_SCHEMA or receipt.get("authority") != _authority():
        return False
    try:
        return _canonical(compile_bundle(bundle["input"])) == _canonical(bundle)
    except (ReconcilerError, KeyError, TypeError):
        return False


def load_json_strict(path: Path, limit: int = 8_000_000) -> Any:
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
        raise ReconcilerError("input must be a bounded regular file")
    flags = os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ReconcilerError("input changed or is not regular")
        if (st.st_dev, st.st_ino, st.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise ReconcilerError("input changed before retained read")
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(fd, min(131072, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        if len(raw) > limit or len(raw) != before.st_size:
            raise ReconcilerError("input exceeds bound or changed")
        if (before.st_dev, before.st_ino, before.st_size) != (
            after.st_dev, after.st_ino, after.st_size
        ):
            raise ReconcilerError("input changed while reading")
    finally:
        os.close(fd)

    def reject_constant(value: str) -> None:
        raise ReconcilerError(f"non-finite JSON constant: {value}")

    def reject_float(value: str) -> None:
        raise ReconcilerError(f"floating JSON number forbidden: {value}")

    def bounded_int(value: str) -> int:
        digits = value[1:] if value.startswith("-") else value
        if len(digits) > 18:
            raise ReconcilerError("JSON integer exceeds bound")
        return int(value)

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReconcilerError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_float=reject_float,
            parse_int=bounded_int,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReconcilerError(f"invalid strict JSON: {exc}") from exc


def _publish_exclusive(path: Path, value: Any) -> None:
    payload = _canonical(value) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(fd, payload[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Accepted-work-to-cash reconciler")
    sub = parser.add_subparsers(dest="command", required=True)
    comp = sub.add_parser("compile")
    comp.add_argument("input", type=Path)
    comp.add_argument("output", type=Path)
    ver = sub.add_parser("verify")
    ver.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            _publish_exclusive(args.output, compile_bundle(load_json_strict(args.input)))
            return 0
        if not verify_bundle(load_json_strict(args.bundle)):
            raise ReconcilerError("bundle verification failed")
        return 0
    except (OSError, ReconcilerError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
