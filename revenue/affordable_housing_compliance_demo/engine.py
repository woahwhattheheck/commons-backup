from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
from collections import defaultdict
from pathlib import Path
from typing import Any

REQUEST_SCHEMA = "affordable-housing-compliance-demo-request/v1"
RECEIPT_SCHEMA = "affordable-housing-compliance-demo-receipt/v1"
MAX_BYTES = 5 * 1024 * 1024
SHA256_CHARS = set("0123456789abcdef")
SOURCE_AUTHORITIES = {"DISCOVERY", "CONTROLLING"}
DATA_CLASSES = {"SYNTHETIC", "APPROVED_DEIDENTIFIED"}
DECISIONS = {
    "MEASURE_ONLY",
    "READY_FOR_PRIME_REVIEW",
    "HOLD_SOURCE_AUTHORITY",
    "HOLD_EVIDENCE",
    "HOLD_THRESHOLDS",
}
PII_KEYS = {
    "name", "first_name", "last_name", "full_name", "email", "phone", "telephone",
    "ssn", "social_security_number", "dob", "date_of_birth", "address", "street_address",
    "tenant_name", "applicant_name", "household_member_name", "bank_account", "routing_number",
}
REQUEST_KEYS = {
    "schema", "buyer_ref", "opportunity_ref", "generated_at", "data_classification",
    "sources", "requirements", "gold_findings", "candidate_findings", "migration_source",
    "migration_target", "access_policy", "audit_events", "effects", "threshold_policy",
}
THRESHOLD_KEYS = {
    "approved", "approval_ref", "approval_sha256", "min_precision_bps", "min_recall_bps",
    "max_migration_missing", "max_migration_extra", "max_migration_changed",
    "max_access_violations", "max_duplicate_effects",
}


class EvidenceError(ValueError):
    pass


def _is_int(value: Any) -> bool:
    return type(value) is int


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA256_CHARS


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise EvidenceError(f"non-finite JSON number: {value}")


