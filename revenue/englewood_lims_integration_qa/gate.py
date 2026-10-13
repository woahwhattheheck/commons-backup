from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SNAPSHOT_MAX_AGE_SECONDS = 900
EVIDENCE_MAX_AGE_SECONDS = 86400
FUTURE_SKEW_SECONDS = 60
RECEIPT_MAX_AGE_SECONDS = 300

REQ_CATEGORIES = {"AUDIT_TRAIL", "REAL_TIME_VALIDATION", "SECURE_MULTI_USER_WORKFLOW", "INTEGRATION", "DEPLOYMENT_TESTING", "OTHER"}
TEST_KINDS = {"FUNCTIONAL", "INTEGRATION", "SECURITY", "VALIDATION", "REPLAY"}
CORE_RULES = {"AUDIT_CHAIN_INTEGRITY", "REAL_TIME_VALIDATION", "MULTI_USER_ROLE_SEPARATION", "INTEGRATION_REPLAY_IDEMPOTENCY", "REQUIREMENT_TRACEABILITY"}
WORKFLOW_ROLES = {"CONFIGURE": "CONFIGURATOR", "EXECUTE_TEST": "TESTER", "VALIDATE": "VALIDATOR", "APPROVE_RELEASE": "RELEASE_APPROVER"}
WORKFLOW_ACTIONS = tuple(WORKFLOW_ROLES)
INTEGRATION_OUTCOMES = {"APPLIED", "NO_EFFECT_RETRY", "QUARANTINED"}
AUDIT_ACTIONS = set(WORKFLOW_ACTIONS) | {"INTEGRATION_APPLY", "INTEGRATION_RETRY", "INTEGRATION_QUARANTINE"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

AUTHORITY_FALSE = {
    "proposal_submission_authorized": False,
    "production_deploy_authorized": False,
    "operational_release_authorized": False,
    "contract_authorized": False,
    "payment_authorized": False,
    "buyer_acceptance_claimed": False,
    "recognized_revenue_claimed": False,
}
TOP_KEYS = {"schema_version", "packet_id", "release_id", "snapshot_id", "captured_at", "complete", "requirements", "test_cases", "test_runs", "validation_results", "workflow_events", "integration_events", "audit_events"}
ROW_KEYS = {
    "requirements": {"requirement_id", "category", "mandatory"},
    "test_cases": {"test_id", "requirement_ids", "test_kind"},
    "test_runs": {"run_id", "test_id", "status", "observed_at", "evidence_sha256"},
    "validation_results": {"validation_id", "rule_id", "subject_id", "status", "observed_at", "input_sha256", "result_sha256"},
    "workflow_events": {"event_id", "object_id", "action", "actor_id", "role", "observed_at", "evidence_sha256"},
    "integration_events": {"event_id", "interface_id", "business_key", "sequence", "outcome", "retry_of", "observed_at", "payload_sha256"},
    "audit_events": {"event_id", "sequence", "actor_id", "action", "object_id", "observed_at", "details_sha256", "prev_hash", "event_hash"},
}
RECEIPT_KEYS = {"schema_version", "packet_id", "snapshot_id", "release_id", "decision", "hold_reasons", "counts", "snapshot_digest", "evaluated_at", "expires_at", "authority", "receipt_digest"}
COUNT_KEYS = {"requirements", "mandatory_requirements", "test_cases", "test_runs", "validation_results", "workflow_events", "integration_events_unique", "audit_events"}


class EvidenceError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict(path: str | os.PathLike[str]) -> dict[str, Any]:
    def bad_constant(value: str) -> None:
        raise EvidenceError(f"non-finite JSON number: {value}")
    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=_pairs_no_duplicates, parse_constant=bad_constant)
    if not isinstance(value, dict):
        raise EvidenceError("JSON root must be an object")
    return value


