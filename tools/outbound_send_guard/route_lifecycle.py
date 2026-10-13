#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "outbound-route-lifecycle-evidence/v1"
RECEIPT_SCHEMA = "outbound-route-lifecycle-receipt/v1"
DECISIONS = {"BLOCK_ROUTE", "HOLD_ROUTE", "DELIVERED", "UNCONFIRMED"}
MAX_EVENTS = 10_000
_EMAIL_RE = re.compile(r"^[^\s@<>(),;:]+@[^\s@<>(),;:]+$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_STATUS_RE = re.compile(r"^[245]\.[0-9]{1,3}\.[0-9]{1,3}$")


class RouteError(ValueError):
    pass


class DuplicateKeyError(RouteError):
    pass


@dataclass(frozen=True)
class Event:
    event_id: str
    kind: str
    provider_message_id: str
    recipient: str
    observed_at: datetime
    source_id: str
    source_sha256: str
    smtp_code: int | None
    enhanced_status: str | None


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def _dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise RouteError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise RouteError(f"{label} must be a list")
    if len(value) > MAX_EVENTS:
        raise RouteError(f"{label} exceeds {MAX_EVENTS} rows")
    return value


def _text(value: Any, label: str, max_len: int = 512) -> str:
    if type(value) is not str:
        raise RouteError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise RouteError(f"{label} must not be empty")
    if len(text) > max_len:
        raise RouteError(f"{label} exceeds {max_len} characters")
    if any(ord(ch) < 32 for ch in text):
        raise RouteError(f"{label} contains control characters")
    return text


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise RouteError(f"{label} must be a boolean")
    return value


def _int(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int:
        raise RouteError(f"{label} must be an integer")
    if not low <= value <= high:
        raise RouteError(f"{label} must be between {low} and {high}")
    return value


def _email(value: Any, label: str) -> str:
    text = _text(value, label, 320)
    if text.count("@") != 1 or not _EMAIL_RE.fullmatch(text):
        raise RouteError(f"{label} must be one plain email address")
    local, domain = text.rsplit("@", 1)
    if not local or not domain or domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise RouteError(f"{label} is malformed")
    return f"{local}@{domain}".casefold()


def _time(value: Any, label: str) -> datetime:
    text = _text(value, label, 64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RouteError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RouteError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _fmt(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="microseconds" if value.microsecond else "seconds").replace("+00:00", "Z")


def _only(obj: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise RouteError(f"{label} has unknown fields: {', '.join(sorted(extra))}")


def _sha(value: Any, label: str) -> str:
    text = _text(value, label, 64)
    if not _HEX64_RE.fullmatch(text):
        raise RouteError(f"{label} must be lowercase SHA-256 hex")
    return text


def _status(value: Any, label: str) -> str:
    text = _text(value, label, 16)
    if not _STATUS_RE.fullmatch(text):
        raise RouteError(f"{label} must be an enhanced status code like 5.1.1")
    return text


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def parse_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RouteError(f"{label} must be UTF-8 JSON") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(RouteError(f"{label} contains non-finite number {token}")),
        )
    except RouteError:
        raise
    except json.JSONDecodeError as exc:
        raise RouteError(f"{label} is not valid JSON: {exc.msg}") from exc
    return _dict(value, label)


def _parse_event(raw: Any, index: int, recipient: str, provider_message_id: str, sent_at: datetime, as_of: datetime) -> Event:
    label = f"evidence.events[{index}]"
    obj = _dict(raw, label)
    _only(
        obj,
        {"event_id", "kind", "provider_message_id", "recipient", "observed_at", "source_id", "source_sha256", "smtp_code", "enhanced_status"},
        label,
    )
    event_id = _text(obj.get("event_id"), f"{label}.event_id", 256)
    kind = _text(obj.get("kind"), f"{label}.kind", 32)
    if kind not in {"dsn", "delivered", "complaint", "unsubscribe"}:
        raise RouteError(f"{label}.kind must be dsn, delivered, complaint, or unsubscribe")
    event_provider = _text(obj.get("provider_message_id"), f"{label}.provider_message_id", 256)
    if event_provider != provider_message_id:
        raise RouteError(f"{label}.provider_message_id does not match route send")
    event_recipient = _email(obj.get("recipient"), f"{label}.recipient")
    if event_recipient != recipient:
        raise RouteError(f"{label}.recipient is outside route scope")
    observed_at = _time(obj.get("observed_at"), f"{label}.observed_at")
    if observed_at < sent_at:
        raise RouteError(f"{label}.observed_at precedes the send")
    if observed_at > as_of:
        raise RouteError(f"{label}.observed_at is after the as_of boundary")
    source_id = _text(obj.get("source_id"), f"{label}.source_id", 256)
    source_sha256 = _sha(obj.get("source_sha256"), f"{label}.source_sha256")
    smtp_code = obj.get("smtp_code")
    enhanced_status = obj.get("enhanced_status")
    if kind == "dsn":
        smtp_code = _int(smtp_code, f"{label}.smtp_code", 400, 599)
        if smtp_code // 100 not in {4, 5}:
            raise RouteError(f"{label}.smtp_code must be a 4xx or 5xx failure")
        enhanced_status = _status(enhanced_status, f"{label}.enhanced_status")
        if int(enhanced_status.split(".", 1)[0]) != smtp_code // 100:
            raise RouteError(f"{label} SMTP and enhanced-status classes disagree")
    else:
        if smtp_code is not None or enhanced_status is not None:
            raise RouteError(f"{label} non-DSN events must not carry SMTP failure codes")
        smtp_code = None
        enhanced_status = None
    return Event(event_id, kind, event_provider, event_recipient, observed_at, source_id, source_sha256, smtp_code, enhanced_status)


def _parse(raw: dict[str, Any]) -> tuple[str, str, datetime, datetime, str, list[Event], int]:
    _only(raw, {"schema_version", "capture_id", "recipient", "provider_message_id", "sent_at", "as_of", "complete", "next_cursor", "query_id", "events"}, "evidence")
    if raw.get("schema_version") != SCHEMA:
        raise RouteError(f"evidence.schema_version must equal {SCHEMA!r}")
    capture_id = _text(raw.get("capture_id"), "evidence.capture_id", 200)
    recipient = _email(raw.get("recipient"), "evidence.recipient")
    provider_message_id = _text(raw.get("provider_message_id"), "evidence.provider_message_id", 256)
    sent_at = _time(raw.get("sent_at"), "evidence.sent_at")
    as_of = _time(raw.get("as_of"), "evidence.as_of")
    if as_of < sent_at:
        raise RouteError("evidence.as_of must not precede sent_at")
    if not _bool(raw.get("complete"), "evidence.complete"):
        raise RouteError("evidence lookup is incomplete")
    if raw.get("next_cursor") is not None:
        raise RouteError("evidence.next_cursor must be null for a complete lookup")
    query_id = _text(raw.get("query_id"), "evidence.query_id", 200)
    parsed: list[Event] = []
    seen: dict[str, Event] = {}
    duplicates = 0
    for index, item in enumerate(_list(raw.get("events"), "evidence.events")):
        event = _parse_event(item, index, recipient, provider_message_id, sent_at, as_of)
        previous = seen.get(event.event_id)
        if previous is not None:
            if previous != event:
                raise RouteError(f"evidence event_id {event.event_id} has conflicting rows")
            duplicates += 1
            continue
        seen[event.event_id] = event
        parsed.append(event)
    parsed.sort(key=lambda event: (event.observed_at, event.event_id))
    return capture_id, recipient, sent_at, as_of, query_id, parsed, duplicates


def evaluate(raw: dict[str, Any], *, source_sha256: str | None = None) -> dict[str, Any]:
    capture_id, recipient, sent_at, as_of, query_id, events, duplicates = _parse(raw)
    provider_message_id = _text(raw.get("provider_message_id"), "evidence.provider_message_id", 256)
    recipient_blocks: list[Event] = []
    destination_blocks: list[Event] = []
    temporary_holds: list[Event] = []
    review_holds: list[Event] = []
    delivered: list[Event] = []
    reasons: list[str] = []

    for event in events:
        if event.kind in {"complaint", "unsubscribe"}:
            recipient_blocks.append(event)
            continue
        if event.kind == "delivered":
            delivered.append(event)
            continue
        if event.kind != "dsn" or event.enhanced_status is None or event.smtp_code is None:
            raise RouteError("normalized event has an invalid internal kind")
        if event.enhanced_status == "5.1.1":
            destination_blocks.append(event)
        elif event.smtp_code // 100 == 4:
            temporary_holds.append(event)
        else:
            review_holds.append(event)

    if recipient_blocks:
        decision = "BLOCK_ROUTE"
        authority = "complete"
        if any(event.kind == "unsubscribe" for event in recipient_blocks):
            reasons.append("recipient unsubscribe evidence blocks future use of this route")
        if any(event.kind == "complaint" for event in recipient_blocks):
            reasons.append("recipient complaint evidence blocks future use of this route")
        if delivered:
            reasons.append("delivery evidence does not erase later or earlier recipient opt-out/complaint intent")
    elif destination_blocks and delivered:
        decision = "HOLD_ROUTE"
        authority = "unknown"
        reasons.append("delivery evidence conflicts with enhanced-status 5.1.1 route-blocking evidence")
    elif destination_blocks:
        decision = "BLOCK_ROUTE"
        authority = "complete"
        reasons.append("enhanced status 5.1.1 proves a bad destination mailbox for this route")
    elif review_holds and delivered:
        decision = "HOLD_ROUTE"
        authority = "unknown"
        reasons.append("delivery evidence conflicts with a non-allowlisted permanent SMTP failure event")
    elif review_holds:
        decision = "HOLD_ROUTE"
        authority = "complete"
        reasons.append("permanent SMTP failure is not an allowlisted dead-mailbox code; hold for route review")
    elif temporary_holds and delivered:
        latest_temporary = max(event.observed_at for event in temporary_holds)
        latest_delivery = max(event.observed_at for event in delivered)
        if latest_delivery > latest_temporary:
            decision = "DELIVERED"
            authority = "complete"
            reasons.append("explicit delivery evidence strictly postdates all temporary SMTP failures for the exact route send")
        else:
            decision = "HOLD_ROUTE"
            authority = "unknown"
            reasons.append("a temporary SMTP failure is not followed by strictly later delivery evidence")
    elif temporary_holds:
        decision = "HOLD_ROUTE"
        authority = "complete"
        reasons.append("temporary SMTP failure requires a fresh route check before retry")
    elif delivered:
        decision = "DELIVERED"
        authority = "complete"
        reasons.append("explicit delivery evidence exists for the exact provider message and recipient")
    else:
        decision = "UNCONFIRMED"
        authority = "complete"
        reasons.append("complete lookup contains no delivery or failure event for the exact provider message")

    if decision not in DECISIONS:
        raise RouteError("internal decision is outside the receipt contract")
    refs = [f"{event.kind}:{event.event_id}" for event in events]
    payload = {
        "schema_version": RECEIPT_SCHEMA,
        "capture_id": capture_id,
        "route": {
            "recipient": recipient,
            "provider_message_id": provider_message_id,
            "sent_at": _fmt(sent_at),
            "as_of": _fmt(as_of),
            "query_id": query_id,
        },
        "decision": decision,
        "authority": authority,
        "reasons": reasons,
        "event_refs": refs,
        "exact_duplicates_collapsed": duplicates,
        "source_evidence_sha256": source_sha256 or hashlib.sha256(canonical_bytes(raw)).hexdigest(),
        "same_route_resend_authorized": False,
        "alternate_route_requires_independent_send_guard": True,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": hashlib.sha256(canonical_bytes(payload)).hexdigest()}


def _aliases(a: Path, b: Path) -> bool:
    try:
        if a.resolve(strict=False) == b.resolve(strict=False):
            return True
    except OSError as exc:
        raise RouteError(f"cannot resolve path identity: {exc}") from exc
    try:
        return os.path.samefile(a, b)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RouteError(f"cannot compare path identity: {exc}") from exc


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.stage-", dir=str(path.parent))
    except OSError as exc:
        raise RouteError(f"cannot stage output {path}: {exc}") from exc
    stage = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(stage, path)
        if os.name != "nt":
            dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
    except OSError as exc:
        try:
            if os.path.lexists(stage):
                stage.unlink()
        finally:
            raise RouteError(f"cannot publish output {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify route-specific outbound delivery evidence without authorizing a send")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.out is not None and _aliases(args.evidence, args.out):
            raise RouteError("output must not alias evidence input")
        try:
            raw = args.evidence.read_bytes()
        except OSError as exc:
            raise RouteError(f"cannot read evidence {args.evidence}: {exc}") from exc
        obj = parse_json_bytes(raw, "evidence")
        receipt = evaluate(obj, source_sha256=hashlib.sha256(raw).hexdigest())
        encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        if args.out is None:
            sys.stdout.buffer.write(encoded)
        else:
            _atomic_write(args.out, encoded)
        return {"BLOCK_ROUTE": 5, "HOLD_ROUTE": 4, "DELIVERED": 0, "UNCONFIRMED": 3}[receipt["payload"]["decision"]]
    except RouteError as exc:
        print(f"outbound-route-lifecycle: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
