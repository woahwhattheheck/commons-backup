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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

INTENT_SCHEMA = "outbound-send-intent/v1"
EVIDENCE_SCHEMA = "outbound-send-evidence/v1"
RECEIPT_SCHEMA = "outbound-send-guard-receipt/v1"
DECISIONS = {"ALLOW_NEW", "REPLY_ONLY", "HOLD", "DO_NOT_RESEND"}
DEFAULT_CROSS_OFFER_COOLDOWN_DAYS = 30
DEFAULT_MAX_EVIDENCE_AGE_SECONDS = 900
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 300
MAX_EVIDENCE_ROWS = 10_000
_EMAIL_RE = re.compile(r"^[^\s@<>(),;:]+@[^\s@<>(),;:]+$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class GuardError(ValueError):
    pass


class DuplicateKeyError(GuardError):
    pass


@dataclass(frozen=True)
class Policy:
    cross_offer_cooldown_days: int = DEFAULT_CROSS_OFFER_COOLDOWN_DAYS
    max_evidence_age_seconds: int = DEFAULT_MAX_EVIDENCE_AGE_SECONDS
    max_future_skew_seconds: int = DEFAULT_MAX_FUTURE_SKEW_SECONDS


@dataclass(frozen=True)
class MailRow:
    message_id: str
    direction: str
    counterparty: str
    observed_at: datetime
    offer_id: str | None


@dataclass(frozen=True)
class SlackRow:
    event_id: str
    kind: str
    recipient: str
    observed_at: datetime
    offer_id: str | None
    provider_message_id: str | None


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GuardError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise GuardError(f"{label} must be a list")
    if len(value) > MAX_EVIDENCE_ROWS:
        raise GuardError(f"{label} exceeds {MAX_EVIDENCE_ROWS} rows")
    return value


def _require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise GuardError(f"{label} must be a boolean")
    return value


def _require_int(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise GuardError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise GuardError(f"{label} must be between {minimum} and {maximum}")
    return value


def _require_text(value: Any, label: str, *, max_len: int = 512) -> str:
    if type(value) is not str:
        raise GuardError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise GuardError(f"{label} must not be empty")
    if len(text) > max_len:
        raise GuardError(f"{label} exceeds {max_len} characters")
    if any(ord(ch) < 32 for ch in text):
        raise GuardError(f"{label} contains control characters")
    return text


def _optional_text(value: Any, label: str, *, max_len: int = 512) -> str | None:
    if value is None:
        return None
    return _require_text(value, label, max_len=max_len)


def normalize_email(value: Any, label: str = "email") -> str:
    text = _require_text(value, label, max_len=320)
    if not _EMAIL_RE.fullmatch(text) or text.count("@") != 1:
        raise GuardError(f"{label} must be one plain email address")
    local, domain = text.rsplit("@", 1)
    if not local or not domain or domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise GuardError(f"{label} is malformed")
    return f"{local}@{domain}".casefold()


def parse_time(value: Any, label: str) -> datetime:
    text = _require_text(value, label, max_len=64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GuardError(f"{label} must be ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise GuardError(f"{label} must include a timezone")
    return dt.astimezone(timezone.utc)


def format_time(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    if dt.microsecond:
        return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest_object(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def parse_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GuardError(f"{label} must be UTF-8 JSON") from exc
    try:
        value = json.loads(text, object_pairs_hook=_strict_object, parse_constant=lambda x: (_ for _ in ()).throw(GuardError(f"{label} contains non-finite number {x}")))
    except DuplicateKeyError:
        raise
    except GuardError:
        raise
    except json.JSONDecodeError as exc:
        raise GuardError(f"{label} is not valid JSON: {exc.msg}") from exc
    return _require_dict(value, label)


def _parse_policy(raw: Any) -> Policy:
    if raw is None:
        return Policy()
    obj = _require_dict(raw, "evidence.policy")
    allowed = {"cross_offer_cooldown_days", "max_evidence_age_seconds", "max_future_skew_seconds"}
    unknown = set(obj) - allowed
    if unknown:
        raise GuardError(f"evidence.policy has unknown fields: {', '.join(sorted(unknown))}")
    return Policy(
        cross_offer_cooldown_days=_require_int(obj.get("cross_offer_cooldown_days", DEFAULT_CROSS_OFFER_COOLDOWN_DAYS), "evidence.policy.cross_offer_cooldown_days", minimum=0, maximum=3650),
        max_evidence_age_seconds=_require_int(obj.get("max_evidence_age_seconds", DEFAULT_MAX_EVIDENCE_AGE_SECONDS), "evidence.policy.max_evidence_age_seconds", minimum=0, maximum=604800),
        max_future_skew_seconds=_require_int(obj.get("max_future_skew_seconds", DEFAULT_MAX_FUTURE_SKEW_SECONDS), "evidence.policy.max_future_skew_seconds", minimum=0, maximum=86400),
    )


def _parse_intent(raw: dict[str, Any]) -> dict[str, Any]:
    allowed = {"schema_version", "intent_id", "recipient", "offer_id", "requested_at", "route_kind"}
    unknown = set(raw) - allowed
    if unknown:
        raise GuardError(f"intent has unknown fields: {', '.join(sorted(unknown))}")
    if raw.get("schema_version") != INTENT_SCHEMA:
        raise GuardError(f"intent.schema_version must equal {INTENT_SCHEMA!r}")
    route = _require_text(raw.get("route_kind", "email"), "intent.route_kind", max_len=32)
    if route != "email":
        raise GuardError("intent.route_kind must equal 'email'")
    return {
        "schema_version": INTENT_SCHEMA,
        "intent_id": _require_text(raw.get("intent_id"), "intent.intent_id", max_len=200),
        "recipient": normalize_email(raw.get("recipient"), "intent.recipient"),
        "offer_id": _require_text(raw.get("offer_id"), "intent.offer_id", max_len=200),
        "requested_at": parse_time(raw.get("requested_at"), "intent.requested_at"),
        "route_kind": "email",
    }


def _parse_mail_rows(raw: Any) -> tuple[bool, str, list[MailRow], list[str]]:
    obj = _require_dict(raw, "evidence.mailbox")
    allowed = {"complete", "query_id", "messages"}
    unknown = set(obj) - allowed
    if unknown:
        raise GuardError(f"evidence.mailbox has unknown fields: {', '.join(sorted(unknown))}")
    complete = _require_bool(obj.get("complete"), "evidence.mailbox.complete")
    query_id = _require_text(obj.get("query_id"), "evidence.mailbox.query_id", max_len=200)
    rows: list[MailRow] = []
    conflicts: list[str] = []
    seen: dict[str, MailRow] = {}
    for index, item in enumerate(_require_list(obj.get("messages"), "evidence.mailbox.messages")):
        row = _require_dict(item, f"evidence.mailbox.messages[{index}]")
        allowed_row = {"message_id", "direction", "counterparty", "observed_at", "offer_id"}
        extra = set(row) - allowed_row
        if extra:
            raise GuardError(f"evidence.mailbox.messages[{index}] has unknown fields: {', '.join(sorted(extra))}")
        parsed = MailRow(
            message_id=_require_text(row.get("message_id"), f"evidence.mailbox.messages[{index}].message_id", max_len=256),
            direction=_require_text(row.get("direction"), f"evidence.mailbox.messages[{index}].direction", max_len=16),
            counterparty=normalize_email(row.get("counterparty"), f"evidence.mailbox.messages[{index}].counterparty"),
            observed_at=parse_time(row.get("observed_at"), f"evidence.mailbox.messages[{index}].observed_at"),
            offer_id=_optional_text(row.get("offer_id"), f"evidence.mailbox.messages[{index}].offer_id", max_len=200),
        )
        if parsed.direction not in {"inbound", "outbound"}:
            raise GuardError(f"evidence.mailbox.messages[{index}].direction must be inbound or outbound")
        previous = seen.get(parsed.message_id)
        if previous is not None and previous != parsed:
            conflicts.append(f"mailbox message_id {parsed.message_id} has conflicting rows")
            continue
        if previous is None:
            seen[parsed.message_id] = parsed
            rows.append(parsed)
    return complete, query_id, rows, conflicts


def _parse_slack_rows(raw: Any) -> tuple[bool, str, list[SlackRow], list[str]]:
    obj = _require_dict(raw, "evidence.slack")
    allowed = {"complete", "query_id", "events"}
    unknown = set(obj) - allowed
    if unknown:
        raise GuardError(f"evidence.slack has unknown fields: {', '.join(sorted(unknown))}")
    complete = _require_bool(obj.get("complete"), "evidence.slack.complete")
    query_id = _require_text(obj.get("query_id"), "evidence.slack.query_id", max_len=200)
    rows: list[SlackRow] = []
    conflicts: list[str] = []
    seen: dict[str, SlackRow] = {}
    for index, item in enumerate(_require_list(obj.get("events"), "evidence.slack.events")):
        row = _require_dict(item, f"evidence.slack.events[{index}]")
        allowed_row = {"event_id", "kind", "recipient", "observed_at", "offer_id", "provider_message_id"}
        extra = set(row) - allowed_row
        if extra:
            raise GuardError(f"evidence.slack.events[{index}] has unknown fields: {', '.join(sorted(extra))}")
        parsed = SlackRow(
            event_id=_require_text(row.get("event_id"), f"evidence.slack.events[{index}].event_id", max_len=256),
            kind=_require_text(row.get("kind"), f"evidence.slack.events[{index}].kind", max_len=32),
            recipient=normalize_email(row.get("recipient"), f"evidence.slack.events[{index}].recipient"),
            observed_at=parse_time(row.get("observed_at"), f"evidence.slack.events[{index}].observed_at"),
            offer_id=_optional_text(row.get("offer_id"), f"evidence.slack.events[{index}].offer_id", max_len=200),
            provider_message_id=_optional_text(row.get("provider_message_id"), f"evidence.slack.events[{index}].provider_message_id", max_len=256),
        )
        if parsed.kind not in {"lead", "sent", "hard_dnr"}:
            raise GuardError(f"evidence.slack.events[{index}].kind must be lead, sent, or hard_dnr")
        previous = seen.get(parsed.event_id)
        if previous is not None and previous != parsed:
            conflicts.append(f"slack event_id {parsed.event_id} has conflicting rows")
            continue
        if previous is None:
            seen[parsed.event_id] = parsed
            rows.append(parsed)
    return complete, query_id, rows, conflicts


def _parse_evidence(raw: dict[str, Any]) -> tuple[datetime, Policy, bool, str, list[MailRow], bool, str, list[SlackRow], list[str]]:
    allowed = {"schema_version", "generated_at", "mailbox", "slack", "policy"}
    unknown = set(raw) - allowed
    if unknown:
        raise GuardError(f"evidence has unknown fields: {', '.join(sorted(unknown))}")
    if raw.get("schema_version") != EVIDENCE_SCHEMA:
        raise GuardError(f"evidence.schema_version must equal {EVIDENCE_SCHEMA!r}")
    generated_at = parse_time(raw.get("generated_at"), "evidence.generated_at")
    policy = _parse_policy(raw.get("policy"))
    mail_complete, mail_query_id, mail_rows, mail_conflicts = _parse_mail_rows(raw.get("mailbox"))
    slack_complete, slack_query_id, slack_rows, slack_conflicts = _parse_slack_rows(raw.get("slack"))
    return generated_at, policy, mail_complete, mail_query_id, mail_rows, slack_complete, slack_query_id, slack_rows, mail_conflicts + slack_conflicts


def _row_ref(kind: str, row_id: str) -> str:
    return f"{kind}:{row_id}"


def evaluate(intent_raw: dict[str, Any], evidence_raw: dict[str, Any], *, intent_sha256: str | None = None, evidence_sha256: str | None = None) -> dict[str, Any]:
    intent = _parse_intent(intent_raw)
    generated_at, policy, mail_complete, mail_query_id, mail_rows, slack_complete, slack_query_id, slack_rows, conflicts = _parse_evidence(evidence_raw)
    recipient = intent["recipient"]
    offer_id = intent["offer_id"]
    requested_at = intent["requested_at"]

    reasons: list[str] = []
    matched_refs: list[str] = []
    authority = "complete"

    if not mail_complete:
        reasons.append("mailbox lookup is incomplete")
        authority = "partial"
    if not slack_complete:
        reasons.append("slack lookup is incomplete")
        authority = "partial"
    if conflicts:
        reasons.extend(sorted(conflicts))
        authority = "unknown"

    age = requested_at - generated_at
    if age > timedelta(seconds=policy.max_evidence_age_seconds):
        reasons.append("evidence snapshot is stale")
        authority = "partial" if authority == "complete" else authority
    if generated_at - requested_at > timedelta(seconds=policy.max_future_skew_seconds):
        reasons.append("evidence snapshot is implausibly future-dated")
        authority = "unknown"

    if any(row.observed_at > generated_at for row in mail_rows):
        reasons.append("mailbox evidence contains a row after the snapshot boundary")
        authority = "unknown"
    if any(row.observed_at > generated_at for row in slack_rows):
        reasons.append("slack evidence contains a row after the snapshot boundary")
        authority = "unknown"

    relevant_mail = [row for row in mail_rows if row.counterparty == recipient and row.observed_at <= generated_at]
    relevant_slack = [row for row in slack_rows if row.recipient == recipient and row.observed_at <= generated_at]

    hard_dnr = sorted((row for row in relevant_slack if row.kind == "hard_dnr"), key=lambda row: (row.observed_at, row.event_id))
    if hard_dnr:
        reasons.append("hard do-not-resend evidence exists for this recipient")
        matched_refs.extend(_row_ref("slack", row.event_id) for row in hard_dnr)

    outbound_mail = [row for row in relevant_mail if row.direction == "outbound"]
    inbound_mail = [row for row in relevant_mail if row.direction == "inbound"]
    sent_slack = [row for row in relevant_slack if row.kind == "sent"]

    outbound_points: list[tuple[datetime, str, str | None]] = []
    for row in outbound_mail:
        outbound_points.append((row.observed_at, _row_ref("mail", row.message_id), row.offer_id))
    for row in sent_slack:
        outbound_points.append((row.observed_at, _row_ref("slack", row.event_id), row.offer_id))
    outbound_points.sort(key=lambda item: (item[0], item[1]))
    inbound_mail.sort(key=lambda row: (row.observed_at, row.message_id))

    latest_outbound = outbound_points[-1] if outbound_points else None
    latest_inbound = inbound_mail[-1] if inbound_mail else None
    newer_inbound = bool(latest_inbound and (latest_outbound is None or latest_inbound.observed_at > latest_outbound[0]))

    same_offer = [point for point in outbound_points if point[2] == offer_id]
    if same_offer:
        matched_refs.extend(point[1] for point in same_offer)
    if latest_outbound is not None:
        matched_refs.append(latest_outbound[1])
    if latest_inbound is not None:
        matched_refs.append(_row_ref("mail", latest_inbound.message_id))

    # Decision precedence deliberately keeps hard DNR and evidence-integrity failures above all send authority.
    if hard_dnr:
        decision = "DO_NOT_RESEND"
    elif authority != "complete" or reasons:
        decision = "HOLD"
    elif newer_inbound:
        decision = "REPLY_ONLY"
        reasons.append("recipient inbound is newer than the latest outbound; reply is allowed but net-new send is not")
    elif same_offer:
        decision = "DO_NOT_RESEND"
        reasons.append("the same offer already has outbound evidence")
    elif latest_outbound is not None:
        cooldown = timedelta(days=policy.cross_offer_cooldown_days)
        if generated_at - latest_outbound[0] < cooldown:
            decision = "HOLD"
            reasons.append("another outbound to this recipient is still inside the cross-offer cooldown")
        else:
            decision = "ALLOW_NEW"
            reasons.append("prior outbound is outside the cross-offer cooldown and no same-offer send is recorded")
    else:
        decision = "ALLOW_NEW"
        reasons.append("complete evidence contains no prior outbound to this recipient")

    assert decision in DECISIONS
    refs = sorted(set(matched_refs))
    payload = {
        "schema_version": RECEIPT_SCHEMA,
        "intent": {
            "intent_id": intent["intent_id"],
            "recipient": recipient,
            "offer_id": offer_id,
            "requested_at": format_time(requested_at),
            "route_kind": "email",
        },
        "evidence": {
            "generated_at": format_time(generated_at),
            "mailbox_complete": mail_complete,
            "mailbox_query_id": mail_query_id,
            "slack_complete": slack_complete,
            "slack_query_id": slack_query_id,
            "intent_sha256": intent_sha256 or digest_object(intent_raw),
            "evidence_sha256": evidence_sha256 or digest_object(evidence_raw),
            "matched_refs": refs,
        },
        "policy": {
            "cross_offer_cooldown_days": policy.cross_offer_cooldown_days,
            "max_evidence_age_seconds": policy.max_evidence_age_seconds,
            "max_future_skew_seconds": policy.max_future_skew_seconds,
        },
        "decision": decision,
        "authority": authority,
        "reasons": reasons,
        "latest_outbound_at": format_time(latest_outbound[0]) if latest_outbound else None,
        "latest_inbound_at": format_time(latest_inbound.observed_at) if latest_inbound else None,
        "reply_message_id": latest_inbound.message_id if decision == "REPLY_ONLY" and latest_inbound else None,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": digest_object(payload)}


def _same_file_or_alias(a: Path, b: Path) -> bool:
    try:
        if a.resolve(strict=False) == b.resolve(strict=False):
            return True
    except OSError as exc:
        raise GuardError(f"cannot resolve path identity: {exc}") from exc
    try:
        return os.path.samefile(a, b)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise GuardError(f"cannot compare path identity: {exc}") from exc


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.stage-", dir=str(path.parent))
    except OSError as exc:
        raise GuardError(f"cannot stage output {path}: {exc}") from exc
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        if os.name != "nt":
            dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
    except OSError as exc:
        try:
            if os.path.lexists(temp):
                temp.unlink()
        finally:
            raise GuardError(f"cannot publish output {path}: {exc}") from exc


def _load_raw(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GuardError(f"cannot read {label} {path}: {exc}") from exc
    return raw, parse_json_bytes(raw, label)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline fail-closed outbound email send authority gate")
    parser.add_argument("--intent", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if _same_file_or_alias(args.intent, args.evidence):
            raise GuardError("intent and evidence must be distinct files")
        if args.out is not None:
            if _same_file_or_alias(args.out, args.intent) or _same_file_or_alias(args.out, args.evidence):
                raise GuardError("output must not alias an input")
        intent_raw, intent_obj = _load_raw(args.intent, "intent")
        evidence_raw, evidence_obj = _load_raw(args.evidence, "evidence")
        receipt = evaluate(intent_obj, evidence_obj, intent_sha256=digest_bytes(intent_raw), evidence_sha256=digest_bytes(evidence_raw))
        encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        if args.out is None:
            sys.stdout.buffer.write(encoded)
        else:
            _atomic_write(args.out, encoded)
        return {"ALLOW_NEW": 0, "REPLY_ONLY": 3, "HOLD": 4, "DO_NOT_RESEND": 5}[receipt["payload"]["decision"]]
    except GuardError as exc:
        print(f"outbound-send-guard: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
