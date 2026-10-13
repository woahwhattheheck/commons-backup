#!/usr/bin/env python3
"""Verify and normalize Stripe webhook events for the Commons checkout projector.

The bridge is deliberately transport-neutral.  An HTTPS runtime supplies the
exact raw request body, the Stripe-Signature header, and the endpoint signing
secret.  This module verifies provenance before JSON parsing and emits only a
public-safe Commons observation.  It never creates a charge, calls Stripe,
writes CRM data, or claims that provider funds reached a bank.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import tempfile
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from checkout_handoff import (
    HandoffError,
    build_checkout_envelope,
    load_json,
    payment_projection,
    validate_request,
)


DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "revenue" / "outcome_commerce" / "catalog.json"
DEFAULT_SECRET_ENV = "STRIPE_WEBHOOK_SECRET"
DEFAULT_SIGNATURE_ENV = "STRIPE_SIGNATURE_HEADER"
DEFAULT_TOLERANCE_SECONDS = 300
HEX_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,120}$")

SUPPORTED_EVENT_TYPES = {
    "checkout.session.completed",
    "payment_intent.succeeded",
    "charge.succeeded",
    "charge.refunded",
}

METADATA_BINDINGS = {
    "commons_request_id": ("request_id",),
    "commons_crm_record": ("crm", "record_id"),
    "commons_sku_id": ("sku_id",),
    "commons_acceptance_sha256": ("acceptance_digest",),
}


class BridgeError(ValueError):
    """A public-safe verification or normalization failure."""


def _request_value(request: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = request
    for key in path:
        value = value[key]
    return value


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BridgeError("payload JSON contains duplicate object keys")
        result[key] = value
    return result


def _reject_float(value: str) -> Any:
    raise BridgeError("payload JSON numbers must not use floating point: %s" % value)


def parse_signature_header(header: str) -> tuple[int, list[str]]:
    """Return the one Stripe timestamp and all valid v1 signature candidates."""
    if not isinstance(header, str) or not header.strip():
        raise BridgeError("Stripe-Signature header is missing")
    timestamps: list[str] = []
    signatures: list[str] = []
    for item in header.split(","):
        key, separator, value = item.strip().partition("=")
        if not separator:
            raise BridgeError("Stripe-Signature header is malformed")
        if key == "t":
            timestamps.append(value)
        elif key == "v1":
            signatures.append(value)
    if len(timestamps) != 1 or not timestamps[0].isdigit():
        raise BridgeError("Stripe-Signature header must contain one timestamp")
    if not signatures or any(not HEX_SHA256_RE.fullmatch(value) for value in signatures):
        raise BridgeError("Stripe-Signature header has no valid v1 signature")
    return int(timestamps[0]), signatures


def verify_signature(
    raw_body: bytes,
    signature_header: str,
    endpoint_secret: str,
    *,
    now: int | None = None,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Verify a Stripe v1 HMAC and timestamp without disclosing secret material."""
    if not isinstance(raw_body, bytes) or not raw_body:
        raise BridgeError("raw webhook body must be nonempty bytes")
    if not isinstance(endpoint_secret, str) or not endpoint_secret:
        raise BridgeError("webhook signing secret is unavailable")
    if isinstance(tolerance_seconds, bool) or not isinstance(tolerance_seconds, int) or tolerance_seconds <= 0:
        raise BridgeError("signature tolerance must be a positive integer")
    timestamp, candidates = parse_signature_header(signature_header)
    current = int(time.time()) if now is None else now
    if isinstance(current, bool) or not isinstance(current, int):
        raise BridgeError("verification clock must be an integer Unix timestamp")
    if abs(current - timestamp) > tolerance_seconds:
        raise BridgeError("Stripe-Signature timestamp is outside tolerance")
    signed_payload = str(timestamp).encode("ascii") + b"." + raw_body
    expected = hmac.new(endpoint_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate.lower()) for candidate in candidates):
        raise BridgeError("Stripe-Signature verification failed")
    return {
        "scheme": "v1",
        "timestamp": timestamp,
        "tolerance_seconds": tolerance_seconds,
    }


