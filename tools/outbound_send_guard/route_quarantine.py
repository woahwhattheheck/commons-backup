#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import dsn_authority, guard, route_lifecycle

BUNDLE_SCHEMA = "outbound-route-quarantine-bundle/v1"
RECEIPT_SCHEMA = "outbound-route-aware-send-receipt/v1"
DECISIONS = {"ALLOW_NEW", "REPLY_ONLY", "HOLD", "DO_NOT_RESEND", "DO_NOT_USE_ROUTE"}
ROUTE_STATES = {"CLEAR", "HOLD", "BLOCKED"}
MAX_ROUTE_CHECKS = 10_000
MAX_INPUT_BYTES = 8 * 1024 * 1024
_EMAIL_RE = re.compile(r"^[^\s@<>(),;:]+@[^\s@<>(),;:]+$")


class QuarantineError(ValueError):
    pass


class DuplicateKeyError(QuarantineError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def _dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise QuarantineError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise QuarantineError(f"{label} must be a list")
    if len(value) > MAX_ROUTE_CHECKS:
        raise QuarantineError(f"{label} exceeds {MAX_ROUTE_CHECKS} rows")
    return value


def _text(value: Any, label: str, max_len: int = 512) -> str:
    if type(value) is not str:
        raise QuarantineError(f"{label} must be a string")
    value = value.strip()
    if not value:
        raise QuarantineError(f"{label} must not be empty")
    if len(value) > max_len:
        raise QuarantineError(f"{label} exceeds {max_len} characters")
    if any(ord(ch) < 32 for ch in value):
        raise QuarantineError(f"{label} contains control characters")
    return value


def _email(value: Any, label: str) -> str:
    value = _text(value, label, 320)
    if value.count("@") != 1 or not _EMAIL_RE.fullmatch(value):
        raise QuarantineError(f"{label} must be one plain email address")
    local, domain = value.rsplit("@", 1)
    if not local or not domain or domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise QuarantineError(f"{label} is malformed")
    return f"{local}@{domain}".casefold()


def _time(value: Any, label: str) -> datetime:
    value = _text(value, label, 64)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise QuarantineError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QuarantineError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _fmt(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="microseconds" if value.microsecond else "seconds").replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise QuarantineError("value is not strict canonical JSON") from exc


def digest_object(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_INPUT_BYTES:
        raise QuarantineError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise QuarantineError(f"{label} must be UTF-8 JSON") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                QuarantineError(f"{label} contains non-finite number {token}")
            ),
        )
    except QuarantineError:
        raise
    except (ValueError, RecursionError) as exc:
        raise QuarantineError(f"{label} is not valid bounded JSON") from exc
    return _dict(value, label)


def _snapshot(value: Any, label: str) -> dict[str, Any]:
    return parse_json_bytes(canonical_bytes(_dict(value, label)), label)


