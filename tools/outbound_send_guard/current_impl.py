#!/usr/bin/env python3
"""Process-clock current authority for the deterministic outbound send guard."""
from __future__ import annotations

import argparse
import inspect
import json
import os
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from . import guard
except ImportError:  # pragma: no cover - direct script execution
    import guard  # type: ignore

CURRENT_RECEIPT_SCHEMA = "outbound-send-guard-current-receipt/v1"
HISTORICAL_RECEIPT_SCHEMA = "outbound-send-guard-historical-receipt/v1"
CURRENT_VERIFICATION_SCHEMA = "outbound-send-guard-current-verification/v1"
POLICY_GENERATION = "outbound-send-guard-current-policy/1"
MODE_CURRENT = "CURRENT"
MODE_HISTORICAL = "HISTORICAL_INTEGRITY_ONLY"
MAX_EVIDENCE_AGE_SECONDS = 900
MAX_REQUEST_AGE_SECONDS = 900
MAX_FUTURE_SKEW_SECONDS = 300
POSITIVE_RECEIPT_TTL_SECONDS = 60
MAX_INPUT_BYTES = 2 * 1024 * 1024
DECISIONS = {"ALLOW_NEW", "REPLY_ONLY", "HOLD", "DO_NOT_RESEND"}
POSITIVE = {"ALLOW_NEW", "REPLY_ONLY"}


