#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from .guard import GuardError, canonical_bytes, format_time, normalize_email, parse_time
except ImportError:
    from guard import GuardError, canonical_bytes, format_time, normalize_email, parse_time

MAILBOX_SCHEMA = "outbound-mailbox-export/v1"
SLACK_SCHEMA = "outbound-slack-export/v1"
EVIDENCE_SCHEMA = "outbound-send-evidence/v1"
RECEIPT_SCHEMA = "outbound-send-evidence-compile-receipt/v1"
MAX_ROWS = 10_000
DEFAULT_POLICY = {
    "cross_offer_cooldown_days": 30,
    "max_evidence_age_seconds": 900,
    "max_future_skew_seconds": 300,
}


class CompileError(GuardError):
    pass


@dataclass(frozen=True)
class SourceMeta:
    capture_id: str
    recipient: str
    as_of: datetime
    collected_at: datetime
    query_id: str


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CompileError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def parse_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CompileError(f"{label} must be UTF-8 JSON") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CompileError(f"{label} contains non-finite number {token}")
            ),
        )
    except CompileError:
        raise
    except json.JSONDecodeError as exc:
        raise CompileError(f"{label} is not valid JSON: {exc.msg}") from exc
    return _dict(value, label)


def _dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CompileError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise CompileError(f"{label} must be a list")
    if len(value) > MAX_ROWS:
        raise CompileError(f"{label} exceeds {MAX_ROWS} rows")
    return value


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise CompileError(f"{label} must be a boolean")
    return value