def _only(obj: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise QuarantineError(f"{label} has unknown fields: {', '.join(sorted(extra))}")


def _parse_bundle(raw: dict[str, Any]) -> tuple[str, datetime, list[dict[str, Any]]]:
    _only(raw, {"schema_version", "recipient", "as_of", "route_checks"}, "route_bundle")
    if raw.get("schema_version") != BUNDLE_SCHEMA:
        raise QuarantineError(f"route_bundle.schema_version must equal {BUNDLE_SCHEMA!r}")
    recipient = _email(raw.get("recipient"), "route_bundle.recipient")
    as_of = _time(raw.get("as_of"), "route_bundle.as_of")
    checks: list[dict[str, Any]] = []
    for index, item in enumerate(_list(raw.get("route_checks"), "route_bundle.route_checks")):
        checks.append(_dict(item, f"route_bundle.route_checks[{index}]"))
    return recipient, as_of, checks


def _provider_outbounds(send_evidence: dict[str, Any], recipient: str) -> dict[str, datetime]:
    mailbox = _dict(send_evidence.get("mailbox"), "send_evidence.mailbox")
    messages = mailbox.get("messages")
    if type(messages) is not list:
        raise QuarantineError("send_evidence.mailbox.messages must be a list")
    out: dict[str, datetime] = {}
    for index, raw in enumerate(messages):
        row = _dict(raw, f"send_evidence.mailbox.messages[{index}]")
        if row.get("direction") != "outbound":
            continue
        counterparty = _email(row.get("counterparty"), f"send_evidence.mailbox.messages[{index}].counterparty")
        if counterparty != recipient:
            continue
        message_id = _text(row.get("message_id"), f"send_evidence.mailbox.messages[{index}].message_id", 256)
        observed_at = _time(row.get("observed_at"), f"send_evidence.mailbox.messages[{index}].observed_at")
        previous = out.get(message_id)
        if previous is not None and previous != observed_at:
            raise QuarantineError(f"provider message {message_id!r} has conflicting outbound timestamps")
        out[message_id] = observed_at
    slack = _dict(send_evidence.get("slack"), "send_evidence.slack")
    events = slack.get("events")
    if type(events) is not list:
        raise QuarantineError("send_evidence.slack.events must be a list")
    for index, raw in enumerate(events):
        row = _dict(raw, f"send_evidence.slack.events[{index}]")
        if row.get("kind") != "sent":
            continue
        row_recipient = _email(row.get("recipient"), f"send_evidence.slack.events[{index}].recipient")
        if row_recipient != recipient:
            continue
        provider_message_id = row.get("provider_message_id")
        if provider_message_id is None:
            raise QuarantineError(
                f"send_evidence.slack.events[{index}] is a sent receipt without provider_message_id; "
                "route lifecycle coverage cannot be proven"
            )
        provider_message_id = _text(
            provider_message_id, f"send_evidence.slack.events[{index}].provider_message_id", 256
        )
        if provider_message_id not in out:
            raise QuarantineError(
                f"slack sent receipt {provider_message_id!r} has no matching provider outbound in mailbox evidence"
            )
    return out


def _retained_dsn_events(
    raw: dict[str, Any] | None, recipient: str, as_of: datetime, outbounds: dict[str, datetime],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Recompute a separate capture input; never synthesize it from a route claim."""
    if raw is None:
        return {}
    _only(raw, {"sources"}, "dsn_sources")
    by_provider: dict[str, dict[str, dict[str, Any]]] = {}
    source_ids: set[str] = set()
    for index, item in enumerate(_list(raw.get("sources"), "dsn_sources.sources")):
        label = f"dsn_sources.sources[{index}]"
        source = _dict(item, label)
        _only(source, {"raw_mime_base64", "binding", "receipt"}, label)
        encoded = source.get("raw_mime_base64")
        if type(encoded) is not str or not encoded or len(encoded) > MAX_INPUT_BYTES:
            raise QuarantineError(f"{label}.raw_mime_base64 must be a bounded nonempty string")
        try:
            mime = base64.b64decode(encoded, validate=True)
            if base64.b64encode(mime).decode("ascii") != encoded:
                raise ValueError("noncanonical base64")
        except (ValueError, binascii.Error) as exc:
            raise QuarantineError(f"{label}.raw_mime_base64 must be canonical base64") from exc
        binding = _dict(source.get("binding"), f"{label}.binding")
        claimed = _dict(source.get("receipt"), f"{label}.receipt")
        try:
            recomputed = dsn_authority.authoritative_receipt(claimed, mime, binding)
        except (ValueError, TypeError, RecursionError) as exc:
            raise QuarantineError(f"{label}: retained DSN recomputation failed: {exc}") from exc
        event = recomputed["event"]
        provider = event["provider_message_id"]
        if event["recipient"] != recipient or provider not in outbounds:
            raise QuarantineError(f"{label}: retained DSN is outside the recipient/provider send scope")
        if _time(binding.get("sent_at"), f"{label}.binding.sent_at") != outbounds[provider]:
            raise QuarantineError(f"{label}: retained binding disagrees with the provider send time")
        if _time(binding.get("captured_at"), f"{label}.binding.captured_at") > as_of:
            raise QuarantineError(f"{label}: retained capture is after the route bundle boundary")
        source_id = event["source_id"]
        if source_id in source_ids:
            raise QuarantineError(f"{label}: duplicate retained DSN source identity")
        source_ids.add(source_id)
        events = by_provider.setdefault(provider, {})
        if event["event_id"] in events:
            raise QuarantineError(f"{label}: duplicate retained DSN event identity")
        events[event["event_id"]] = recomputed
    return by_provider


def _source_authority(
    check: dict[str, Any], retained: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    matched: set[str] = set()
    problems: list[str] = []
    for index, event in enumerate(check["events"]):
        if event["kind"] != "dsn":
            problems.append(f"event {index}: {event['kind']} has no retained-source authority adapter")
            continue
        source = retained.get(event["event_id"])
        if source is None:
            problems.append(f"event {index}: matching retained DSN source is missing")
        elif canonical_bytes(event) != canonical_bytes(source["event"]):
            problems.append(f"event {index}: claim differs from the complete source-recomputed DSN event")
        else:
            matched.add(event["event_id"])
    missing = sorted(set(retained) - matched)
    if missing:
        problems.append("retained DSN events omitted or substituted in the route check: " + ", ".join(missing))
    return problems, sorted(matched)


def evaluate(
    intent_raw: dict[str, Any],
    send_evidence_raw: dict[str, Any],
    route_bundle_raw: dict[str, Any],
    *,
    dsn_sources_raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose normal send preflight with source-bound route-health coverage.

    Retained MIME, binding and normalizer receipts are a separate trusted capture
    input, not reconstructed from route checks. No result authorizes a side effect.
    """
    # Downstream parsing and hashing consume the same detached JSON generations.
    intent_raw = _snapshot(intent_raw, "intent")
    send_evidence_raw = _snapshot(send_evidence_raw, "send_evidence")
    route_bundle_raw = _snapshot(route_bundle_raw, "route_bundle")
    if dsn_sources_raw is not None:
        dsn_sources_raw = _snapshot(dsn_sources_raw, "dsn_sources")
    try:
        send_guard = guard.evaluate(intent_raw, send_evidence_raw)
    except Exception as exc:
        raise QuarantineError(f"send guard rejected inputs: {exc}") from exc

    intent_recipient = _email(intent_raw.get("recipient"), "intent.recipient")
    recipient, bundle_as_of, checks = _parse_bundle(route_bundle_raw)
    if recipient != intent_recipient:
        raise QuarantineError("route_bundle.recipient does not match intent.recipient")

    generated_at = _time(send_evidence_raw.get("generated_at"), "send_evidence.generated_at")
    if bundle_as_of != generated_at:
        raise QuarantineError("route_bundle.as_of must equal send_evidence.generated_at")

    outbounds = _provider_outbounds(send_evidence_raw, recipient)
    retained = _retained_dsn_events(dsn_sources_raw, recipient, bundle_as_of, outbounds)
    by_provider: dict[str, tuple[dict[str, Any], dict[str, Any], list[str], list[str]]] = {}
    for index, check in enumerate(checks):
        try:
            route_receipt = route_lifecycle.evaluate(check, source_sha256=digest_object(check))
        except Exception as exc:
            raise QuarantineError(f"route_bundle.route_checks[{index}] is invalid: {exc}") from exc
        payload = _dict(route_receipt.get("payload"), f"route_receipt[{index}].payload")
        route = _dict(payload.get("route"), f"route_receipt[{index}].payload.route")
        route_recipient = _email(route.get("recipient"), f"route_receipt[{index}].payload.route.recipient")
        if route_recipient != recipient:
            raise QuarantineError(f"route check {index} is outside recipient scope")
        provider_message_id = _text(
            route.get("provider_message_id"), f"route_receipt[{index}].payload.route.provider_message_id", 256
        )
        if provider_message_id in by_provider:
            raise QuarantineError(f"duplicate route check for provider message {provider_message_id!r}")
        route_as_of = _time(route.get("as_of"), f"route_receipt[{index}].payload.route.as_of")
        if route_as_of != bundle_as_of:
            raise QuarantineError(f"route check {provider_message_id!r} does not share the bundle as_of boundary")
        sent_at = _time(route.get("sent_at"), f"route_receipt[{index}].payload.route.sent_at")
        expected_sent_at = outbounds.get(provider_message_id)
        if expected_sent_at is None:
            raise QuarantineError(f"route check references provider message {provider_message_id!r} absent from send evidence")
        if sent_at != expected_sent_at:
            raise QuarantineError(f"route check {provider_message_id!r} sent_at disagrees with send evidence")
        problems, matched = _source_authority(check, retained.get(provider_message_id, {}))
        by_provider[provider_message_id] = (check, route_receipt, problems, matched)

    missing = sorted(set(outbounds) - set(by_provider))
    if missing:
        raise QuarantineError(
            "route lifecycle coverage is incomplete for provider outbound messages: " + ", ".join(missing)
        )

    # A self-hash authenticates neither a DSN nor a delivery/recipient-intent claim.
    # Keep the classifier receipt for traceability, but only consume its decision
    # after every claimed event and every supplied retained event is reconciled.
    decisions = ["HOLD_ROUTE" if entry[2] else entry[1]["payload"]["decision"] for entry in by_provider.values()]
    if any(decision == "BLOCK_ROUTE" for decision in decisions):
        route_state = "BLOCKED"
    elif any(decision == "HOLD_ROUTE" for decision in decisions):
        route_state = "HOLD"
    else:
        route_state = "CLEAR"
    assert route_state in ROUTE_STATES

    guard_payload = _dict(send_guard.get("payload"), "send_guard.payload")
    guard_decision = _text(guard_payload.get("decision"), "send_guard.payload.decision", 32)
    if guard_decision not in {"ALLOW_NEW", "REPLY_ONLY", "HOLD", "DO_NOT_RESEND"}:
        raise QuarantineError(f"unexpected send guard decision {guard_decision!r}")

    if guard_decision == "DO_NOT_RESEND":
        decision = "DO_NOT_RESEND"
        reasons = ["terminal send-guard prohibition preserved regardless of route-source review state"]
    elif route_state == "BLOCKED":
        decision = "DO_NOT_USE_ROUTE"
        reasons = ["source-recomputed DSN lifecycle evidence blocks this email route"]
    elif route_state == "HOLD":
        decision = "HOLD"
        reasons = ["route lifecycle or retained-source reconciliation requires review before any same-route send"]
    else:
        decision = guard_decision
        reasons = [f"send guard decision preserved under clear route lifecycle coverage: {guard_decision}"]
    assert decision in DECISIONS

    route_receipts = []
    for provider_message_id in sorted(by_provider):
        check, receipt, problems, matched = by_provider[provider_message_id]
        sources = retained.get(provider_message_id, {})
        route_receipts.append(
            {
                "provider_message_id": provider_message_id,
                "route_evidence_sha256": digest_object(check),
                "route_receipt_sha256": _text(receipt.get("receipt_sha256"), "route receipt digest", 64),
                "claimed_lifecycle_decision": receipt["payload"]["decision"],
                "decision": "HOLD_ROUTE" if problems else receipt["payload"]["decision"],
                "source_authority_problems": problems,
                "source_matched_event_ids": matched,
                "retained_dsn_receipts": [
                    {
                        "event_id": event_id,
                        "source_id": sources[event_id]["source_id"],
                        "source_sha256": sources[event_id]["source_sha256"],
                        "binding_sha256": sources[event_id]["binding_sha256"],
                        "receipt_sha256": sources[event_id]["receipt_sha256"],
                    }
                    for event_id in sorted(sources)
                ],
            }
        )

    payload = {
        "schema_version": RECEIPT_SCHEMA,
        "recipient": recipient,
        "as_of": _fmt(bundle_as_of),
        "decision": decision,
        "route_state": route_state,
        "send_guard_decision": guard_decision,
        "reasons": reasons,
        "checked_provider_message_ids": sorted(outbounds),
        "route_receipts": route_receipts,
        "intent_sha256": digest_object(intent_raw),
        "send_evidence_sha256": digest_object(send_evidence_raw),
        "route_bundle_sha256": digest_object(route_bundle_raw),
        "dsn_sources_sha256": digest_object(dsn_sources_raw) if dsn_sources_raw is not None else None,
        "send_guard_receipt_sha256": _text(send_guard.get("receipt_sha256"), "send guard digest", 64),
        # A route block never creates an obligation to hunt another alias.
        "alternate_route_research_required": False,
        "research_obligation": None,
        "route_review_required": route_state == "HOLD",
        "same_route_send_authorized": False,
        "alternate_route_send_requires_fresh_preflight": True,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": digest_object(payload)}


def verify(
    receipt_raw: dict[str, Any],
    intent_raw: dict[str, Any],
    send_evidence_raw: dict[str, Any],
    route_bundle_raw: dict[str, Any],
    *,
    dsn_sources_raw: dict[str, Any] | None = None,
) -> bool:
    claimed = _snapshot(receipt_raw, "receipt")
    _only(claimed, {"payload", "receipt_sha256"}, "receipt")
    recomputed = evaluate(intent_raw, send_evidence_raw, route_bundle_raw, dsn_sources_raw=dsn_sources_raw)
    return canonical_bytes(claimed) == canonical_bytes(recomputed)


def _read_bounded_regular(path: Path, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise QuarantineError(f"cannot open {label}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise QuarantineError(f"{label} must be a regular file")
        if before.st_size > MAX_INPUT_BYTES:
            raise QuarantineError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
        chunks: list[bytes] = []
        remaining = MAX_INPUT_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_INPUT_BYTES:
            raise QuarantineError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
        after = os.fstat(fd)
        generation_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        generation_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if generation_before != generation_after or len(raw) != after.st_size:
            raise QuarantineError(f"{label} changed while being read")
        return raw
    finally:
        os.close(fd)


def _load(path: Path, label: str) -> dict[str, Any]:
    return parse_json_bytes(_read_bounded_regular(path, label), label)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compose outbound send guard with route lifecycle quarantine authority")
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--send-evidence", type=Path, required=True)
    parser.add_argument("--route-bundle", type=Path, required=True)
    parser.add_argument("--dsn-sources", type=Path, help="separate retained MIME/binding/normalizer-receipt input")
    parser.add_argument("--receipt", type=Path, help="optional receipt to verify instead of compiling")
    args = parser.parse_args(argv)
    try:
        intent = _load(args.intent, "intent")
        evidence = _load(args.send_evidence, "send evidence")
        bundle = _load(args.route_bundle, "route bundle")
        sources = _load(args.dsn_sources, "DSN sources") if args.dsn_sources is not None else None
        if args.receipt is not None:
            receipt = _load(args.receipt, "receipt")
            if not verify(receipt, intent, evidence, bundle, dsn_sources_raw=sources):
                raise QuarantineError("receipt does not exactly recompute from supplied sources")
            print("VERIFIED")
            return 0
        receipt = evaluate(intent, evidence, bundle, dsn_sources_raw=sources)
        sys.stdout.buffer.write(canonical_bytes(receipt))
        decision = receipt["payload"]["decision"]
        return {"ALLOW_NEW": 0, "REPLY_ONLY": 3, "HOLD": 4, "DO_NOT_RESEND": 5, "DO_NOT_USE_ROUTE": 6}[decision]
    except (OSError, QuarantineError) as exc:
        print(f"route-quarantine error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