class CurrentGuardError(guard.GuardError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CurrentGuardError(f"{label} must be an object")
    return value


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise CurrentGuardError(f"{label} must be a boolean")
    return value


def _integer(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise CurrentGuardError(f"{label} must be an integer between {low} and {high}")
    return value


def _text(value: Any, label: str, limit: int = 256) -> str:
    if type(value) is not str:
        raise CurrentGuardError(f"{label} must be a string")
    value = value.strip()
    if not value or len(value) > limit or any(ord(ch) < 32 for ch in value):
        raise CurrentGuardError(f"{label} is malformed")
    return value


def _aware(value: datetime, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentGuardError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _snapshot(value: Any, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = guard.canonical_bytes(_dict(value, label))
    except (TypeError, ValueError) as exc:
        raise CurrentGuardError(f"{label} is not canonical JSON") from exc
    return guard.parse_json_bytes(raw, f"{label} canonical snapshot"), raw


def _parse_bytes(raw: bytes, label: str) -> dict[str, Any]:
    if type(raw) is not bytes:
        raise CurrentGuardError(f"{label} bytes must be bytes")
    if len(raw) > MAX_INPUT_BYTES:
        raise CurrentGuardError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
    return guard.parse_json_bytes(raw, label)


def _core(intent: dict[str, Any], evidence: dict[str, Any], ib: bytes, eb: bytes) -> dict[str, Any]:
    params = inspect.signature(guard.evaluate).parameters
    if {"intent_sha256", "evidence_sha256"} <= set(params):
        return guard.evaluate(
            intent,
            evidence,
            intent_sha256=guard.digest_bytes(ib),
            evidence_sha256=guard.digest_bytes(eb),
        )
    return guard.evaluate(intent, evidence)


def _core_parts(
    intent: dict[str, Any], evidence: dict[str, Any], ib: bytes, eb: bytes
) -> tuple[dict[str, Any], dict[str, Any], str]:
    receipt = _dict(_core(intent, evidence, ib, eb), "core receipt")
    core = _dict(receipt.get("payload"), "core payload")
    decision = _text(core.get("decision"), "core decision", 32)
    if decision not in DECISIONS:
        raise CurrentGuardError("unsupported core decision")
    if _bool(core.get("side_effects_authorized"), "core side_effects_authorized"):
        raise CurrentGuardError("core unexpectedly authorizes side effects")
    _text(receipt.get("receipt_sha256"), "core receipt digest", 64)
    return receipt, core, decision


def _policy(core: dict[str, Any]) -> dict[str, int]:
    raw = _dict(core.get("policy"), "core policy")
    declared_age = _integer(raw.get("max_evidence_age_seconds"), "max evidence age", 0, 604800)
    declared_future = _integer(raw.get("max_future_skew_seconds"), "max future skew", 0, 86400)
    return {
        "max_evidence_age_seconds": min(declared_age, MAX_EVIDENCE_AGE_SECONDS),
        "max_request_age_seconds": MAX_REQUEST_AGE_SECONDS,
        "max_future_skew_seconds": min(declared_future, MAX_FUTURE_SKEW_SECONDS),
        "positive_receipt_ttl_seconds": POSITIVE_RECEIPT_TTL_SECONDS,
    }


def _temporal_projection(
    intent: dict[str, Any],
    evidence: dict[str, Any],
    core: dict[str, Any],
    verifier_time: datetime,
) -> tuple[list[str], dict[str, int], datetime]:
    """Project temporal facts only; this helper cannot emit authority artifacts."""
    now = _aware(verifier_time, "verifier_time")
    requested = guard.parse_time(intent.get("requested_at"), "intent.requested_at")
    generated = guard.parse_time(evidence.get("generated_at"), "evidence.generated_at")
    policy = _policy(core)
    reasons: list[str] = []
    if now - generated > timedelta(seconds=policy["max_evidence_age_seconds"]):
        reasons.append("evidence snapshot is stale at verifier time")
    if generated - now > timedelta(seconds=policy["max_future_skew_seconds"]):
        reasons.append("evidence snapshot is future-dated relative to verifier time")
    if now - requested > timedelta(seconds=policy["max_request_age_seconds"]):
        reasons.append("intent request is stale at verifier time")
    if requested - now > timedelta(seconds=policy["max_future_skew_seconds"]):
        reasons.append("intent request is future-dated relative to verifier time")
    valid_until = min(
        generated + timedelta(seconds=policy["max_evidence_age_seconds"]),
        requested + timedelta(seconds=policy["max_request_age_seconds"]),
        now + timedelta(seconds=policy["positive_receipt_ttl_seconds"]),
    )
    return reasons, policy, valid_until


def _decision(core_decision: str, temporal_reasons: list[str]) -> tuple[str, list[str]]:
    if core_decision == "DO_NOT_RESEND":
        return "DO_NOT_RESEND", list(temporal_reasons)
    if temporal_reasons:
        return "HOLD", list(temporal_reasons)
    return core_decision, []


def _source_record(
    intent: dict[str, Any],
    evidence: dict[str, Any],
    ib: bytes,
    eb: bytes,
    source_mode: str,
) -> dict[str, Any]:
    if source_mode not in {"canonical_objects", "exact_consumed_bytes"}:
        raise CurrentGuardError("unsupported source mode")
    source: dict[str, Any] = {
        "custody_mode": source_mode,
        "intent_object_sha256": guard.digest_object(intent),
        "evidence_object_sha256": guard.digest_object(evidence),
        "byte_custody": None,
    }
    if source_mode == "exact_consumed_bytes":
        source["byte_custody"] = {
            "intent_sha256": guard.digest_bytes(ib),
            "evidence_sha256": guard.digest_bytes(eb),
        }
    return source


def _compile_current_owned_clock(
    intent: dict[str, Any],
    evidence: dict[str, Any],
    *,
    ib: bytes,
    eb: bytes,
    source_mode: str,
) -> dict[str, Any]:
    """Emit current authority using a clock sampled inside this function."""
    now = _aware(_utc_now(), "process UTC")
    core_receipt, core, core_decision = _core_parts(intent, evidence, ib, eb)
    temporal, effective_policy, valid_until = _temporal_projection(intent, evidence, core, now)
    decision, reasons = _decision(core_decision, temporal)
    clear = decision in POSITIVE and not temporal
    payload = {
        "schema_version": CURRENT_RECEIPT_SCHEMA,
        "mode": MODE_CURRENT,
        "verified_at": guard.format_time(now),
        "valid_until": guard.format_time(valid_until),
        "policy_generation": POLICY_GENERATION,
        "current_policy": effective_policy,
        "source": _source_record(intent, evidence, ib, eb, source_mode),
        "core_receipt_sha256": _text(core_receipt.get("receipt_sha256"), "core receipt digest", 64),
        "core": core,
        "historical_decision": core_decision,
        "core_authority": _text(core.get("authority"), "core authority", 32),
        "decision": decision,
        "reasons": reasons,
        "temporal_reasons": temporal,
        "current_preflight_clear": clear,
        "net_new_send_preflight_clear": clear and decision == "ALLOW_NEW",
        "reply_preflight_clear": clear and decision == "REPLY_ONLY",
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": guard.digest_object(payload)}


def compile_current(intent_raw: dict[str, Any], evidence_raw: dict[str, Any]) -> dict[str, Any]:
    intent, ib = _snapshot(intent_raw, "intent")
    evidence, eb = _snapshot(evidence_raw, "evidence")
    return _compile_current_owned_clock(
        intent, evidence, ib=ib, eb=eb, source_mode="canonical_objects"
    )


def compile_current_bytes(intent_bytes: bytes, evidence_bytes: bytes) -> dict[str, Any]:
    intent = _parse_bytes(intent_bytes, "intent")
    evidence = _parse_bytes(evidence_bytes, "evidence")
    return _compile_current_owned_clock(
        intent,
        evidence,
        ib=intent_bytes,
        eb=evidence_bytes,
        source_mode="exact_consumed_bytes",
    )


def compile_historical_at(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    *,
    historical_at: datetime,
) -> dict[str, Any]:
    """Compile deterministic historical integrity with no current-authority fields."""
    intent, ib = _snapshot(intent_raw, "intent")
    evidence, eb = _snapshot(evidence_raw, "evidence")
    historical_time = _aware(historical_at, "historical_at")
    core_receipt, core, core_decision = _core_parts(intent, evidence, ib, eb)
    temporal, effective_policy, valid_until = _temporal_projection(
        intent, evidence, core, historical_time
    )
    payload = {
        "schema_version": HISTORICAL_RECEIPT_SCHEMA,
        "mode": MODE_HISTORICAL,
        "evaluated_at": guard.format_time(historical_time),
        "would_be_valid_until": guard.format_time(valid_until),
        "policy_generation": POLICY_GENERATION,
        "current_policy": effective_policy,
        "source": _source_record(intent, evidence, ib, eb, "canonical_objects"),
        "core_receipt_sha256": _text(core_receipt.get("receipt_sha256"), "core receipt digest", 64),
        "core": core,
        "historical_decision": core_decision,
        "decision": "HOLD",
        "reasons": ["historical replay cannot authorize a current send"],
        "temporal_reasons_at_historical_time": temporal,
        "current_preflight_clear": False,
        "net_new_send_preflight_clear": False,
        "reply_preflight_clear": False,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": guard.digest_object(payload)}


def _receipt_current(value: dict[str, Any]) -> tuple[dict[str, Any], str]:
    value = _dict(value, "receipt")
    if set(value) != {"payload", "receipt_sha256"}:
        raise CurrentGuardError("receipt must contain exactly payload and receipt_sha256")
    payload = _dict(value.get("payload"), "receipt payload")
    digest = _text(value.get("receipt_sha256"), "receipt digest", 64)
    if digest != guard.digest_object(payload):
        raise CurrentGuardError("receipt digest mismatch")
    if (
        payload.get("schema_version") != CURRENT_RECEIPT_SCHEMA
        or payload.get("policy_generation") != POLICY_GENERATION
        or payload.get("mode") != MODE_CURRENT
    ):
        raise CurrentGuardError("unsupported current receipt schema, policy, or mode")
    if _bool(payload.get("side_effects_authorized"), "receipt side_effects_authorized"):
        raise CurrentGuardError("receipt unexpectedly authorizes side effects")
    return payload, digest


def _verify_current_owned_clock(
    intent: dict[str, Any],
    evidence: dict[str, Any],
    *,
    ib: bytes,
    eb: bytes,
    source_mode: str,
    receipt_raw: dict[str, Any],
) -> dict[str, Any]:
    """Verify current authority using a clock sampled inside this function."""
    payload, digest = _receipt_current(receipt_raw)
    now = _aware(_utc_now(), "process UTC")
    bound_at = guard.parse_time(payload.get("verified_at"), "receipt.verified_at")
    core_receipt, core, core_decision = _core_parts(intent, evidence, ib, eb)

    bound_temporal, bound_policy, bound_valid_until = _temporal_projection(
        intent, evidence, core, bound_at
    )
    bound_decision, bound_reasons = _decision(core_decision, bound_temporal)
    bound_clear = bound_decision in POSITIVE and not bound_temporal
    expected_payload = {
        "schema_version": CURRENT_RECEIPT_SCHEMA,
        "mode": MODE_CURRENT,
        "verified_at": guard.format_time(bound_at),
        "valid_until": guard.format_time(bound_valid_until),
        "policy_generation": POLICY_GENERATION,
        "current_policy": bound_policy,
        "source": _source_record(intent, evidence, ib, eb, source_mode),
        "core_receipt_sha256": _text(core_receipt.get("receipt_sha256"), "core receipt digest", 64),
        "core": core,
        "historical_decision": core_decision,
        "core_authority": _text(core.get("authority"), "core authority", 32),
        "decision": bound_decision,
        "reasons": bound_reasons,
        "temporal_reasons": bound_temporal,
        "current_preflight_clear": bound_clear,
        "net_new_send_preflight_clear": bound_clear and bound_decision == "ALLOW_NEW",
        "reply_preflight_clear": bound_clear and bound_decision == "REPLY_ONLY",
        "side_effects_authorized": False,
    }
    historical_valid = expected_payload == payload

    current_temporal, _, _ = _temporal_projection(intent, evidence, core, now)
    current_decision, _ = _decision(core_decision, current_temporal)
    current_clear = current_decision in POSITIVE and not current_temporal
    expired = now > guard.parse_time(payload.get("valid_until"), "receipt.valid_until")
    receipt_decision = _text(payload.get("decision"), "receipt decision", 32)
    semantic_match = receipt_decision == current_decision
    receipt_clear = _bool(payload.get("current_preflight_clear"), "receipt current_preflight_clear")
    valid = (
        historical_valid
        and not expired
        and semantic_match
        and receipt_clear
        and current_clear
    )
    reasons: list[str] = []
    if not historical_valid:
        reasons.append("receipt does not replay at its bound verifier time")
    if expired:
        reasons.append("receipt is expired")
    if not semantic_match:
        reasons.append("current decision no longer matches receipt decision")
    if not receipt_clear or not current_clear:
        reasons.append("receipt is not a current positive preflight")
    verification = {
        "schema_version": CURRENT_VERIFICATION_SCHEMA,
        "verified_receipt_sha256": digest,
        "checked_at": guard.format_time(now),
        "historical_valid": historical_valid,
        "expired": expired,
        "current_semantics_match": semantic_match,
        "receipt_decision": receipt_decision,
        "current_decision": current_decision,
        "current_preflight_valid": valid,
        "reasons": reasons,
        "side_effects_authorized": False,
    }
    return {"payload": verification, "receipt_sha256": guard.digest_object(verification)}


def verify_current(
    intent_raw: dict[str, Any], evidence_raw: dict[str, Any], receipt_raw: dict[str, Any]
) -> dict[str, Any]:
    intent, ib = _snapshot(intent_raw, "intent")
    evidence, eb = _snapshot(evidence_raw, "evidence")
    return _verify_current_owned_clock(
        intent,
        evidence,
        ib=ib,
        eb=eb,
        source_mode="canonical_objects",
        receipt_raw=receipt_raw,
    )


def verify_current_bytes(
    intent_bytes: bytes, evidence_bytes: bytes, receipt_bytes: bytes
) -> dict[str, Any]:
    intent = _parse_bytes(intent_bytes, "intent")
    evidence = _parse_bytes(evidence_bytes, "evidence")
    receipt = _parse_bytes(receipt_bytes, "receipt")
    return _verify_current_owned_clock(
        intent,
        evidence,
        ib=intent_bytes,
        eb=evidence_bytes,
        source_mode="exact_consumed_bytes",
        receipt_raw=receipt,
    )


def _alias(a: Path, b: Path) -> bool:
    try:
        return a.resolve(strict=False) == b.resolve(strict=False) or os.path.samefile(a, b)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise CurrentGuardError(f"cannot compare path identity: {exc}") from exc


def _read(path: Path, label: str) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CurrentGuardError(f"cannot open {label} {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > MAX_INPUT_BYTES
        ):
            raise CurrentGuardError(f"{label} must be one bounded regular single-link file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise CurrentGuardError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
        after = os.fstat(fd)

        def signature(value: os.stat_result) -> tuple[int, ...]:
            return (
                value.st_dev,
                value.st_ino,
                value.st_mode,
                value.st_nlink,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
            )

        if signature(before) != signature(after):
            raise CurrentGuardError(f"{label} generation changed during read")
        visible = os.lstat(path)
        if stat.S_ISLNK(visible.st_mode) or (visible.st_dev, visible.st_ino) != (
            after.st_dev,
            after.st_ino,
        ):
            raise CurrentGuardError(f"{label} path no longer names the consumed file")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise CurrentGuardError(f"cannot create output {path}: {exc}") from exc
    try:
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise CurrentGuardError(f"short write to output {path}")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _encode(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifier-clock-bound outbound send preflight")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--intent", required=True, type=Path)
        command.add_argument("--evidence", required=True, type=Path)
        if name == "verify":
            command.add_argument("--receipt", required=True, type=Path)
        command.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        inputs = [args.intent, args.evidence] + (
            [args.receipt] if args.command == "verify" else []
        )
        if any(_alias(a, b) for index, a in enumerate(inputs) for b in inputs[index + 1 :]):
            raise CurrentGuardError("input files must be distinct")
        if args.out is not None and any(_alias(args.out, item) for item in inputs):
            raise CurrentGuardError("output must not alias an input")
        ib = _read(args.intent, "intent")
        eb = _read(args.evidence, "evidence")
        if args.command == "compile":
            result = compile_current_bytes(ib, eb)
            code = {
                "ALLOW_NEW": 0,
                "REPLY_ONLY": 3,
                "HOLD": 4,
                "DO_NOT_RESEND": 5,
            }[result["payload"]["decision"]]
        else:
            result = verify_current_bytes(ib, eb, _read(args.receipt, "receipt"))
            code = (
                0
                if result["payload"]["current_preflight_valid"]
                else 5
                if result["payload"]["current_decision"] == "DO_NOT_RESEND"
                else 4
            )
        raw = _encode(result)
        if args.out is None:
            sys.stdout.buffer.write(raw)
        else:
            _write(args.out, raw)
        return code
    except (CurrentGuardError, guard.GuardError) as exc:
        print(f"outbound-send-current: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
