from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPORT_SCHEMA = "outbound-transport-reconcile-report/v2"
POLICY_SCHEMA = "outbound-transport-reconcile-policy/v1"
GMAIL_SCHEMA = "gmail-sent-snapshot/v1"
SLACK_SCHEMA = "slack-send-receipt-snapshot/v1"
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 10000
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-=]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReconcileError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise ReconcileError(f"non-finite JSON number is forbidden: {value}")


def _pairs_object(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ReconcileError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    if type(raw) is not str:
        raise ReconcileError("JSON input must be text")
    try:
        return json.loads(raw, object_pairs_hook=_pairs_object, parse_constant=_reject_constant)
    except ReconcileError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ReconcileError(f"invalid JSON: {exc}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_exact_keys(obj: Mapping[str, Any], expected: Iterable[str], where: str) -> None:
    if type(obj) is not dict:
        raise ReconcileError(f"{where} must be an object")
    want = set(expected)
    got = set(obj)
    if got != want:
        missing = sorted(want - got)
        extra = sorted(got - want)
        raise ReconcileError(f"{where} keys mismatch missing={missing} extra={extra}")


def _require_str(value: Any, where: str, *, max_len: int = 192) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise ReconcileError(f"{where} must be a non-empty string <= {max_len} chars")
    return value


def _require_id(value: Any, where: str) -> str:
    text = _require_str(value, where)
    if not _ID_RE.fullmatch(text):
        raise ReconcileError(f"{where} is not a safe opaque id")
    return text


def _require_sha256(value: Any, where: str) -> str:
    text = _require_str(value, where, max_len=64)
    if not _SHA256_RE.fullmatch(text):
        raise ReconcileError(f"{where} must be lowercase sha256")
    return text


def _require_bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ReconcileError(f"{where} must be a boolean")
    return value


def _require_positive_int(value: Any, where: str, *, maximum: int = 7 * 24 * 3600) -> int:
    if type(value) is not int or value <= 0 or value > maximum:
        raise ReconcileError(f"{where} must be a positive integer <= {maximum}")
    return value


def _parse_utc(value: Any, where: str) -> datetime:
    text = _require_str(value, where, max_len=20)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text):
        raise ReconcileError(f"{where} must be canonical UTC whole seconds")
    try:
        dt = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReconcileError(f"{where} is not a valid UTC timestamp") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise ReconcileError(f"{where} is not canonical UTC")
    return dt


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReconcileError("trusted as_of must be timezone-aware")
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_policy(policy: Mapping[str, Any]) -> Dict[str, Any]:
    _require_exact_keys(policy, {"schema", "max_snapshot_age_seconds"}, "policy")
    if policy["schema"] != POLICY_SCHEMA:
        raise ReconcileError("unsupported policy schema")
    return {
        "schema": POLICY_SCHEMA,
        "max_snapshot_age_seconds": _require_positive_int(
            policy["max_snapshot_age_seconds"], "policy.max_snapshot_age_seconds"
        ),
    }


def _normalize_gmail_record(value: Mapping[str, Any], index: int) -> Dict[str, Any]:
    where = f"gmail.records[{index}]"
    _require_exact_keys(value, {"message_id", "recipient_sha256", "sent_at", "evidence_sha256"}, where)
    return {
        "message_id": _require_id(value["message_id"], f"{where}.message_id"),
        "recipient_sha256": _require_sha256(value["recipient_sha256"], f"{where}.recipient_sha256"),
        "sent_at": _format_utc(_parse_utc(value["sent_at"], f"{where}.sent_at")),
        "evidence_sha256": _require_sha256(value["evidence_sha256"], f"{where}.evidence_sha256"),
    }


def _normalize_slack_record(value: Mapping[str, Any], index: int) -> Dict[str, Any]:
    where = f"slack.records[{index}]"
    _require_exact_keys(
        value,
        {"event_id", "provider_message_id", "recipient_sha256", "recorded_at", "evidence_sha256"},
        where,
    )
    provider_message_id = value["provider_message_id"]
    if provider_message_id is not None:
        provider_message_id = _require_id(provider_message_id, f"{where}.provider_message_id")
    return {
        "event_id": _require_id(value["event_id"], f"{where}.event_id"),
        "provider_message_id": provider_message_id,
        "recipient_sha256": _require_sha256(value["recipient_sha256"], f"{where}.recipient_sha256"),
        "recorded_at": _format_utc(_parse_utc(value["recorded_at"], f"{where}.recorded_at")),
        "evidence_sha256": _require_sha256(value["evidence_sha256"], f"{where}.evidence_sha256"),
    }


def _normalize_snapshot(
    snapshot: Mapping[str, Any], *, kind: str
) -> Tuple[Dict[str, Any], List[str]]:
    if kind not in {"gmail", "slack"}:
        raise ReconcileError("internal snapshot kind error")
    schema = GMAIL_SCHEMA if kind == "gmail" else SLACK_SCHEMA
    _require_exact_keys(snapshot, {"schema", "snapshot_id", "captured_at", "complete", "records"}, kind)
    if snapshot["schema"] != schema:
        raise ReconcileError(f"unsupported {kind} snapshot schema")
    records = snapshot["records"]
    if type(records) is not list or len(records) > MAX_RECORDS:
        raise ReconcileError(f"{kind}.records must be a list with at most {MAX_RECORDS} entries")
    normalizer = _normalize_gmail_record if kind == "gmail" else _normalize_slack_record
    normalized_records = [normalizer(record, idx) for idx, record in enumerate(records)]

    key_name = "message_id" if kind == "gmail" else "event_id"
    by_id: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for record in normalized_records:
        stable_id = record[key_name]
        by_id.setdefault(stable_id, {})[canonical_json(record)] = record
    conflicts = [f"{kind.upper()}_STABLE_ID_CONFLICT:{stable_id}"
                 for stable_id, variants in sorted(by_id.items()) if len(variants) > 1]
    # Preserve every distinct conflicting variant in the bound snapshot. Exact
    # replay collapses, but array order must not select which evidence survives.
    normalized_records = sorted(
        (record for variants in by_id.values() for record in variants.values()),
        key=canonical_json,
    )
    normalized = {
        "schema": schema,
        "snapshot_id": _require_id(snapshot["snapshot_id"], f"{kind}.snapshot_id"),
        "captured_at": _format_utc(_parse_utc(snapshot["captured_at"], f"{kind}.captured_at")),
        "complete": _require_bool(snapshot["complete"], f"{kind}.complete"),
        "records": normalized_records,
    }
    return normalized, conflicts


def _snapshot_hold_reasons(
    gmail: Mapping[str, Any], slack: Mapping[str, Any], policy: Mapping[str, Any], as_of: datetime
) -> List[str]:
    reasons: List[str] = []
    max_age = policy["max_snapshot_age_seconds"]
    for kind, snapshot, time_key in (("GMAIL", gmail, "sent_at"), ("SLACK", slack, "recorded_at")):
        if not snapshot["complete"]:
            reasons.append(f"{kind}_SNAPSHOT_INCOMPLETE")
        captured = _parse_utc(snapshot["captured_at"], f"{kind.lower()}.captured_at")
        if captured > as_of:
            reasons.append(f"{kind}_SNAPSHOT_FROM_FUTURE")
        elif (as_of - captured).total_seconds() > max_age:
            reasons.append(f"{kind}_SNAPSHOT_STALE")
        for record in snapshot["records"]:
            observed = _parse_utc(record[time_key], f"{kind.lower()}.record_time")
            stable_id = record.get("message_id", record.get("event_id"))
            if observed > captured:
                reasons.append(f"{kind}_RECORD_AFTER_SNAPSHOT:{stable_id}")
            if observed > as_of:
                reasons.append(f"{kind}_RECORD_FROM_FUTURE:{stable_id}")
    return sorted(set(reasons))


def _common_coverage_through(gmail: Mapping[str, Any], slack: Mapping[str, Any]) -> datetime:
    gmail_captured = _parse_utc(gmail["captured_at"], "gmail.captured_at")
    slack_captured = _parse_utc(slack["captured_at"], "slack.captured_at")
    return min(gmail_captured, slack_captured)


def _cross_ledger_hold_reasons(gmail: Mapping[str, Any], slack: Mapping[str, Any]) -> List[str]:
    """Reject impossible matches and absence claims outside counterpart coverage."""
    reasons: List[str] = []
    gmail_captured = _parse_utc(gmail["captured_at"], "gmail.captured_at")
    slack_captured = _parse_utc(slack["captured_at"], "slack.captured_at")
    providers = {row["message_id"]: row for row in gmail["records"]}
    slack_by_provider: Dict[str, List[Mapping[str, Any]]] = {}
    for row in slack["records"]:
        provider_id = row["provider_message_id"]
        if provider_id is not None:
            slack_by_provider.setdefault(provider_id, []).append(row)
            provider = providers.get(provider_id)
            if provider is not None:
                recorded = _parse_utc(row["recorded_at"], "slack.recorded_at")
                sent = _parse_utc(provider["sent_at"], "gmail.sent_at")
                if recorded < sent:
                    reasons.append(f"SLACK_RECEIPT_BEFORE_PROVIDER_SENT:{row['event_id']}")
            elif _parse_utc(row["recorded_at"], "slack.recorded_at") > gmail_captured:
                reasons.append(f"SLACK_EVENT_OUTSIDE_GMAIL_COVERAGE:{row['event_id']}")

    for provider_id, provider in providers.items():
        if provider_id not in slack_by_provider:
            sent = _parse_utc(provider["sent_at"], "gmail.sent_at")
            if sent > slack_captured:
                reasons.append(f"GMAIL_EVENT_OUTSIDE_SLACK_COVERAGE:{provider_id}")
    return sorted(set(reasons))


def _discrepancy(
    code: str,
    *,
    provider_message_id: Optional[str] = None,
    slack_event_id: Optional[str] = None,
    recipient_sha256: Optional[str] = None,
    observed_recipient_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "code": code,
        "provider_message_id": provider_message_id,
        "slack_event_id": slack_event_id,
        "recipient_sha256": recipient_sha256,
        "observed_recipient_sha256": observed_recipient_sha256,
    }


def compile_report(
    gmail_snapshot: Mapping[str, Any],
    slack_snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    as_of: datetime,
) -> Dict[str, Any]:
    as_of_text = _format_utc(as_of)
    trusted_as_of = _parse_utc(as_of_text, "as_of")
    normalized_policy = _normalize_policy(policy)
    gmail, gmail_conflicts = _normalize_snapshot(gmail_snapshot, kind="gmail")
    slack, slack_conflicts = _normalize_snapshot(slack_snapshot, kind="slack")

    common_coverage_through = _format_utc(_common_coverage_through(gmail, slack))
    hold_reasons = gmail_conflicts + slack_conflicts
    hold_reasons.extend(_snapshot_hold_reasons(gmail, slack, normalized_policy, trusted_as_of))
    hold_reasons.extend(_cross_ledger_hold_reasons(gmail, slack))
    hold_reasons = sorted(set(hold_reasons))

    discrepancies: List[Dict[str, Any]] = []
    if not hold_reasons:
        providers = {row["message_id"]: row for row in gmail["records"]}
        slack_by_provider: Dict[str, List[Dict[str, Any]]] = {}

        for row in slack["records"]:
            provider_id = row["provider_message_id"]
            if provider_id is None:
                discrepancies.append(
                    _discrepancy(
                        "SLACK_RECEIPT_UNBOUND",
                        slack_event_id=row["event_id"],
                        recipient_sha256=row["recipient_sha256"],
                    )
                )
                continue
            slack_by_provider.setdefault(provider_id, []).append(row)
            if provider_id not in providers:
                discrepancies.append(
                    _discrepancy(
                        "SLACK_SENT_WITHOUT_PROVIDER_SENT",
                        provider_message_id=provider_id,
                        slack_event_id=row["event_id"],
                        recipient_sha256=row["recipient_sha256"],
                    )
                )

        for provider_id, provider in sorted(providers.items()):
            receipts = slack_by_provider.get(provider_id, [])
            if not receipts:
                discrepancies.append(
                    _discrepancy(
                        "PROVIDER_SENT_NOT_RECORDED",
                        provider_message_id=provider_id,
                        recipient_sha256=provider["recipient_sha256"],
                    )
                )
                continue
            matching = [row for row in receipts if row["recipient_sha256"] == provider["recipient_sha256"]]
            mismatching = [row for row in receipts if row["recipient_sha256"] != provider["recipient_sha256"]]
            for row in mismatching:
                discrepancies.append(
                    _discrepancy(
                        "PROVIDER_RECIPIENT_CONFLICT",
                        provider_message_id=provider_id,
                        slack_event_id=row["event_id"],
                        recipient_sha256=provider["recipient_sha256"],
                        observed_recipient_sha256=row["recipient_sha256"],
                    )
                )
            if not matching:
                continue
            if len(receipts) > 1:
                for row in sorted(receipts, key=lambda item: item["event_id"]):
                    discrepancies.append(
                        _discrepancy(
                            "DUPLICATE_OR_CONFLICTING_RECEIPT",
                            provider_message_id=provider_id,
                            slack_event_id=row["event_id"],
                            recipient_sha256=row["recipient_sha256"],
                        )
                    )

    discrepancies = sorted(discrepancies, key=canonical_json)
    if hold_reasons:
        status = "HOLD"
    elif discrepancies:
        status = "RECONCILIATION_REQUIRED"
    else:
        status = "LEDGERS_CONSISTENT"

    base_report: Dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "as_of": as_of_text,
        "common_coverage_through": common_coverage_through,
        "policy": normalized_policy,
        "snapshot_ids": {"gmail": gmail["snapshot_id"], "slack": slack["snapshot_id"]},
        "snapshot_sha256": {"gmail": sha256_json(gmail), "slack": sha256_json(slack)},
        "status": status,
        "hold_reasons": hold_reasons,
        "counts": {
            "gmail_sent": len({row["message_id"] for row in gmail["records"]}),
            "slack_receipts": len({row["event_id"] for row in slack["records"]}),
            "discrepancies": len(discrepancies),
        },
        "discrepancies": discrepancies,
        "authority": {
            "gmail_write_authorized": False,
            "slack_write_authorized": False,
            "customer_contact_authorized": False,
            "resend_authorized": False,
            "payment_authorized": False,
            "revenue_recognition_authorized": False,
        },
    }
    report = dict(base_report)
    report["receipt_sha256"] = sha256_json(base_report)
    return report


