#!/usr/bin/env python3
"""Deterministic, read-only paid-fulfillment release decision gate.

A release decision is only current for a bounded authority window. Source
freshness is checked against trusted evaluation time, while the release receipt
expires at the earliest of the snapshot TTL or any source freshness deadline.
This prevents an internally coherent historical snapshot from being replayed as
current authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

SCHEMA_VERSION = 1
MAX_EVENTS = 10_000
MAX_AMOUNT_MINOR = 10**15
MAX_FRESHNESS_SECONDS = 7 * 24 * 60 * 60
RELEASE_RECEIPT_TTL_SECONDS = 5 * 60
REQUIRED_SOURCES = (
    "PAYMENT_PROVIDER",
    "OPERATIONS_SYSTEM",
    "ORDER_SYSTEM",
    "FULFILLMENT_SYSTEM",
)
SOURCE_FOR_KIND = {
    "PAYMENT_CAPTURED": "PAYMENT_PROVIDER",
    "PAYMENT_REFUNDED": "PAYMENT_PROVIDER",
    "PAYMENT_CHARGEBACK": "PAYMENT_PROVIDER",
    "FULFILLMENT_READY": "OPERATIONS_SYSTEM",
    "FULFILLMENT_NOT_READY": "OPERATIONS_SYSTEM",
    "ORDER_CANCELLED": "ORDER_SYSTEM",
    "FULFILLMENT_RELEASED": "FULFILLMENT_SYSTEM",
}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GateInputError(ValueError):
    pass


def _no_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateInputError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateInputError(f"cannot read input: {exc}") from exc
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicate_object_keys)
    except (json.JSONDecodeError, GateInputError) as exc:
        raise GateInputError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise GateInputError("top-level JSON value must be an object")
    return value


def _exact(obj: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise GateInputError(f"{where} must be an object")
    missing, extra = sorted(expected - set(obj)), sorted(set(obj) - expected)
    if missing or extra:
        pieces = []
        if missing:
            pieces.append(f"missing={','.join(missing)}")
        if extra:
            pieces.append(f"extra={','.join(extra)}")
        raise GateInputError(f"{where} keys mismatch ({'; '.join(pieces)})")
    return obj


def _stable_id(value: Any, where: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise GateInputError(f"{where} must be a 1-128 character stable identifier")
    return value


def _currency(value: Any, where: str) -> str:
    if not isinstance(value, str) or not CURRENCY_RE.fullmatch(value):
        raise GateInputError(f"{where} must be a three-letter uppercase currency")
    return value


def _integer(value: Any, where: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
        raise GateInputError(f"{where} must be an integer in [{low}, {high}]")
    return value


def _time(value: Any, where: str) -> datetime:
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        raise GateInputError(f"{where} must be an RFC3339 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise GateInputError(f"{where} must be an RFC3339 timestamp") from exc
    return parsed.astimezone(timezone.utc)


def _trusted_time(value: datetime | None, where: str) -> datetime:
    if value is None:
        value = _utcnow()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise GateInputError(f"{where} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ftime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_states(
    raw: Any,
    snapshot_at: datetime,
    evaluated_at: datetime,
    freshness: int,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    source_obj = _exact(raw, set(REQUIRED_SOURCES), "sources")
    states: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for source in REQUIRED_SOURCES:
        item = _exact(
            source_obj[source], {"complete", "observed_at"}, f"sources.{source}"
        )
        if not isinstance(item["complete"], bool):
            raise GateInputError(f"sources.{source}.complete must be boolean")
        observed = _time(item["observed_at"], f"sources.{source}.observed_at")
        if observed > snapshot_at:
            raise GateInputError(f"sources.{source}.observed_at is after snapshot_at")
        snapshot_age = (snapshot_at - observed).total_seconds()
        evaluation_age = (evaluated_at - observed).total_seconds()
        if not item["complete"]:
            blockers.append(f"SOURCE_INCOMPLETE:{source}")
        if evaluation_age >= freshness:
            blockers.append(f"SOURCE_STALE:{source}")
        states[source] = {
            "complete": item["complete"],
            "observed": observed,
            "age": snapshot_age,
            "evaluation_age": evaluation_age,
        }
    return states, blockers


def _event_keys(kind: str) -> set[str]:
    common = {"event_id", "kind", "source", "order_id", "occurred_at"}
    extras = {
        "PAYMENT_CAPTURED": {"payment_id", "amount_minor", "currency"},
        "PAYMENT_REFUNDED": {"payment_id", "refund_id", "amount_minor", "currency"},
        "PAYMENT_CHARGEBACK": {"payment_id", "chargeback_id"},
        "ORDER_CANCELLED": {"cancellation_id"},
        "FULFILLMENT_RELEASED": {"release_id"},
        "FULFILLMENT_READY": set(),
        "FULFILLMENT_NOT_READY": set(),
    }
    if kind not in extras:
        raise GateInputError(f"unsupported event kind: {kind}")
    return common | extras[kind]


def _parse_event(
    raw: Any,
    index: int,
    order_id: str,
    sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    where = f"events[{index}]"
    if not isinstance(raw, dict):
        raise GateInputError(f"{where} must be an object")
    kind = raw.get("kind")
    if kind not in SOURCE_FOR_KIND:
        raise GateInputError(f"{where}.kind is unsupported")
    item = _exact(raw, _event_keys(kind), where)
    event_id = _stable_id(item["event_id"], f"{where}.event_id")
    source = item["source"]
    if source != SOURCE_FOR_KIND[kind]:
        raise GateInputError(
            f"{where}.source must be {SOURCE_FOR_KIND[kind]} for {kind}"
        )
    if _stable_id(item["order_id"], f"{where}.order_id") != order_id:
        raise GateInputError(f"{where}.order_id does not match order.order_id")
    occurred = _time(item["occurred_at"], f"{where}.occurred_at")
    if occurred > sources[source]["observed"]:
        raise GateInputError(f"{where}.occurred_at is newer than its source snapshot")

    data = dict(item)
    data["occurred_at"] = _ftime(occurred)
    for key in (
        "payment_id",
        "refund_id",
        "chargeback_id",
        "cancellation_id",
        "release_id",
    ):
        if key in data:
            data[key] = _stable_id(data[key], f"{where}.{key}")
    if "currency" in data:
        data["currency"] = _currency(data["currency"], f"{where}.currency")
    if "amount_minor" in data:
        data["amount_minor"] = _integer(
            data["amount_minor"], f"{where}.amount_minor", 1, MAX_AMOUNT_MINOR
        )
    return {"id": event_id, "kind": kind, "occurred": occurred, "data": data}


def _dedupe(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_id: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for event in events:
        prior = by_id.get(event["id"])
        if prior is None:
            by_id[event["id"]] = event
        elif prior["data"] != event["data"]:
            raise GateInputError(
                f"event_id reused with different content: {event['id']}"
            )
        else:
            duplicates += 1
    return sorted(by_id.values(), key=lambda e: (e["occurred"], e["id"])), duplicates


def _readiness(
    events: list[dict[str, Any]], at: datetime | None = None
) -> tuple[str, str | None, datetime | None, bool]:
    candidates = [
        e
        for e in events
        if e["kind"] in {"FULFILLMENT_READY", "FULFILLMENT_NOT_READY"}
    ]
    if at is not None:
        candidates = [e for e in candidates if e["occurred"] <= at]
    if not candidates:
        return "UNKNOWN", None, None, False
    latest_time = max(e["occurred"] for e in candidates)
    latest = [e for e in candidates if e["occurred"] == latest_time]
    kinds = {e["kind"] for e in latest}
    if len(kinds) != 1:
        return "UNKNOWN", None, latest_time, True
    chosen = sorted(latest, key=lambda e: e["id"])[-1]
    state = "READY" if chosen["kind"] == "FULFILLMENT_READY" else "NOT_READY"
    return state, chosen["id"], latest_time, False


def evaluate(
    payload: dict[str, Any], *, evaluated_at: datetime | None = None
) -> dict[str, Any]:
    """Evaluate one release snapshot against trusted current time.

    ``evaluated_at`` is an out-of-band authority for deterministic tests and
    trusted adapters. It is never read from the untrusted snapshot payload.
    Production callers should omit it so UTC wall-clock time is used.
    """

    top = _exact(
        payload,
        {
            "schema_version",
            "decision_id",
            "snapshot_at",
            "freshness_window_seconds",
            "order",
            "sources",
            "events",
        },
        "top-level",
    )
    if top["schema_version"] != SCHEMA_VERSION:
        raise GateInputError(f"schema_version must be {SCHEMA_VERSION}")
    decision_id = _stable_id(top["decision_id"], "decision_id")
    snapshot_at = _time(top["snapshot_at"], "snapshot_at")
    evaluation_time = _trusted_time(evaluated_at, "evaluated_at")
    if snapshot_at > evaluation_time:
        raise GateInputError("snapshot_at is after trusted evaluation time")
    snapshot_authority_expires_at = snapshot_at + timedelta(
        seconds=RELEASE_RECEIPT_TTL_SECONDS
    )
    snapshot_age = (evaluation_time - snapshot_at).total_seconds()
    snapshot_expired = evaluation_time >= snapshot_authority_expires_at

    freshness = _integer(
        top["freshness_window_seconds"],
        "freshness_window_seconds",
        1,
        MAX_FRESHNESS_SECONDS,
    )
    order = _exact(
        top["order"],
        {"order_id", "currency", "required_amount_minor"},
        "order",
    )
    order_id = _stable_id(order["order_id"], "order.order_id")
    currency = _currency(order["currency"], "order.currency")
    required = _integer(
        order["required_amount_minor"],
        "order.required_amount_minor",
        1,
        MAX_AMOUNT_MINOR,
    )
    sources, blockers = _source_states(
        top["sources"], snapshot_at, evaluation_time, freshness
    )
    source_authority_expires_at = min(
        state["observed"] + timedelta(seconds=freshness)
        for state in sources.values()
    )
    authority_expires_at = min(
        snapshot_authority_expires_at, source_authority_expires_at
    )
    authority_expired = evaluation_time >= authority_expires_at
    if snapshot_expired:
        blockers.append("SNAPSHOT_EXPIRED")

    if not isinstance(top["events"], list):
        raise GateInputError("events must be an array")
    if len(top["events"]) > MAX_EVENTS:
        raise GateInputError(f"events exceeds maximum of {MAX_EVENTS}")
    parsed = [
        _parse_event(raw, i, order_id, sources)
        for i, raw in enumerate(top["events"])
    ]
    events, duplicate_count = _dedupe(parsed)

    exceptions: list[str] = []
    captures: dict[str, dict[str, Any]] = {}
    refunds: dict[str, dict[str, Any]] = {}
    chargebacks: dict[str, str] = {}
    cancellations: list[dict[str, Any]] = []
    releases: list[dict[str, Any]] = []

    for event in events:
        data, kind = event["data"], event["kind"]
        if kind == "PAYMENT_CAPTURED":
            if data["currency"] != currency:
                exceptions.append(f"PAYMENT_CURRENCY_MISMATCH:{event['id']}")
                continue
            candidate = {
                "amount": data["amount_minor"],
                "currency": data["currency"],
                "occurred": event["occurred"],
            }
            prior = captures.get(data["payment_id"])
            if prior and (prior["amount"], prior["currency"]) != (
                candidate["amount"],
                candidate["currency"],
            ):
                exceptions.append(f"PAYMENT_ID_CONFLICT:{data['payment_id']}")
            elif not prior:
                captures[data["payment_id"]] = candidate
        elif kind == "PAYMENT_REFUNDED":
            if data["currency"] != currency:
                exceptions.append(f"REFUND_CURRENCY_MISMATCH:{event['id']}")
                continue
            candidate = {
                "payment_id": data["payment_id"],
                "amount": data["amount_minor"],
                "currency": data["currency"],
                "occurred": event["occurred"],
            }
            prior = refunds.get(data["refund_id"])
            if prior and (
                prior["payment_id"],
                prior["amount"],
                prior["currency"],
            ) != (
                candidate["payment_id"],
                candidate["amount"],
                candidate["currency"],
            ):
                exceptions.append(f"REFUND_ID_CONFLICT:{data['refund_id']}")
            elif not prior:
                refunds[data["refund_id"]] = candidate
        elif kind == "PAYMENT_CHARGEBACK":
            prior = chargebacks.get(data["chargeback_id"])
            if prior and prior != data["payment_id"]:
                exceptions.append(
                    f"CHARGEBACK_ID_CONFLICT:{data['chargeback_id']}"
                )
            else:
                chargebacks[data["chargeback_id"]] = data["payment_id"]
        elif kind == "ORDER_CANCELLED":
            cancellations.append(event)
        elif kind == "FULFILLMENT_RELEASED":
            releases.append(event)

    for refund_id, refund in refunds.items():
        if refund["payment_id"] not in captures:
            exceptions.append(f"REFUND_WITHOUT_CAPTURE:{refund_id}")
    for chargeback_id, payment_id in chargebacks.items():
        if payment_id not in captures:
            exceptions.append(f"CHARGEBACK_WITHOUT_CAPTURE:{chargeback_id}")
    for payment_id in captures:
        refunded = sum(
            r["amount"]
            for r in refunds.values()
            if r["payment_id"] == payment_id
        )
        if refunded > captures[payment_id]["amount"]:
            exceptions.append(f"REFUND_EXCEEDS_CAPTURE:{payment_id}")

    captured_total = sum(c["amount"] for c in captures.values())
    refunded_total = sum(r["amount"] for r in refunds.values())
    net_paid = captured_total - refunded_total
    readiness, readiness_id, readiness_at, readiness_conflict = _readiness(events)
    if readiness_conflict:
        exceptions.append("READINESS_CONFLICT_AT_SAME_TIME")

    release_ids = sorted({e["data"]["release_id"] for e in releases})
    release_at = min((e["occurred"] for e in releases), default=None)
    if len(release_ids) > 1:
        exceptions.append("MULTIPLE_RELEASE_IDS")
    if refunds:
        exceptions.append("REFUND_PRESENT")
    if chargebacks:
        exceptions.append("CHARGEBACK_PRESENT")
    if cancellations:
        exceptions.append("ORDER_CANCELLED")

    if release_at is not None:
        paid_at_release = sum(
            c["amount"] for c in captures.values() if c["occurred"] <= release_at
        )
        paid_at_release -= sum(
            r["amount"] for r in refunds.values() if r["occurred"] <= release_at
        )
        if paid_at_release < required:
            exceptions.append("RELEASE_WITHOUT_FULL_PAYMENT")
        release_readiness, _, _, release_readiness_conflict = _readiness(
            events, release_at
        )
        if release_readiness_conflict or release_readiness != "READY":
            exceptions.append("RELEASE_WITHOUT_READY_STATE")
        reversed_after = any(
            r["occurred"] > release_at for r in refunds.values()
        )
        reversed_after |= any(e["occurred"] > release_at for e in cancellations)
        reversed_after |= any(
            e["kind"] == "FULFILLMENT_NOT_READY" and e["occurred"] > release_at
            for e in events
        )
        reversed_after |= any(
            e["kind"] == "PAYMENT_CHARGEBACK" and e["occurred"] > release_at
            for e in events
        )
        if reversed_after:
            exceptions.append("POST_RELEASE_REVERSAL")

    if not exceptions:
        if net_paid < required:
            blockers.append("PAYMENT_INSUFFICIENT")
        if readiness == "UNKNOWN":
            blockers.append("FULFILLMENT_READINESS_MISSING")
        elif readiness != "READY":
            blockers.append("FULFILLMENT_NOT_READY")

    exceptions, blockers = sorted(set(exceptions)), sorted(set(blockers))
    if exceptions:
        decision, release_authorized, reasons = (
            "EXCEPTION",
            False,
            exceptions + blockers,
        )
    elif release_ids:
        decision, release_authorized, reasons = (
            "ALREADY_RELEASED",
            False,
            blockers or ["RELEASE_ALREADY_RECORDED"],
        )
    elif blockers:
        decision, release_authorized, reasons = "HOLD", False, blockers
    else:
        decision, release_authorized, reasons = (
            "RELEASE",
            True,
            ["FULL_PAYMENT_AND_READINESS_PROVEN"],
        )

    normalized_events = [e["data"] for e in events]
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "decision_id": decision_id,
        "order_id": order_id,
        "snapshot_at": _ftime(snapshot_at),
        "evaluated_at": _ftime(evaluation_time),
        "authorization": {
            "ttl_seconds": RELEASE_RECEIPT_TTL_SECONDS,
            "expires_at": _ftime(authority_expires_at),
            "snapshot_age_seconds": round(snapshot_age, 6),
            "expired": authority_expired,
        },
        "decision": decision,
        "release_authorized": release_authorized,
        "reasons": reasons,
        "money": {
            "currency": currency,
            "required_amount_minor": required,
            "captured_amount_minor": captured_total,
            "refunded_amount_minor": refunded_total,
            "net_paid_amount_minor": net_paid,
            "payment_ids": sorted(captures),
        },
        "readiness": {
            "state": readiness,
            "event_id": readiness_id,
            "occurred_at": _ftime(readiness_at) if readiness_at else None,
        },
        "release_history": {
            "release_ids": release_ids,
            "first_release_at": _ftime(release_at) if release_at else None,
        },
        "sources": {
            name: {
                "complete": state["complete"],
                "observed_at": _ftime(state["observed"]),
                "age_seconds": round(state["age"], 6),
                "evaluation_age_seconds": round(state["evaluation_age"], 6),
            }
            for name, state in sorted(sources.items())
        },
        "events": {
            "input_count": len(top["events"]),
            "normalized_count": len(normalized_events),
            "deduplicated_count": duplicate_count,
            "sha256": _digest(normalized_events),
        },
    }
    receipt["receipt_sha256"] = _digest(receipt)
    return receipt


def verify_release_receipt(
    receipt: dict[str, Any], *, consumed_at: datetime | None = None
) -> bool:
    """Fail closed unless a trusted gate receipt is still usable for release.

    The SHA-256 field detects accidental/tampered byte-level changes inside a
    trusted channel; it is not a signature and does not authenticate receipt
    origin. Integrations must establish provenance separately and call this
    immediately before the physical fulfillment side effect.
    """

    if not isinstance(receipt, dict):
        raise GateInputError("receipt must be an object")
    expected_digest = receipt.get("receipt_sha256")
    if not isinstance(expected_digest, str) or not SHA256_RE.fullmatch(expected_digest):
        raise GateInputError("receipt_sha256 must be a lowercase SHA-256 digest")
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    if not hmac.compare_digest(_digest(unsigned), expected_digest):
        raise GateInputError("receipt_sha256 does not match receipt content")
    if receipt.get("decision") != "RELEASE" or receipt.get("release_authorized") is not True:
        raise GateInputError("receipt does not authorize release")

    authorization = _exact(
        receipt.get("authorization"),
        {"ttl_seconds", "expires_at", "snapshot_age_seconds", "expired"},
        "receipt.authorization",
    )
    ttl = _integer(
        authorization["ttl_seconds"],
        "receipt.authorization.ttl_seconds",
        RELEASE_RECEIPT_TTL_SECONDS,
        RELEASE_RECEIPT_TTL_SECONDS,
    )
    if authorization["expired"] is not False:
        raise GateInputError("receipt authority was already expired at evaluation")
    snapshot_at = _time(receipt.get("snapshot_at"), "receipt.snapshot_at")
    evaluated = _time(receipt.get("evaluated_at"), "receipt.evaluated_at")
    expires = _time(
        authorization["expires_at"], "receipt.authorization.expires_at"
    )
    if expires > snapshot_at + timedelta(seconds=ttl):
        raise GateInputError("receipt expiry exceeds maximum snapshot authority horizon")
    if expires <= snapshot_at:
        raise GateInputError("receipt expiry is not after snapshot_at")
    if evaluated >= expires:
        raise GateInputError("receipt authority was already expired at evaluation")
    consume_time = _trusted_time(consumed_at, "consumed_at")
    if consume_time < evaluated:
        raise GateInputError("consumed_at is before receipt evaluated_at")
    if consume_time >= expires:
        raise GateInputError("release receipt has expired; re-evaluate current state")
    return True


def _write_atomic(
    output: Path, receipt: dict[str, Any], input_path: Path | None = None
) -> None:
    if output.exists() and output.is_symlink():
        raise GateInputError("output path must not be a symlink")
    output.parent.mkdir(parents=True, exist_ok=True)
    if input_path is not None:
        try:
            aliases = output.exists() and os.path.samefile(input_path, output)
            aliases = aliases or (
                not output.exists() and input_path.resolve() == output.resolve()
            )
            if aliases:
                raise GateInputError("input and output must be different files")
        except FileNotFoundError:
            pass
    encoded = json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", dir=str(output.parent), text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, output)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a paid-fulfillment release snapshot"
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--output", type=Path, help="atomically write the receipt instead of stdout"
    )
    args = parser.parse_args(argv)
    try:
        receipt = evaluate(load_json(args.input))
        if args.output:
            _write_atomic(args.output, receipt, args.input)
        else:
            print(
                json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False)
            )
    except GateInputError as exc:
        parser.exit(2, f"paid-fulfillment-release-gate: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