def loads_strict(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid JSON: {exc}") from exc
    if type(value) is not dict:
        raise EvidenceError("JSON root must be an object")
    return value


def read_stable_json(path: Path) -> dict[str, Any]:
    try:
        lst = path.lstat()
    except OSError as exc:
        raise EvidenceError(f"cannot stat {path}: {exc}") from exc
    if stat.S_ISLNK(lst.st_mode) or not stat.S_ISREG(lst.st_mode):
        raise EvidenceError("input must be a regular non-symlink file")
    if lst.st_size <= 0 or lst.st_size > MAX_BYTES:
        raise EvidenceError(f"input size out of bounds: {lst.st_size}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise EvidenceError(f"cannot open {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise EvidenceError("opened input is not a regular file")
        if (before.st_dev, before.st_ino, before.st_size) != (lst.st_dev, lst.st_ino, lst.st_size):
            raise EvidenceError("input identity changed before read")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise EvidenceError("short read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise EvidenceError("input grew during read")
        after = os.fstat(fd)
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if identity_before != identity_after:
            raise EvidenceError("input changed during read")
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    return loads_strict(raw)


def _reject_pii(value: Any, path: str = "$") -> None:
    if type(value) is dict:
        for key, child in value.items():
            if key.lower() in PII_KEYS:
                raise EvidenceError(f"PII-bearing field forbidden at {path}.{key}")
            _reject_pii(child, f"{path}.{key}")
    elif type(value) is list:
        for idx, child in enumerate(value):
            _reject_pii(child, f"{path}[{idx}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise EvidenceError(f"non-finite value at {path}")


def _exact_keys(obj: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise EvidenceError(f"{label} must be an object")
    if set(obj) != keys:
        missing = sorted(keys - set(obj))
        extra = sorted(set(obj) - keys)
        raise EvidenceError(f"{label} schema drift missing={missing} extra={extra}")
    return obj


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{label} must be a non-empty string")
    return value


def _bps(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 10_000 if numerator == 0 else 0
    return (numerator * 10_000) // denominator


def _validate_request(request: dict[str, Any]) -> None:
    _exact_keys(request, REQUEST_KEYS, "request")
    if request["schema"] != REQUEST_SCHEMA:
        raise EvidenceError("unsupported request schema")
    _nonempty(request["buyer_ref"], "buyer_ref")
    _nonempty(request["opportunity_ref"], "opportunity_ref")
    _nonempty(request["generated_at"], "generated_at")
    if request["data_classification"] not in DATA_CLASSES:
        raise EvidenceError("only synthetic or explicitly approved deidentified data is allowed")
    _reject_pii(request)

    if type(request["sources"]) is not list or not request["sources"]:
        raise EvidenceError("at least one source is required")
    source_ids: set[str] = set()
    for i, source in enumerate(request["sources"]):
        _exact_keys(source, {"source_id", "uri", "sha256", "authority", "retrieved_at"}, f"sources[{i}]")
        sid = _nonempty(source["source_id"], f"sources[{i}].source_id")
        if sid in source_ids:
            raise EvidenceError(f"duplicate source_id: {sid}")
        source_ids.add(sid)
        _nonempty(source["uri"], f"sources[{i}].uri")
        if not _valid_sha(source["sha256"]):
            raise EvidenceError(f"invalid source sha256: {sid}")
        if source["authority"] not in SOURCE_AUTHORITIES:
            raise EvidenceError(f"invalid source authority: {sid}")
        _nonempty(source["retrieved_at"], f"sources[{i}].retrieved_at")

    if type(request["requirements"]) is not list or not request["requirements"]:
        raise EvidenceError("requirements must be a non-empty list")
    req_ids: set[str] = set()
    sources = {s["source_id"]: s for s in request["sources"]}
    for i, req in enumerate(request["requirements"]):
        _exact_keys(req, {"requirement_id", "source_id", "source_sha256", "category", "statement_sha256"}, f"requirements[{i}]")
        rid = _nonempty(req["requirement_id"], f"requirements[{i}].requirement_id")
        if rid in req_ids:
            raise EvidenceError(f"duplicate requirement_id: {rid}")
        req_ids.add(rid)
        sid = req["source_id"]
        if sid not in sources:
            raise EvidenceError(f"unknown requirement source: {sid}")
        if req["source_sha256"] != sources[sid]["sha256"]:
            raise EvidenceError(f"requirement source hash mismatch: {rid}")
        _nonempty(req["category"], f"requirements[{i}].category")
        if not _valid_sha(req["statement_sha256"]):
            raise EvidenceError(f"invalid statement sha256: {rid}")

    if type(request["gold_findings"]) is not list or not request["gold_findings"]:
        raise EvidenceError("gold_findings must be a non-empty list")
    seen_gold: set[tuple[str, str]] = set()
    for i, row in enumerate(request["gold_findings"]):
        _exact_keys(row, {"case_id", "finding_code", "requirement_id"}, f"gold_findings[{i}]")
        case_id = _nonempty(row["case_id"], f"gold_findings[{i}].case_id")
        finding = _nonempty(row["finding_code"], f"gold_findings[{i}].finding_code")
        if row["requirement_id"] not in req_ids:
            raise EvidenceError(f"gold finding references unknown requirement: {row['requirement_id']}")
        key = (case_id, finding)
        if key in seen_gold:
            raise EvidenceError(f"duplicate gold finding: {key}")
        seen_gold.add(key)

    if type(request["candidate_findings"]) is not list:
        raise EvidenceError("candidate_findings must be a list")
    seen_candidate: set[tuple[str, str]] = set()
    for i, row in enumerate(request["candidate_findings"]):
        _exact_keys(row, {"case_id", "finding_code", "evidence_sha256"}, f"candidate_findings[{i}]")
        key = (
            _nonempty(row["case_id"], f"candidate_findings[{i}].case_id"),
            _nonempty(row["finding_code"], f"candidate_findings[{i}].finding_code"),
        )
        if key in seen_candidate:
            raise EvidenceError(f"duplicate candidate finding: {key}")
        seen_candidate.add(key)
        if not _valid_sha(row["evidence_sha256"]):
            raise EvidenceError(f"invalid candidate evidence hash: {key}")

    for field in ("migration_source", "migration_target"):
        rows = request[field]
        if type(rows) is not list:
            raise EvidenceError(f"{field} must be a list")
        seen: set[str] = set()
        for i, row in enumerate(rows):
            _exact_keys(row, {"record_id", "record_sha256"}, f"{field}[{i}]")
            rid = _nonempty(row["record_id"], f"{field}[{i}].record_id")
            if rid in seen:
                raise EvidenceError(f"duplicate {field} record_id: {rid}")
            seen.add(rid)
            if not _valid_sha(row["record_sha256"]):
                raise EvidenceError(f"invalid {field} record hash: {rid}")

    if type(request["access_policy"]) is not list:
        raise EvidenceError("access_policy must be a list")
    policy_keys: set[tuple[str, str]] = set()
    for i, row in enumerate(request["access_policy"]):
        _exact_keys(row, {"role", "action", "allowed"}, f"access_policy[{i}]")
        key = (_nonempty(row["role"], f"access_policy[{i}].role"), _nonempty(row["action"], f"access_policy[{i}].action"))
        if key in policy_keys:
            raise EvidenceError(f"duplicate access policy key: {key}")
        policy_keys.add(key)
        if type(row["allowed"]) is not bool:
            raise EvidenceError(f"access policy allowed must be bool: {key}")

    if type(request["audit_events"]) is not list:
        raise EvidenceError("audit_events must be a list")
    event_ids: set[str] = set()
    for i, event in enumerate(request["audit_events"]):
        _exact_keys(event, {"event_id", "role", "action", "resource_id", "observed_allowed"}, f"audit_events[{i}]")
        eid = _nonempty(event["event_id"], f"audit_events[{i}].event_id")
        if eid in event_ids:
            raise EvidenceError(f"duplicate audit event_id: {eid}")
        event_ids.add(eid)
        _nonempty(event["role"], f"audit_events[{i}].role")
        _nonempty(event["action"], f"audit_events[{i}].action")
        _nonempty(event["resource_id"], f"audit_events[{i}].resource_id")
        if type(event["observed_allowed"]) is not bool:
            raise EvidenceError(f"audit observed_allowed must be bool: {eid}")

    if type(request["effects"]) is not list:
        raise EvidenceError("effects must be a list")
    effect_event_ids: set[str] = set()
    for i, event in enumerate(request["effects"]):
        _exact_keys(event, {"event_id", "idempotency_key", "effect_id", "status"}, f"effects[{i}]")
        eid = _nonempty(event["event_id"], f"effects[{i}].event_id")
        if eid in effect_event_ids:
            raise EvidenceError(f"duplicate effect event_id: {eid}")
        effect_event_ids.add(eid)
        _nonempty(event["idempotency_key"], f"effects[{i}].idempotency_key")
        _nonempty(event["effect_id"], f"effects[{i}].effect_id")
        if event["status"] not in {"COMMITTED", "REPLAY"}:
            raise EvidenceError(f"invalid effect status: {eid}")

    threshold = _exact_keys(request["threshold_policy"], THRESHOLD_KEYS, "threshold_policy")
    if type(threshold["approved"]) is not bool:
        raise EvidenceError("threshold_policy.approved must be bool")
    if threshold["approved"]:
        _nonempty(threshold["approval_ref"], "threshold_policy.approval_ref")
        if not _valid_sha(threshold["approval_sha256"]):
            raise EvidenceError("approved threshold policy requires approval_sha256")
    else:
        if threshold["approval_ref"] is not None or threshold["approval_sha256"] is not None:
            raise EvidenceError("unapproved threshold policy cannot imply approval evidence")
    for key in THRESHOLD_KEYS - {"approved", "approval_ref", "approval_sha256"}:
        value = threshold[key]
        if not _is_int(value) or value < 0:
            raise EvidenceError(f"threshold {key} must be a non-negative int")
    if threshold["min_precision_bps"] > 10_000 or threshold["min_recall_bps"] > 10_000:
        raise EvidenceError("basis-point thresholds exceed 10000")


def compile_receipt(request: dict[str, Any]) -> dict[str, Any]:
    _validate_request(request)
    request_sha = digest(request)
    sources = {s["source_id"]: s for s in request["sources"]}
    requirement_source_holds = sorted(
        req["requirement_id"]
        for req in request["requirements"]
        if sources[req["source_id"]]["authority"] != "CONTROLLING"
    )

    gold = {(x["case_id"], x["finding_code"]) for x in request["gold_findings"]}
    candidate = {(x["case_id"], x["finding_code"]) for x in request["candidate_findings"]}
    tp = len(gold & candidate)
    fp = len(candidate - gold)
    fn = len(gold - candidate)
    precision = _bps(tp, tp + fp)
    recall = _bps(tp, tp + fn)

    source_rows = {r["record_id"]: r["record_sha256"] for r in request["migration_source"]}
    target_rows = {r["record_id"]: r["record_sha256"] for r in request["migration_target"]}
    missing = sorted(set(source_rows) - set(target_rows))
    extra = sorted(set(target_rows) - set(source_rows))
    changed = sorted(rid for rid in set(source_rows) & set(target_rows) if source_rows[rid] != target_rows[rid])

    policy = {(x["role"], x["action"]): x["allowed"] for x in request["access_policy"]}
    access_violations: list[dict[str, str]] = []
    for event in request["audit_events"]:
        key = (event["role"], event["action"])
        if key not in policy:
            access_violations.append({"event_id": event["event_id"], "reason": "NO_APPROVED_POLICY"})
        elif event["observed_allowed"] != policy[key]:
            access_violations.append({"event_id": event["event_id"], "reason": "OBSERVED_POLICY_MISMATCH"})

    effects: dict[str, set[str]] = defaultdict(set)
    for event in request["effects"]:
        if event["status"] == "COMMITTED":
            effects[event["idempotency_key"]].add(event["effect_id"])
        elif event["status"] == "REPLAY":
            # A replay may repeat the original effect id, but cannot introduce a new logical effect.
            effects[event["idempotency_key"]].add(event["effect_id"])
    duplicate_effect_keys = sorted(key for key, ids in effects.items() if len(ids) > 1)

    metrics = {
        "finding_true_positive": tp,
        "finding_false_positive": fp,
        "finding_false_negative": fn,
        "finding_precision_bps": precision,
        "finding_recall_bps": recall,
        "migration_source_count": len(source_rows),
        "migration_target_count": len(target_rows),
        "migration_missing_count": len(missing),
        "migration_extra_count": len(extra),
        "migration_changed_count": len(changed),
        "access_violation_count": len(access_violations),
        "duplicate_effect_count": len(duplicate_effect_keys),
    }

    evidence = {
        "requirement_source_holds": requirement_source_holds,
        "migration_missing_ids": missing,
        "migration_extra_ids": extra,
        "migration_changed_ids": changed,
        "access_violations": access_violations,
        "duplicate_effect_keys": duplicate_effect_keys,
    }

    threshold = request["threshold_policy"]
    threshold_failures: list[str] = []
    if threshold["approved"]:
        if precision < threshold["min_precision_bps"]:
            threshold_failures.append("FINDING_PRECISION")
        if recall < threshold["min_recall_bps"]:
            threshold_failures.append("FINDING_RECALL")
        if len(missing) > threshold["max_migration_missing"]:
            threshold_failures.append("MIGRATION_MISSING")
        if len(extra) > threshold["max_migration_extra"]:
            threshold_failures.append("MIGRATION_EXTRA")
        if len(changed) > threshold["max_migration_changed"]:
            threshold_failures.append("MIGRATION_CHANGED")
        if len(access_violations) > threshold["max_access_violations"]:
            threshold_failures.append("ACCESS_POLICY")
        if len(duplicate_effect_keys) > threshold["max_duplicate_effects"]:
            threshold_failures.append("DUPLICATE_EFFECT")

    evidence_problem = bool(missing or extra or changed or access_violations or duplicate_effect_keys)
    if requirement_source_holds:
        decision = "HOLD_SOURCE_AUTHORITY"
    elif evidence_problem and not threshold["approved"]:
        decision = "HOLD_EVIDENCE"
    elif not threshold["approved"]:
        decision = "MEASURE_ONLY"
    elif threshold_failures:
        decision = "HOLD_THRESHOLDS"
    else:
        decision = "READY_FOR_PRIME_REVIEW"

    if decision not in DECISIONS:
        raise AssertionError("internal decision drift")

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "buyer_ref": request["buyer_ref"],
        "opportunity_ref": request["opportunity_ref"],
        "request_sha256": request_sha,
        "data_classification": request["data_classification"],
        "source_inventory_sha256": digest(request["sources"]),
        "requirements_sha256": digest(request["requirements"]),
        "gold_findings_sha256": digest(request["gold_findings"]),
        "candidate_findings_sha256": digest(request["candidate_findings"]),
        "migration_source_sha256": digest(request["migration_source"]),
        "migration_target_sha256": digest(request["migration_target"]),
        "access_policy_sha256": digest(request["access_policy"]),
        "audit_events_sha256": digest(request["audit_events"]),
        "effects_sha256": digest(request["effects"]),
        "threshold_policy_sha256": digest(request["threshold_policy"]),
        "metrics": metrics,
        "evidence": evidence,
        "threshold_failures": threshold_failures,
        "decision": decision,
        "authority": {
            "prime_qualified": False,
            "housing_compliance_determined": False,
            "buyer_acceptance_proven": False,
            "proposal_submission_authorized": False,
            "production_tenant_data_authorized": False,
            "payment_or_revenue_proven": False,
            "autonomous_rule_adoption_authorized": False,
        },
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


def verify_receipt(request: dict[str, Any], receipt: dict[str, Any]) -> bool:
    if type(receipt) is not dict:
        raise EvidenceError("receipt must be an object")
    expected = compile_receipt(request)
    if receipt != expected:
        raise EvidenceError("receipt does not reproduce exactly from request")
    return True


def _write_new(path: Path, value: dict[str, Any]) -> None:
    raw = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise EvidenceError(f"cannot create output exclusively: {exc}") from exc
    try:
        total = 0
        while total < len(raw):
            total += os.write(fd, raw[total:])
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile/verify buyer-neutral affordable-housing compliance demo evidence")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("request", type=Path)
    c.add_argument("output", type=Path)
    v = sub.add_parser("verify")
    v.add_argument("request", type=Path)
    v.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        request = read_stable_json(args.request)
        if args.cmd == "compile":
            _write_new(args.output, compile_receipt(request))
            return 0
        receipt = read_stable_json(args.receipt)
        verify_receipt(request, receipt)
        return 0
    except EvidenceError as exc:
        print(f"HOLD: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