def verify_report(
    report: Mapping[str, Any],
    gmail_snapshot: Mapping[str, Any],
    slack_snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    as_of: datetime,
) -> bool:
    if type(report) is not dict:
        return False
    try:
        verifier_as_of = _parse_utc(_format_utc(as_of), "verifier.as_of")
        report_as_of = _parse_utc(report.get("as_of"), "report.as_of")
        if report_as_of > verifier_as_of:
            return False
        expected = compile_report(gmail_snapshot, slack_snapshot, policy, as_of=report_as_of)
        return canonical_json(report) == canonical_json(expected)
    except (ReconcileError, TypeError, ValueError, UnicodeError):
        return False


def _read_bounded_json(path: str) -> Any:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReconcileError(f"cannot open input safely: {path}: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ReconcileError(f"input is not a regular file: {path}")
        if info.st_size > MAX_INPUT_BYTES:
            raise ReconcileError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        raw = os.read(fd, MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ReconcileError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        tail = os.read(fd, 1)
        if tail:
            raise ReconcileError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
    finally:
        os.close(fd)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReconcileError(f"input is not UTF-8: {path}") from exc
    return strict_json_loads(text)


def _write_exclusive_json(path: str, value: Any) -> None:
    parent = Path(path).parent
    if not parent.exists() or not parent.is_dir():
        raise ReconcileError(f"output parent does not exist: {parent}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    payload = (canonical_json(value) + "\n").encode("utf-8")
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ReconcileError(f"refusing unsafe/existing output: {path}: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ReconcileError("output is not a regular file")
        written = 0
        while written < len(payload):
            count = os.write(fd, payload[written:])
            if count <= 0:
                raise ReconcileError("short output write")
            written += count
        os.fsync(fd)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reconcile Gmail SENT transport facts with Slack send receipts")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--gmail", required=True)
        cmd.add_argument("--slack", required=True)
        cmd.add_argument("--policy", required=True)
        cmd.add_argument("--report", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        gmail = _read_bounded_json(args.gmail)
        slack = _read_bounded_json(args.slack)
        policy = _read_bounded_json(args.policy)
        now = _now_utc()
        if args.command == "compile":
            report = compile_report(gmail, slack, policy, as_of=now)
            _write_exclusive_json(args.report, report)
            print(report["status"])
            return 0
        report = _read_bounded_json(args.report)
        ok = verify_report(report, gmail, slack, policy, as_of=now)
        print("VERIFIED" if ok else "INVALID")
        return 0 if ok else 2
    except ReconcileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
