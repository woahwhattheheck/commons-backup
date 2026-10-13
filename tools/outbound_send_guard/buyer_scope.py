#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from . import guard
except ImportError:  # pragma: no cover - direct script execution
    import guard  # type: ignore

SCOPE_SCHEMA = "outbound-send-buyer-scope/v1"
RECEIPT_SCHEMA = "outbound-send-buyer-scope-receipt/v2"
MAX_SCOPE_MEMBERS = 100


class ScopeError(guard.GuardError):
    pass


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ScopeError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ScopeError(f"{label} must be a list")
    if not value:
        raise ScopeError(f"{label} must not be empty")
    if len(value) > MAX_SCOPE_MEMBERS:
        raise ScopeError(f"{label} exceeds {MAX_SCOPE_MEMBERS} members")
    return value


def _require_text(value: Any, label: str, *, max_len: int = 512) -> str:
    if type(value) is not str:
        raise ScopeError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise ScopeError(f"{label} must not be empty")
    if len(text) > max_len:
        raise ScopeError(f"{label} exceeds {max_len} characters")
    if any(ord(ch) < 32 for ch in text):
        raise ScopeError(f"{label} contains control characters")
    return text


def _require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ScopeError(f"{label} must be a boolean")
    return value


def _snapshot_canonical_object(value: Any, label: str) -> dict[str, Any]:
    """Detach one caller-owned parsed object into a canonical JSON generation."""
    obj = _require_dict(value, label)
    try:
        raw = guard.canonical_bytes(obj)
    except (TypeError, ValueError) as exc:
        raise ScopeError(f"{label} is not canonical JSON") from exc
    return guard.parse_json_bytes(raw, f"{label} canonical snapshot")