def _int(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int:
        raise CompileError(f"{label} must be an integer")
    if not low <= value <= high:
        raise CompileError(f"{label} must be between {low} and {high}")
    return value


def _text(value: Any, label: str, max_len: int = 512) -> str:
    if type(value) is not str:
        raise CompileError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise CompileError(f"{label} must not be empty")
    if len(text) > max_len:
        raise CompileError(f"{label} exceeds {max_len} characters")
    if any(ord(ch) < 32 for ch in text):
        raise CompileError(f"{label} contains control characters")
    return text


def _optional_text(value: Any, label: str, max_len: int = 512) -> str | None:
    if value is None:
        return None
    return _text(value, label, max_len)


def _only(obj: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise CompileError(f"{label} has unknown fields: {', '.join(sorted(extra))}")


def _source_meta(raw: dict[str, Any], *, label: str, schema: str, continuation_field: str) -> SourceMeta:
    allowed = {
        "schema_version", "capture_id", "recipient", "as_of", "collected_at",
        "query_id", "complete", continuation_field,
        "messages" if label == "mailbox" else "events",
    }
    _only(raw, allowed, label)
    if raw.get("schema_version") != schema:
        raise CompileError(f"{label}.schema_version must equal {schema!r}")
    if not _bool(raw.get("complete"), f"{label}.complete"):
        raise CompileError(f"{label} export is incomplete")
    if raw.get(continuation_field) is not None:
        raise CompileError(f"{label}.{continuation_field} must be null for a complete export")
    as_of = parse_time(raw.get("as_of"), f"{label}.as_of")
    collected_at = parse_time(raw.get("collected_at"), f"{label}.collected_at")
    if collected_at < as_of:
        raise CompileError(f"{label}.collected_at must not precede as_of")
    return SourceMeta(
        capture_id=_text(raw.get("capture_id"), f"{label}.capture_id", 200),
        recipient=normalize_email(raw.get("recipient"), f"{label}.recipient"),
        as_of=as_of,
        collected_at=collected_at,
        query_id=_text(raw.get("query_id"), f"{label}.query_id", 200),
    )


def _dedupe(rows: Iterable[dict[str, Any]], key: str, label: str) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = row[key]
        previous = seen.get(row_id)
        if previous is not None and previous != row:
            raise CompileError(f"{label} {key} {row_id} has conflicting rows")
        if previous is None:
            seen[row_id] = row
    return list(seen.values())


def _mailbox_rows(raw: dict[str, Any], meta: SourceMeta) -> tuple[list[dict[str, Any]], int]:
    parsed: list[dict[str, Any]] = []
    original = _list(raw.get("messages"), "mailbox.messages")
    for index, item in enumerate(original):
        row = _dict(item, f"mailbox.messages[{index}]")
        _only(row, {"message_id", "direction", "counterparty", "observed_at", "provider_state", "offer_id"}, f"mailbox.messages[{index}]")
        message_id = _text(row.get("message_id"), f"mailbox.messages[{index}].message_id", 256)
        direction = _text(row.get("direction"), f"mailbox.messages[{index}].direction", 16)
        if direction not in {"inbound", "outbound"}:
            raise CompileError(f"mailbox.messages[{index}].direction must be inbound or outbound")
        state = _text(row.get("provider_state"), f"mailbox.messages[{index}].provider_state", 16)
        expected_state = "received" if direction == "inbound" else "sent"
        if state != expected_state:
            raise CompileError(
                f"mailbox.messages[{index}].provider_state must equal {expected_state!r} for {direction} evidence"
            )
        counterparty = normalize_email(row.get("counterparty"), f"mailbox.messages[{index}].counterparty")
        if counterparty != meta.recipient:
            raise CompileError(f"mailbox.messages[{index}] is outside recipient scope")
        observed_at = parse_time(row.get("observed_at"), f"mailbox.messages[{index}].observed_at")
        if observed_at > meta.as_of:
            raise CompileError(f"mailbox.messages[{index}] is after the as_of boundary")
        parsed.append({
            "message_id": message_id,
            "direction": direction,
            "counterparty": counterparty,
            "observed_at": format_time(observed_at),
            "offer_id": _optional_text(row.get("offer_id"), f"mailbox.messages[{index}].offer_id", 200),
        })
    deduped = _dedupe(parsed, "message_id", "mailbox")
    deduped.sort(key=lambda row: (row["observed_at"], row["message_id"]))
    return deduped, len(original) - len(deduped)


def _slack_rows(raw: dict[str, Any], meta: SourceMeta) -> tuple[list[dict[str, Any]], int]:
    parsed: list[dict[str, Any]] = []
    original = _list(raw.get("events"), "slack.events")
    for index, item in enumerate(original):
        row = _dict(item, f"slack.events[{index}]")
        _only(row, {"event_id", "kind", "recipient", "observed_at", "offer_id", "provider_message_id"}, f"slack.events[{index}]")
        event_id = _text(row.get("event_id"), f"slack.events[{index}].event_id", 256)
        kind = _text(row.get("kind"), f"slack.events[{index}].kind", 32)
        if kind not in {"lead", "sent", "hard_dnr"}:
            raise CompileError(f"slack.events[{index}].kind must be lead, sent, or hard_dnr")
        recipient = normalize_email(row.get("recipient"), f"slack.events[{index}].recipient")
        if recipient != meta.recipient:
            raise CompileError(f"slack.events[{index}] is outside recipient scope")
        observed_at = parse_time(row.get("observed_at"), f"slack.events[{index}].observed_at")
        if observed_at > meta.as_of:
            raise CompileError(f"slack.events[{index}] is after the as_of boundary")
        provider_message_id = _optional_text(row.get("provider_message_id"), f"slack.events[{index}].provider_message_id", 256)
        if provider_message_id is not None and kind != "sent":
            raise CompileError(f"slack.events[{index}].provider_message_id is only valid for sent events")
        parsed.append({
            "event_id": event_id,
            "kind": kind,
            "recipient": recipient,
            "observed_at": format_time(observed_at),
            "offer_id": _optional_text(row.get("offer_id"), f"slack.events[{index}].offer_id", 200),
            "provider_message_id": provider_message_id,
        })
    deduped = _dedupe(parsed, "event_id", "slack")
    deduped.sort(key=lambda row: (row["observed_at"], row["event_id"]))
    return deduped, len(original) - len(deduped)


def _policy(raw: dict[str, Any] | None) -> dict[str, int]:
    if raw is None:
        return dict(DEFAULT_POLICY)
    obj = _dict(raw, "policy")
    _only(obj, set(DEFAULT_POLICY), "policy")
    return {
        "cross_offer_cooldown_days": _int(obj.get("cross_offer_cooldown_days", 30), "policy.cross_offer_cooldown_days", 0, 3650),
        "max_evidence_age_seconds": _int(obj.get("max_evidence_age_seconds", 900), "policy.max_evidence_age_seconds", 0, 604800),
        "max_future_skew_seconds": _int(obj.get("max_future_skew_seconds", 300), "policy.max_future_skew_seconds", 0, 86400),
    }


def compile_evidence(mailbox_raw: dict[str, Any], slack_raw: dict[str, Any], policy_raw: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    mailbox_meta = _source_meta(mailbox_raw, label="mailbox", schema=MAILBOX_SCHEMA, continuation_field="next_page_token")
    slack_meta = _source_meta(slack_raw, label="slack", schema=SLACK_SCHEMA, continuation_field="next_cursor")
    if mailbox_meta.capture_id != slack_meta.capture_id:
        raise CompileError("mailbox and slack capture_id must match")
    if mailbox_meta.recipient != slack_meta.recipient:
        raise CompileError("mailbox and slack recipient scopes must match")
    if mailbox_meta.as_of != slack_meta.as_of:
        raise CompileError("mailbox and slack as_of boundaries must match")

    mailbox_rows, mailbox_deduped = _mailbox_rows(mailbox_raw, mailbox_meta)
    slack_rows, slack_deduped = _slack_rows(slack_raw, slack_meta)
    mailbox_by_id = {row["message_id"]: row for row in mailbox_rows}
    for row in slack_rows:
        provider_id = row["provider_message_id"]
        if row["kind"] != "sent" or provider_id is None:
            continue
        provider = mailbox_by_id.get(provider_id)
        if provider is None or provider["direction"] != "outbound":
            raise CompileError(
                f"slack sent event {row['event_id']} references provider message {provider_id} absent from complete outbound mailbox evidence"
            )
        if row["offer_id"] is not None and provider["offer_id"] is not None and row["offer_id"] != provider["offer_id"]:
            raise CompileError(f"slack sent event {row['event_id']} conflicts with provider offer_id")

    evidence = {
        "schema_version": EVIDENCE_SCHEMA,
        "generated_at": format_time(mailbox_meta.as_of),
        "mailbox": {
            "complete": True,
            "query_id": mailbox_meta.query_id,
            "messages": mailbox_rows,
        },
        "slack": {
            "complete": True,
            "query_id": slack_meta.query_id,
            "events": slack_rows,
        },
        "policy": _policy(policy_raw),
    }
    summary = {
        "capture_id": mailbox_meta.capture_id,
        "recipient": mailbox_meta.recipient,
        "as_of": format_time(mailbox_meta.as_of),
        "mailbox_collected_at": format_time(mailbox_meta.collected_at),
        "slack_collected_at": format_time(slack_meta.collected_at),
        "mailbox_query_id": mailbox_meta.query_id,
        "slack_query_id": slack_meta.query_id,
        "mailbox_rows": len(mailbox_rows),
        "slack_rows": len(slack_rows),
        "mailbox_exact_duplicates_collapsed": mailbox_deduped,
        "slack_exact_duplicates_collapsed": slack_deduped,
    }
    return evidence, summary


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def compile_with_receipt(mailbox_raw_bytes: bytes, slack_raw_bytes: bytes, policy_raw_bytes: bytes | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    mailbox_obj = parse_json_bytes(mailbox_raw_bytes, "mailbox")
    slack_obj = parse_json_bytes(slack_raw_bytes, "slack")
    policy_obj = parse_json_bytes(policy_raw_bytes, "policy") if policy_raw_bytes is not None else None
    evidence, summary = compile_evidence(mailbox_obj, slack_obj, policy_obj)
    evidence_raw = canonical_bytes(evidence)
    receipt_payload = {
        "schema_version": RECEIPT_SCHEMA,
        "summary": summary,
        "sources": {
            "mailbox_sha256": _sha(mailbox_raw_bytes),
            "slack_sha256": _sha(slack_raw_bytes),
            "policy_sha256": _sha(policy_raw_bytes) if policy_raw_bytes is not None else None,
        },
        "evidence_sha256": _sha(evidence_raw),
        "side_effects_authorized": False,
    }
    receipt = {"payload": receipt_payload, "receipt_sha256": _sha(canonical_bytes(receipt_payload))}
    return evidence, receipt


def _aliases(a: Path, b: Path) -> bool:
    try:
        if a.resolve(strict=False) == b.resolve(strict=False):
            return True
    except OSError as exc:
        raise CompileError(f"cannot resolve path identity: {exc}") from exc
    try:
        return os.path.samefile(a, b)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise CompileError(f"cannot compare path identity: {exc}") from exc


def _preflight_paths(inputs: list[tuple[str, Path]], outputs: list[tuple[str, Path]]) -> None:
    all_paths = inputs + outputs
    for index, (left_name, left) in enumerate(all_paths):
        for right_name, right in all_paths[index + 1 :]:
            if _aliases(left, right):
                raise CompileError(f"{left_name} and {right_name} must be distinct paths")
    for name, path in outputs:
        if path.exists() and path.is_dir():
            raise CompileError(f"{name} must not be a directory")


def _stage(path: Path, raw: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.stage-", dir=str(path.parent))
    except OSError as exc:
        raise CompileError(f"cannot stage {path}: {exc}") from exc
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        return temp
    except OSError as exc:
        try:
            if os.path.lexists(temp):
                temp.unlink()
        finally:
            raise CompileError(f"cannot write staged output {path}: {exc}") from exc


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        raise CompileError(f"cannot open output directory {path} for fsync: {exc}") from exc
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _temp_backup(path: Path) -> Path:
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.backup-", dir=str(path.parent))
        os.close(fd)
        os.unlink(name)
        return Path(name)
    except OSError as exc:
        raise CompileError(f"cannot reserve backup path for {path}: {exc}") from exc


def _publish_pair(items: list[tuple[Path, bytes]]) -> None:
    stages: list[tuple[Path, Path]] = []
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    parents: list[Path] = []
    try:
        for path, raw in items:
            stages.append((path, _stage(path, raw)))
            if path.parent not in parents:
                parents.append(path.parent)
        try:
            for path, _ in items:
                if os.path.lexists(path):
                    backup = _temp_backup(path)
                    os.replace(path, backup)
                    backups[path] = backup
            for parent in parents:
                _fsync_dir(parent)
            for path, stage in stages:
                os.replace(stage, path)
                published.append(path)
            for parent in parents:
                _fsync_dir(parent)
        except Exception as exc:
            errors: list[str] = []
            for path in reversed(published):
                try:
                    if os.path.lexists(path):
                        path.unlink()
                except OSError as rollback_exc:
                    errors.append(f"remove {path}: {rollback_exc}")
            for path, backup in backups.items():
                try:
                    if os.path.lexists(backup):
                        os.replace(backup, path)
                except OSError as rollback_exc:
                    errors.append(f"restore {path}: {rollback_exc}")
            detail = f"; rollback errors: {'; '.join(errors)}" if errors else ""
            if isinstance(exc, CompileError):
                raise CompileError(f"{exc}{detail}") from exc
            raise CompileError(f"output publication failed: {exc}{detail}") from exc
        for backup in backups.values():
            try:
                if os.path.lexists(backup):
                    backup.unlink()
            except OSError as exc:
                raise CompileError(f"cannot clean backup {backup}: {exc}") from exc
        for parent in parents:
            _fsync_dir(parent)
    finally:
        for _, stage in stages:
            try:
                if os.path.lexists(stage):
                    stage.unlink()
            except OSError:
                pass


def _read(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CompileError(f"cannot read {label} {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile complete mailbox + Slack exports into outbound send evidence")
    parser.add_argument("--mailbox", required=True, type=Path)
    parser.add_argument("--slack", required=True, type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--evidence-out", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        inputs = [("mailbox", args.mailbox), ("slack", args.slack)]
        if args.policy is not None:
            inputs.append(("policy", args.policy))
        outputs = [("evidence_out", args.evidence_out), ("receipt_out", args.receipt_out)]
        _preflight_paths(inputs, outputs)
        mailbox_raw = _read(args.mailbox, "mailbox")
        slack_raw = _read(args.slack, "slack")
        policy_raw = _read(args.policy, "policy") if args.policy is not None else None
        evidence, receipt = compile_with_receipt(mailbox_raw, slack_raw, policy_raw)
        _publish_pair([
            (args.evidence_out, json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"),
            (args.receipt_out, json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"),
        ])
        return 0
    except GuardError as exc:
        print(f"outbound-send-evidence-compiler: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