def parse_verified_payload(raw_body: bytes) -> dict[str, Any]:
    try:
        text = raw_body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise BridgeError("verified payload is not UTF-8 JSON") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_float=_reject_float,
        )
    except json.JSONDecodeError as exc:
        raise BridgeError("verified payload is not valid JSON") from exc
    if not isinstance(value, dict):
        raise BridgeError("verified payload must be a JSON object")
    return value


def _iso_timestamp(unix_seconds: int, field: str) -> str:
    if isinstance(unix_seconds, bool) or not isinstance(unix_seconds, int) or unix_seconds < 0:
        raise BridgeError("%s must be a non-negative Unix timestamp" % field)
    return datetime.fromtimestamp(unix_seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _bridge_result(
    *,
    status: str,
    event: dict[str, Any],
    payload_sha256: str,
    signature: dict[str, Any],
    reason: str,
    observation: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": "commons-stripe-event-bridge/v1",
        "kind": "STRIPE_EVENT_BRIDGE_RESULT",
        "status": status,
        "reason": reason,
        "provider": "stripe",
        "provider_event_id": event["id"],
        "provider_event_type": event["type"],
        "livemode": event["livemode"],
        "payload_sha256": payload_sha256,
        "replay_key": event["id"],
        "signature": signature,
        "observation": observation,
        "claims": ["The raw payload passed Stripe v1 HMAC and timestamp verification before parsing."],
        "non_claims": [
            "Signature verification is not payment, settlement, payout, bank availability, or cash.",
            "Unknown or unbound events do not enter the Commons payment projector.",
        ],
    }


def _metadata_matches(obj: dict[str, Any], request: dict[str, Any], catalog: dict[str, Any]) -> bool:
    metadata = obj.get("metadata")
    if not isinstance(metadata, dict):
        return False
    expected = {
        key: _request_value(request, path) for key, path in METADATA_BINDINGS.items()
    }
    expected["commons_dedupe_key"] = build_checkout_envelope(request, catalog)["idempotency_key"]
    return all(metadata.get(key) == value for key, value in expected.items())


def _event_amount_and_facts(event_type: str, obj: dict[str, Any]) -> tuple[Any, Any, dict[str, Any]]:
    facts: dict[str, Any] = {}
    if event_type.startswith("checkout.session."):
        amount = obj.get("amount_total")
        currency = obj.get("currency")
        if event_type == "checkout.session.completed":
            facts = {"payment_status": obj.get("payment_status")}
    elif event_type == "payment_intent.succeeded":
        amount = obj.get("amount_received", obj.get("amount"))
        currency = obj.get("currency")
    elif event_type == "charge.succeeded":
        amount = obj.get("amount")
        currency = obj.get("currency")
    elif event_type == "charge.refunded":
        amount = obj.get("amount_refunded")
        currency = obj.get("currency")
        if obj.get("refunded") is True and obj.get("amount_refunded") == obj.get("amount"):
            facts = {"refund_status": "succeeded"}
    else:  # pragma: no cover - guarded by the caller
        amount = None
        currency = None
    return amount, currency, facts


def normalize_signed_event(
    raw_body: bytes,
    signature_header: str,
    endpoint_secret: str,
    request: dict[str, Any],
    catalog: dict[str, Any],
    *,
    now: int | None = None,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Verify, bind, and normalize one Stripe snapshot event.

    A valid but unrelated or unknown Stripe event remains observable through a
    public-safe result.  Only an exact request-bound event receives an
    ``observation`` suitable for ``checkout_handoff.payment_projection``.
    """
    request = validate_request(request, catalog)
    signature = verify_signature(
        raw_body,
        signature_header,
        endpoint_secret,
        now=now,
        tolerance_seconds=tolerance_seconds,
    )
    event = parse_verified_payload(raw_body)
    event_id = event.get("id")
    event_type = event.get("type")
    livemode = event.get("livemode")
    created = event.get("created")
    data = event.get("data")
    if not isinstance(event_id, str) or not SAFE_ID_RE.fullmatch(event_id):
        raise BridgeError("verified event id is invalid")
    if not isinstance(event_type, str) or not event_type.strip():
        raise BridgeError("verified event type is invalid")
    if not isinstance(livemode, bool):
        raise BridgeError("verified event must declare livemode")
    if livemode != request["provider"]["livemode"]:
        raise BridgeError("verified event livemode does not match the checkout request")
    occurred_at = _iso_timestamp(created, "event.created")
    if not isinstance(data, dict) or not isinstance(data.get("object"), dict):
        raise BridgeError("verified event data.object is missing")
    obj = data["object"]
    payload_digest = hashlib.sha256(raw_body).hexdigest()

    if event_type not in SUPPORTED_EVENT_TYPES:
        return _bridge_result(
            status="SIGNED_UNKNOWN_EVENT",
            event=event,
            payload_sha256=payload_digest,
            signature=signature,
            reason="EVENT_TYPE_NOT_PROJECTED",
            observation=None,
        )
    if not _metadata_matches(obj, request, catalog):
        return _bridge_result(
            status="SIGNED_UNBOUND_EVENT",
            event=event,
            payload_sha256=payload_digest,
            signature=signature,
            reason="REQUEST_METADATA_ABSENT_OR_MISMATCHED",
            observation=None,
        )
    object_id = obj.get("id")
    if not isinstance(object_id, str) or not object_id.strip() or len(object_id) > 240:
        raise BridgeError("verified event object id is not a public-safe reference")
    amount, currency, facts = _event_amount_and_facts(event_type, obj)
    if event_type == "checkout.session.completed" and obj.get("client_reference_id") != request["crm"]["record_id"]:
        return _bridge_result(
            status="SIGNED_UNBOUND_EVENT",
            event=event,
            payload_sha256=payload_digest,
            signature=signature,
            reason="CLIENT_REFERENCE_MISMATCH",
            observation=None,
        )
    quote_minor = int(Decimal(request["quote"]["amount"]) * 100)
    if isinstance(amount, bool) or not isinstance(amount, int) or amount != quote_minor:
        return _bridge_result(
            status="SIGNED_UNBOUND_EVENT",
            event=event,
            payload_sha256=payload_digest,
            signature=signature,
            reason="AMOUNT_MISMATCH_OR_PARTIAL_REFUND",
            observation=None,
        )
    if not isinstance(currency, str) or currency.upper() != request["quote"]["currency"]:
        return _bridge_result(
            status="SIGNED_UNBOUND_EVENT",
            event=event,
            payload_sha256=payload_digest,
            signature=signature,
            reason="CURRENCY_MISMATCH",
            observation=None,
        )
    if event_type == "checkout.session.completed" and facts.get("payment_status") not in {
        "paid", "unpaid", "no_payment_required",
    }:
        return _bridge_result(
            status="SIGNED_UNBOUND_EVENT",
            event=event,
            payload_sha256=payload_digest,
            signature=signature,
            reason="PAYMENT_STATUS_UNRECOGNIZED",
            observation=None,
        )
    if event_type == "charge.refunded" and facts != {"refund_status": "succeeded"}:
        return _bridge_result(
            status="SIGNED_UNBOUND_EVENT",
            event=event,
            payload_sha256=payload_digest,
            signature=signature,
            reason="REFUND_NOT_COMPLETE",
            observation=None,
        )

    observation = {
        "schema_version": "commons-checkout-event/v1",
        "kind": "CHECKOUT_PROVIDER_OBSERVATION",
        "event_id": "stripe." + hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:24],
        "provider": "stripe",
        "provider_event_id": event_id,
        "provider_event_type": event_type,
        "provider_object_ref": object_id,
        "request_id": request["request_id"],
        "crm_record_ref": request["crm"]["record_id"],
        "sku_id": request["sku_id"],
        "acceptance_digest": request["acceptance_digest"],
        "occurred_at": occurred_at,
        # The receipt store below preserves this first verified delivery time
        # across retries, which keeps the existing exact-event deduper stable.
        "observed_at": _iso_timestamp(signature["timestamp"], "signature.timestamp"),
        "verification": "SIGNATURE_VERIFIED",
        "payload_sha256": payload_digest,
        "amount_minor": amount,
        "currency": currency.upper(),
        "facts": facts,
    }
    # Reuse the existing validator and projector as the compatibility boundary.
    payment_projection(request, [observation], catalog)
    return _bridge_result(
        status="NORMALIZED",
        event=event,
        payload_sha256=payload_digest,
        signature=signature,
        reason="REQUEST_BOUND_PROVIDER_OBSERVATION",
        observation=observation,
    )


def _stable_replay_view(result: dict[str, Any]) -> dict[str, Any]:
    """Return the full receipt with only retry-varying timestamps neutralized."""
    view = json.loads(json.dumps(result))
    signature = view.get("signature")
    if isinstance(signature, dict):
        signature["timestamp"] = "FIRST_VERIFIED_DELIVERY"
    observation = view.get("observation")
    if isinstance(observation, dict):
        observation["observed_at"] = "FIRST_VERIFIED_DELIVERY"
    return view


def persist_bridge_result(result: dict[str, Any], receipt_dir: str | Path) -> tuple[dict[str, Any], str]:
    """Atomically persist the first public-safe result for a Stripe event id.

    A retry with the same provider event and raw-payload digest returns the
    original result, including its first ``observed_at``.  Conflicting bytes
    under one provider event id raise a retryable conflict.
    """
    event_id = result.get("provider_event_id")
    payload_digest = result.get("payload_sha256")
    if not isinstance(event_id, str) or not SAFE_ID_RE.fullmatch(event_id):
        raise BridgeError("bridge result provider_event_id is invalid")
    if not isinstance(payload_digest, str) or not HEX_SHA256_RE.fullmatch(payload_digest):
        raise BridgeError("bridge result payload_sha256 is invalid")
    directory = Path(receipt_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = "stripe-event-" + hashlib.sha256(event_id.encode("utf-8")).hexdigest() + ".json"
    destination = directory / filename
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="x",
            encoding="utf-8",
            newline="\n",
            prefix=filename + ".",
            suffix=".tmp",
            dir=directory,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-link publication is atomic and never overwrites an earlier
        # receipt.  The fully written, fsynced inode exists before it becomes
        # reachable at the canonical replay path.
        os.link(temporary, destination)
        return result, "RECORDED"
    except FileExistsError:
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BridgeError("durable replay receipt is unreadable") from exc
        if _stable_replay_view(existing) != _stable_replay_view(result):
            raise BridgeError("conflicting replay for provider event id")
        return existing, "REPLAYED"
    except OSError as exc:
        raise BridgeError("durable replay receipt publication failed") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def write_or_print(value: Any, path: str | None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        print(destination)
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="host/stripe_event_bridge.py")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--request", required=True)
    parser.add_argument("--payload", required=True, help="path to the exact raw webhook body")
    parser.add_argument("--signature-file", help="file containing the Stripe-Signature header")
    parser.add_argument("--signature-env", default=DEFAULT_SIGNATURE_ENV)
    parser.add_argument("--secret-env", default=DEFAULT_SECRET_ENV)
    parser.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE_SECONDS)
    parser.add_argument("--now", type=int, help="test-only verification clock")
    parser.add_argument("--receipt-dir", required=True, help="durable public-safe event receipt directory")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        secret = os.environ.get(args.secret_env, "")
        if args.signature_file:
            signature_header = Path(args.signature_file).read_text(encoding="utf-8").strip()
        else:
            signature_header = os.environ.get(args.signature_env, "")
        result = normalize_signed_event(
            Path(args.payload).read_bytes(),
            signature_header,
            secret,
            load_json(args.request),
            load_json(args.catalog),
            now=args.now,
            tolerance_seconds=args.tolerance,
        )
        stored, disposition = persist_bridge_result(result, args.receipt_dir)
        write_or_print({"delivery_disposition": disposition, "result": stored}, args.out)
        return 0
    except (BridgeError, HandoffError, OSError, json.JSONDecodeError) as exc:
        print("INVALID %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