def _parse_scope(raw: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    allowed = {"schema_version", "scope_id", "members"}
    unknown = set(raw) - allowed
    if unknown:
        raise ScopeError(f"buyer scope has unknown fields: {', '.join(sorted(unknown))}")
    if raw.get("schema_version") != SCOPE_SCHEMA:
        raise ScopeError(f"buyer scope schema_version must equal {SCOPE_SCHEMA!r}")
    scope_id = _require_text(raw.get("scope_id"), "buyer_scope.scope_id", max_len=200)

    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(_require_list(raw.get("members"), "buyer_scope.members")):
        obj = _require_dict(item, f"buyer_scope.members[{index}]")
        allowed_member = {
            "email",
            "mailbox_complete",
            "mailbox_query_id",
            "slack_complete",
            "slack_query_id",
        }
        extra = set(obj) - allowed_member
        if extra:
            raise ScopeError(
                f"buyer_scope.members[{index}] has unknown fields: {', '.join(sorted(extra))}"
            )
        email = guard.normalize_email(obj.get("email"), f"buyer_scope.members[{index}].email")
        if email in seen:
            raise ScopeError(f"buyer_scope.members contains duplicate normalized email: {email}")
        seen.add(email)
        members.append(
            {
                "email": email,
                "mailbox_complete": _require_bool(
                    obj.get("mailbox_complete"),
                    f"buyer_scope.members[{index}].mailbox_complete",
                ),
                "mailbox_query_id": _require_text(
                    obj.get("mailbox_query_id"),
                    f"buyer_scope.members[{index}].mailbox_query_id",
                    max_len=200,
                ),
                "slack_complete": _require_bool(
                    obj.get("slack_complete"),
                    f"buyer_scope.members[{index}].slack_complete",
                ),
                "slack_query_id": _require_text(
                    obj.get("slack_query_id"),
                    f"buyer_scope.members[{index}].slack_query_id",
                    max_len=200,
                ),
            }
        )
    members.sort(key=lambda member: member["email"])
    return scope_id, members


def _effective_complete(base_value: Any, member_values: list[bool], label: str) -> bool:
    base = _require_bool(base_value, label)
    return base and all(member_values)


def _rebind_evidence(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    recipient = guard.normalize_email(intent_raw.get("recipient"), "intent.recipient")
    member_emails = {member["email"] for member in members}
    if recipient not in member_emails:
        raise ScopeError("intent.recipient must be a declared buyer-scope member")

    evidence = copy.deepcopy(_require_dict(evidence_raw, "evidence"))
    mailbox = _require_dict(evidence.get("mailbox"), "evidence.mailbox")
    slack = _require_dict(evidence.get("slack"), "evidence.slack")

    mailbox["complete"] = _effective_complete(
        mailbox.get("complete"),
        [member["mailbox_complete"] for member in members],
        "evidence.mailbox.complete",
    )
    slack["complete"] = _effective_complete(
        slack.get("complete"),
        [member["slack_complete"] for member in members],
        "evidence.slack.complete",
    )

    messages = mailbox.get("messages")
    if type(messages) is not list:
        raise ScopeError("evidence.mailbox.messages must be a list")
    for index, row_raw in enumerate(messages):
        row = _require_dict(row_raw, f"evidence.mailbox.messages[{index}]")
        if "counterparty" not in row:
            continue
        normalized = guard.normalize_email(
            row.get("counterparty"),
            f"evidence.mailbox.messages[{index}].counterparty",
        )
        if normalized in member_emails:
            row["counterparty"] = recipient

    events = slack.get("events")
    if type(events) is not list:
        raise ScopeError("evidence.slack.events must be a list")
    for index, row_raw in enumerate(events):
        row = _require_dict(row_raw, f"evidence.slack.events[{index}]")
        if "recipient" not in row:
            continue
        normalized = guard.normalize_email(
            row.get("recipient"),
            f"evidence.slack.events[{index}].recipient",
        )
        if normalized in member_emails:
            row["recipient"] = recipient

    return evidence


def _evaluate(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    scope_raw: dict[str, Any],
    *,
    raw_bytes: tuple[bytes, bytes, bytes] | None,
) -> dict[str, Any]:
    scope_id, members = _parse_scope(_require_dict(scope_raw, "buyer scope"))
    scoped_evidence = _rebind_evidence(intent_raw, evidence_raw, members)
    core = guard.evaluate(intent_raw, scoped_evidence)

    byte_custody = None
    if raw_bytes is not None:
        if type(raw_bytes) is not tuple or len(raw_bytes) != 3 or any(type(item) is not bytes for item in raw_bytes):
            raise ScopeError("internal raw-byte custody must contain exactly three byte strings")
        parsed_sources = (
            guard.parse_json_bytes(raw_bytes[0], "intent byte custody"),
            guard.parse_json_bytes(raw_bytes[1], "evidence byte custody"),
            guard.parse_json_bytes(raw_bytes[2], "buyer scope byte custody"),
        )
        evaluated_sources = (intent_raw, evidence_raw, scope_raw)
        if any(
            guard.canonical_bytes(parsed) != guard.canonical_bytes(evaluated)
            for parsed, evaluated in zip(parsed_sources, evaluated_sources)
        ):
            raise ScopeError("raw-byte custody does not match evaluated source objects")
        byte_custody = {
            "mode": "exact_consumed_bytes",
            "intent_sha256": guard.digest_bytes(raw_bytes[0]),
            "evidence_sha256": guard.digest_bytes(raw_bytes[1]),
            "scope_sha256": guard.digest_bytes(raw_bytes[2]),
        }

    payload = {
        "schema_version": RECEIPT_SCHEMA,
        "buyer_scope": {
            "scope_id": scope_id,
            "members": members,
        },
        "source": {
            "custody_mode": (
                "exact_consumed_bytes" if byte_custody is not None else "canonical_objects"
            ),
            "intent_object_sha256": guard.digest_object(intent_raw),
            "evidence_object_sha256": guard.digest_object(evidence_raw),
            "scope_object_sha256": guard.digest_object(scope_raw),
            "scoped_evidence_object_sha256": guard.digest_object(scoped_evidence),
            "byte_custody": byte_custody,
        },
        "core_receipt_sha256": core["receipt_sha256"],
        "core": core["payload"],
        "decision": core["payload"]["decision"],
        "authority": core["payload"]["authority"],
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": guard.digest_object(payload)}


def evaluate(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    scope_raw: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one detached canonical generation of each caller-owned object.

    This API proves canonical object integrity only. It intentionally cannot accept
    externally supplied source digests and therefore cannot claim raw-byte custody.
    """
    intent_snapshot = _snapshot_canonical_object(intent_raw, "intent")
    evidence_snapshot = _snapshot_canonical_object(evidence_raw, "evidence")
    scope_snapshot = _snapshot_canonical_object(scope_raw, "buyer scope")
    return _evaluate(
        intent_snapshot,
        evidence_snapshot,
        scope_snapshot,
        raw_bytes=None,
    )


def evaluate_bytes(
    intent_bytes: bytes,
    evidence_bytes: bytes,
    scope_bytes: bytes,
) -> dict[str, Any]:
    """Strict-parse and evaluate the exact bytes whose digests enter the receipt."""
    if type(intent_bytes) is not bytes:
        raise ScopeError("intent bytes must be bytes")
    if type(evidence_bytes) is not bytes:
        raise ScopeError("evidence bytes must be bytes")
    if type(scope_bytes) is not bytes:
        raise ScopeError("buyer scope bytes must be bytes")

    intent = guard.parse_json_bytes(intent_bytes, "intent")
    evidence = guard.parse_json_bytes(evidence_bytes, "evidence")
    scope = guard.parse_json_bytes(scope_bytes, "buyer scope")
    return _evaluate(
        intent,
        evidence,
        scope,
        raw_bytes=(intent_bytes, evidence_bytes, scope_bytes),
    )


def _same_file_or_alias(a: Path, b: Path) -> bool:
    try:
        if a.resolve(strict=False) == b.resolve(strict=False):
            return True
    except OSError as exc:
        raise ScopeError(f"cannot resolve path identity: {exc}") from exc
    try:
        return os.path.samefile(a, b)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ScopeError(f"cannot compare path identity: {exc}") from exc


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.stage-", dir=str(path.parent))
    except OSError as exc:
        raise ScopeError(f"cannot stage output {path}: {exc}") from exc
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
            raise ScopeError(f"cannot publish output {path}: {exc}") from exc


def _load_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ScopeError(f"cannot read {label} {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explicit buyer-scope companion for the outbound send guard"
    )
    parser.add_argument("--intent", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--scope", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    try:
        inputs = [args.intent, args.evidence, args.scope]
        for index, first in enumerate(inputs):
            for second in inputs[index + 1 :]:
                if _same_file_or_alias(first, second):
                    raise ScopeError("intent, evidence, and scope must be distinct files")
        if args.out is not None and any(_same_file_or_alias(args.out, value) for value in inputs):
            raise ScopeError("output must not alias an input")

        intent_bytes = _load_bytes(args.intent, "intent")
        evidence_bytes = _load_bytes(args.evidence, "evidence")
        scope_bytes = _load_bytes(args.scope, "buyer scope")
        receipt = evaluate_bytes(intent_bytes, evidence_bytes, scope_bytes)
        encoded = (
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
            + b"\n"
        )
        if args.out is None:
            sys.stdout.buffer.write(encoded)
        else:
            _atomic_write(args.out, encoded)
        return {
            "ALLOW_NEW": 0,
            "REPLY_ONLY": 3,
            "HOLD": 4,
            "DO_NOT_RESEND": 5,
        }[receipt["payload"]["decision"]]
    except guard.GuardError as exc:
        print(f"outbound-buyer-scope-guard: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())