def _keys(row: Any, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != expected:
        actual = set(row) if isinstance(row, dict) else set()
        raise EvidenceError(f"{name} keys mismatch missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    return row


def _ident(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise EvidenceError(f"{name} must be a bounded identifier")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise EvidenceError(f"{name} must be lowercase SHA-256 hex")
    return value


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvidenceError(f"{name} must be integer >= {minimum}")
    return value


def _time(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not RFC3339_UTC.fullmatch(value):
        raise EvidenceError(f"{name} must be whole-second RFC3339 UTC")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise EvidenceError(f"invalid {name}: {value}") from exc


def _fmt(value: datetime) -> str:
    if value.tzinfo is None:
        raise EvidenceError("trusted time must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _array(value: Any, name: str, allow_empty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise EvidenceError(f"{name} must be a {'possibly empty ' if allow_empty else 'non-empty '}array")
    return value


def _unique(rows: list[dict[str, Any]], key: str, name: str) -> None:
    values = [row[key] for row in rows]
    if len(values) != len(set(values)):
        raise EvidenceError(f"duplicate {name}")


def _event_time_reason(value: str, captured: datetime, evaluated: datetime) -> str | None:
    observed = _time(value, "observed_at")
    if observed > captured + timedelta(seconds=FUTURE_SKEW_SECONDS):
        return "EVIDENCE_AFTER_SNAPSHOT"
    if observed > evaluated + timedelta(seconds=FUTURE_SKEW_SECONDS):
        return "FUTURE_EVIDENCE"
    if evaluated - observed > timedelta(seconds=EVIDENCE_MAX_AGE_SECONDS):
        return "STALE_EVIDENCE"
    return None


def make_audit_event(*, event_id: str, sequence: int, actor_id: str, action: str, object_id: str, observed_at: str, details_sha256: str, prev_hash: str | None) -> dict[str, Any]:
    row = {"event_id": event_id, "sequence": sequence, "actor_id": actor_id, "action": action, "object_id": object_id, "observed_at": observed_at, "details_sha256": details_sha256, "prev_hash": prev_hash}
    row["event_hash"] = sha256_json(row)
    return row


def _validate_shape(packet: Any) -> dict[str, Any]:
    packet = _keys(packet, TOP_KEYS, "packet")
    if packet["schema_version"] != SCHEMA_VERSION or isinstance(packet["schema_version"], bool):
        raise EvidenceError("unsupported schema_version")
    for field in ("packet_id", "release_id", "snapshot_id"):
        _ident(packet[field], field)
    _time(packet["captured_at"], "captured_at")
    if type(packet["complete"]) is not bool:
        raise EvidenceError("complete must be boolean")
    for name in ROW_KEYS:
        _array(packet[name], name)
        for i, row in enumerate(packet[name]):
            _keys(row, ROW_KEYS[name], f"{name}[{i}]")

    for row in packet["requirements"]:
        _ident(row["requirement_id"], "requirement_id")
        if row["category"] not in REQ_CATEGORIES or type(row["mandatory"]) is not bool:
            raise EvidenceError("invalid requirement")
    _unique(packet["requirements"], "requirement_id", "requirement_id")

    for row in packet["test_cases"]:
        _ident(row["test_id"], "test_id")
        refs = _array(row["requirement_ids"], "requirement_ids")
        if len(refs) != len(set(refs)) or row["test_kind"] not in TEST_KINDS:
            raise EvidenceError("invalid test case")
        for ref in refs: _ident(ref, "requirement_id")
    _unique(packet["test_cases"], "test_id", "test_id")

    for row in packet["test_runs"]:
        _ident(row["run_id"], "run_id"); _ident(row["test_id"], "test_id"); _time(row["observed_at"], "observed_at"); _sha(row["evidence_sha256"], "evidence_sha256")
        if row["status"] not in {"PASS", "FAIL"}: raise EvidenceError("invalid test status")
    _unique(packet["test_runs"], "run_id", "run_id")

    for row in packet["validation_results"]:
        for field in ("validation_id", "rule_id", "subject_id"): _ident(row[field], field)
        _time(row["observed_at"], "observed_at"); _sha(row["input_sha256"], "input_sha256"); _sha(row["result_sha256"], "result_sha256")
        if row["status"] not in {"PASS", "FAIL"}: raise EvidenceError("invalid validation status")
    _unique(packet["validation_results"], "validation_id", "validation_id")

    for row in packet["workflow_events"]:
        for field in ("event_id", "object_id", "actor_id", "role"): _ident(row[field], field)
        _time(row["observed_at"], "observed_at"); _sha(row["evidence_sha256"], "evidence_sha256")
        if row["action"] not in WORKFLOW_ROLES: raise EvidenceError("invalid workflow action")
    _unique(packet["workflow_events"], "event_id", "workflow event_id")

    for row in packet["integration_events"]:
        for field in ("event_id", "interface_id", "business_key"): _ident(row[field], field)
        _integer(row["sequence"], "sequence", 1); _time(row["observed_at"], "observed_at"); _sha(row["payload_sha256"], "payload_sha256")
        if row["outcome"] not in INTEGRATION_OUTCOMES: raise EvidenceError("invalid integration outcome")
        if row["retry_of"] is not None: _ident(row["retry_of"], "retry_of")

    for row in packet["audit_events"]:
        for field in ("event_id", "actor_id", "object_id"): _ident(row[field], field)
        _integer(row["sequence"], "sequence", 1); _time(row["observed_at"], "observed_at"); _sha(row["details_sha256"], "details_sha256"); _sha(row["event_hash"], "event_hash")
        if row["prev_hash"] is not None: _sha(row["prev_hash"], "prev_hash")
        if row["action"] not in AUDIT_ACTIONS: raise EvidenceError("invalid audit action")
    _unique(packet["audit_events"], "event_id", "audit event_id"); _unique(packet["audit_events"], "sequence", "audit sequence")
    return packet


def _collapse_integrations(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    by_id: dict[str, dict[str, Any]] = {}
    conflict = False
    for row in rows:
        prior = by_id.get(row["event_id"])
        if prior is None: by_id[row["event_id"]] = row
        elif prior != row: conflict = True
    return sorted(by_id.values(), key=lambda r: (r["interface_id"], r["business_key"], r["sequence"], r["event_id"])), conflict


def _normalized(packet: dict[str, Any]) -> dict[str, Any]:
    out = dict(packet)
    keys = {"requirements": "requirement_id", "test_cases": "test_id", "test_runs": "run_id", "validation_results": "validation_id", "workflow_events": "event_id"}
    for name, key in keys.items(): out[name] = sorted(packet[name], key=lambda r: r[key])
    out["integration_events"] = _collapse_integrations(packet["integration_events"])[0]
    out["audit_events"] = sorted(packet["audit_events"], key=lambda r: r["sequence"])
    return out


def _evaluate(packet: dict[str, Any], evaluated_at: datetime) -> dict[str, Any]:
    packet = _validate_shape(packet)
    evaluated = evaluated_at.astimezone(timezone.utc).replace(microsecond=0)
    captured = _time(packet["captured_at"], "captured_at")
    reasons: set[str] = set()
    if not packet["complete"]: reasons.add("INCOMPLETE_SNAPSHOT")
    if captured > evaluated + timedelta(seconds=FUTURE_SKEW_SECONDS): reasons.add("FUTURE_SNAPSHOT")
    if evaluated - captured > timedelta(seconds=SNAPSHOT_MAX_AGE_SECONDS): reasons.add("STALE_SNAPSHOT")

    requirements = {row["requirement_id"]: row for row in packet["requirements"]}
    tests = {row["test_id"]: row for row in packet["test_cases"]}
    runs_by_test: dict[str, list[dict[str, Any]]] = {}
    for row in packet["test_runs"]:
        runs_by_test.setdefault(row["test_id"], []).append(row)
        if row["test_id"] not in tests: reasons.add("UNKNOWN_TEST_RUN")
        reason = _event_time_reason(row["observed_at"], captured, evaluated)
        if reason: reasons.add(reason)
    covered: set[str] = set()
    for test in packet["test_cases"]:
        if any(ref not in requirements for ref in test["requirement_ids"]): reasons.add("UNKNOWN_REQUIREMENT_REFERENCE")
        runs = runs_by_test.get(test["test_id"], [])
        if len(runs) != 1: reasons.add("TEST_EXECUTION_CARDINALITY")
        elif runs[0]["status"] != "PASS": reasons.add("TEST_FAILURE")
        else: covered.update(test["requirement_ids"])
    if any(row["mandatory"] and row["requirement_id"] not in covered for row in packet["requirements"]): reasons.add("MANDATORY_REQUIREMENT_UNCOVERED")

    by_rule: dict[str, list[dict[str, Any]]] = {}
    for row in packet["validation_results"]:
        by_rule.setdefault(row["rule_id"], []).append(row)
        if row["rule_id"] not in CORE_RULES: reasons.add("UNAPPROVED_VALIDATION_RULE")
        if row["status"] != "PASS": reasons.add("VALIDATION_FAILURE")
        reason = _event_time_reason(row["observed_at"], captured, evaluated)
        if reason: reasons.add(reason)
    if any(len(by_rule.get(rule, [])) != 1 for rule in CORE_RULES): reasons.add("CORE_VALIDATION_CARDINALITY")

    by_action: dict[str, list[dict[str, Any]]] = {}
    for row in packet["workflow_events"]:
        by_action.setdefault(row["action"], []).append(row)
        if row["object_id"] != packet["release_id"]: reasons.add("WORKFLOW_RELEASE_MISMATCH")
        if row["role"] != WORKFLOW_ROLES[row["action"]]: reasons.add("WORKFLOW_ROLE_MISMATCH")
        reason = _event_time_reason(row["observed_at"], captured, evaluated)
        if reason: reasons.add(reason)
    if any(len(by_action.get(action, [])) != 1 for action in WORKFLOW_ACTIONS): reasons.add("WORKFLOW_ACTION_CARDINALITY")
    if all(len(by_action.get(action, [])) == 1 for action in WORKFLOW_ACTIONS):
        actors = {by_action["CONFIGURE"][0]["actor_id"], by_action["EXECUTE_TEST"][0]["actor_id"], by_action["APPROVE_RELEASE"][0]["actor_id"]}
        if len(actors) != 3: reasons.add("ROLE_SEPARATION_VIOLATION")

    integrations, conflict = _collapse_integrations(packet["integration_events"])
    if conflict: reasons.add("INTEGRATION_EVENT_ID_CONFLICT")
    applied = {row["event_id"]: row for row in integrations if row["outcome"] == "APPLIED"}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in integrations:
        groups.setdefault((row["interface_id"], row["business_key"]), []).append(row)
        reason = _event_time_reason(row["observed_at"], captured, evaluated)
        if reason: reasons.add(reason)
        if row["outcome"] == "QUARANTINED": reasons.add("INTEGRATION_QUARANTINED")
        if row["outcome"] == "APPLIED" and row["retry_of"] is not None: reasons.add("INVALID_RETRY_LINK")
        if row["outcome"] == "NO_EFFECT_RETRY":
            original = applied.get(row["retry_of"] or "")
            if original is None or any(original[field] != row[field] for field in ("interface_id", "business_key", "payload_sha256", "sequence")): reasons.add("INVALID_RETRY_LINK")
    for rows in groups.values():
        sequences = sorted({row["sequence"] for row in rows if row["outcome"] == "APPLIED"})
        if sequences and sequences != list(range(1, max(sequences) + 1)): reasons.add("INTEGRATION_SEQUENCE_GAP")
    if not applied: reasons.add("NO_APPLIED_INTEGRATION_EVIDENCE")

    audit = sorted(packet["audit_events"], key=lambda r: r["sequence"])
    prev: str | None = None
    last_time: datetime | None = None
    audit_actions: set[str] = set()
    for expected, row in enumerate(audit, 1):
        if row["sequence"] != expected: reasons.add("AUDIT_SEQUENCE_GAP")
        observed = _time(row["observed_at"], "observed_at")
        if last_time is not None and observed < last_time: reasons.add("AUDIT_TIME_REGRESSION")
        last_time = observed
        if row["prev_hash"] != prev: reasons.add("AUDIT_CHAIN_BROKEN")
        unsigned = {key: value for key, value in row.items() if key != "event_hash"}
        expected_hash = sha256_json(unsigned)
        if row["event_hash"] != expected_hash: reasons.add("AUDIT_HASH_MISMATCH")
        prev = row["event_hash"]
        audit_actions.add(row["action"])
        reason = _event_time_reason(row["observed_at"], captured, evaluated)
        if reason: reasons.add(reason)
    if any(action not in audit_actions for action in WORKFLOW_ACTIONS): reasons.add("WORKFLOW_NOT_AUDITED")

    expires = min(evaluated + timedelta(seconds=RECEIPT_MAX_AGE_SECONDS), captured + timedelta(seconds=SNAPSHOT_MAX_AGE_SECONDS))
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "packet_id": packet["packet_id"],
        "snapshot_id": packet["snapshot_id"],
        "release_id": packet["release_id"],
        "decision": "HOLD" if reasons else "READY_FOR_PRIME_REVIEW",
        "hold_reasons": sorted(reasons),
        "counts": {
            "requirements": len(packet["requirements"]),
            "mandatory_requirements": sum(1 for row in packet["requirements"] if row["mandatory"]),
            "test_cases": len(packet["test_cases"]),
            "test_runs": len(packet["test_runs"]),
            "validation_results": len(packet["validation_results"]),
            "workflow_events": len(packet["workflow_events"]),
            "integration_events_unique": len(integrations),
            "audit_events": len(packet["audit_events"]),
        },
        "snapshot_digest": sha256_json(_normalized(packet)),
        "evaluated_at": _fmt(evaluated),
        "expires_at": _fmt(expires),
        "authority": dict(AUTHORITY_FALSE),
    }
    receipt["receipt_digest"] = sha256_json(receipt)
    return receipt


def evaluate(packet: dict[str, Any]) -> dict[str, Any]:
    """Evaluate against trusted process time; packet timestamps cannot grant freshness."""
    return _evaluate(packet, _utcnow())


def _validate_receipt(receipt: Any) -> dict[str, Any]:
    receipt = _keys(receipt, RECEIPT_KEYS, "receipt")
    if receipt["schema_version"] != SCHEMA_VERSION or isinstance(receipt["schema_version"], bool): raise EvidenceError("unsupported receipt schema_version")
    for field in ("packet_id", "snapshot_id", "release_id"): _ident(receipt[field], field)
    if receipt["decision"] not in {"READY_FOR_PRIME_REVIEW", "HOLD"}: raise EvidenceError("invalid receipt decision")
    reasons = _array(receipt["hold_reasons"], "hold_reasons", allow_empty=True)
    if any(not isinstance(reason, str) or not ID_PATTERN.fullmatch(reason) for reason in reasons) or reasons != sorted(set(reasons)): raise EvidenceError("invalid hold reasons")
    if (receipt["decision"] == "HOLD") != bool(reasons): raise EvidenceError("decision/reasons mismatch")
    counts = _keys(receipt["counts"], COUNT_KEYS, "counts")
    for name, value in counts.items(): _integer(value, f"counts.{name}")
    _sha(receipt["snapshot_digest"], "snapshot_digest"); _time(receipt["evaluated_at"], "evaluated_at"); _time(receipt["expires_at"], "expires_at"); _sha(receipt["receipt_digest"], "receipt_digest")
    if receipt["authority"] != AUTHORITY_FALSE: raise EvidenceError("receipt authority boundary changed")
    return receipt


def _verify_receipt_at(receipt: dict[str, Any], consume_at: datetime) -> bool:
    try:
        receipt = _validate_receipt(receipt)
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        if sha256_json(unsigned) != receipt["receipt_digest"]: return False
        evaluated, expires = _time(receipt["evaluated_at"], "evaluated_at"), _time(receipt["expires_at"], "expires_at")
        consume = consume_at.astimezone(timezone.utc).replace(microsecond=0)
        return expires > evaluated and expires - evaluated <= timedelta(seconds=RECEIPT_MAX_AGE_SECONDS) and evaluated <= consume < expires
    except (EvidenceError, ValueError, TypeError, OverflowError):
        return False


def verify_receipt(receipt: dict[str, Any]) -> bool:
    return _verify_receipt_at(receipt, _utcnow())


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(canonical_json(value) + "\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        try: os.unlink(temp)
        except OSError: pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Englewood LIMS integration-QA evidence gate")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate_parser = sub.add_parser("evaluate"); evaluate_parser.add_argument("packet"); evaluate_parser.add_argument("--out", required=True)
    verify_parser = sub.add_parser("verify"); verify_parser.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            source, target = Path(args.packet).resolve(), Path(args.out).resolve()
            if source == target: raise EvidenceError("input and output paths must differ")
            receipt = evaluate(load_json_strict(source)); _atomic_write(target, receipt); print(canonical_json(receipt))
            return 0 if receipt["decision"] == "READY_FOR_PRIME_REVIEW" else 3
        ok = verify_receipt(load_json_strict(args.receipt)); print("VALID" if ok else "INVALID"); return 0 if ok else 4
    except (EvidenceError, OSError, ValueError, TypeError, OverflowError) as exc:
        print(f"ERROR: {exc}"); return 2


if __name__ == "__main__":
    raise SystemExit(main())
