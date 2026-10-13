from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

DOMAINS = {"finance", "procurement", "hr", "payroll"}
FORBIDDEN_FIXTURE_FIELDS = {
    "ssn", "social_security_number", "bank_account", "routing_number",
    "date_of_birth", "dob", "home_address", "personal_email",
}


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _text(value: Any, name: str, max_len: int = 256) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    value = value.strip()
    if not value or len(value) > max_len:
        raise ValueError(f"{name} must be non-empty and <= {max_len} chars")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must contain scalar Unicode") from exc
    return value


def _instant(value: Any, name: str = "effective_at") -> str:
    raw = _text(value, name, 64)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _decimal(value: Any, name: str) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be decimal-compatible") from exc
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    rendered = format(parsed.normalize(), "f")
    return "0" if rendered in {"-0", ""} else rendered


def _reject_sensitive_fixture_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_FIXTURE_FIELDS:
                raise ValueError(f"raw sensitive fixture field forbidden: {lowered}")
            _reject_sensitive_fixture_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive_fixture_fields(child)


def _safe_attributes(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("attributes must be an object")
    serialized = stable_json(value)
    try:
        serialized.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("attributes must contain scalar Unicode") from exc
    normalized = json.loads(serialized)
    _reject_sensitive_fixture_fields(normalized)
    return normalized


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("record must be an object")
    domain = _text(raw.get("domain"), "domain", 32)
    if domain not in DOMAINS:
        raise ValueError(f"unsupported domain: {domain}")
    record = {
        "domain": domain,
        "record_type": _text(raw.get("record_type"), "record_type", 80),
        "source_system": _text(raw.get("source_system"), "source_system", 80),
        "source_id": _text(raw.get("source_id"), "source_id", 160),
        "effective_at": _instant(raw.get("effective_at")),
        "currency": _text(raw.get("currency", "USD"), "currency", 8).upper(),
        "amount": _decimal(raw.get("amount", "0"), "amount"),
        "attributes": _safe_attributes(raw.get("attributes")),
    }
    identity = {k: record[k] for k in ("domain", "record_type", "source_system", "source_id", "effective_at")}
    record["stable_key"] = sha256_json(identity)
    record["content_hash"] = sha256_json({k: record[k] for k in record if k not in {"stable_key", "content_hash"}})
    return record


def ingest(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        row = normalize_record(raw)
        if row["stable_key"] in seen:
            raise ValueError(f"duplicate stable record: {row['stable_key']}")
        seen.add(row["stable_key"])
        out.append(row)
    return sorted(out, key=lambda row: row["stable_key"])


def _totals(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    totals: dict[str, Decimal] = {}
    for row in rows:
        key = f"{row['domain']}:{row['record_type']}:{row['currency']}"
        totals[key] = totals.get(key, Decimal("0")) + Decimal(row["amount"])
    return {k: format(v.normalize(), "f") for k, v in sorted(totals.items())}


def reconcile_migration(source_rows: Iterable[dict[str, Any]], target_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    source_list, target_list = ingest(source_rows), ingest(target_rows)
    source = {r["stable_key"]: r for r in source_list}
    target = {r["stable_key"]: r for r in target_list}
    missing = sorted(set(source) - set(target))
    extra = sorted(set(target) - set(source))
    changed = sorted(k for k in set(source) & set(target) if source[k]["content_hash"] != target[k]["content_hash"])
    matched = sorted(k for k in set(source) & set(target) if source[k]["content_hash"] == target[k]["content_hash"])
    source_totals, target_totals = _totals(source_list), _totals(target_list)
    totals_match = source_totals == target_totals
    result = {
        "source_count": len(source), "target_count": len(target), "matched": matched,
        "missing": missing, "extra": extra, "changed": changed,
        "source_totals": source_totals, "target_totals": target_totals, "totals_match": totals_match,
    }
    result["status"] = "pass" if not missing and not extra and not changed and totals_match else "review_required"
    result["evidence_hash"] = sha256_json(result)
    return result


def evaluate_interface_replay(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    attempts: dict[str, dict[str, Any]] = {}
    violations: list[str] = []
    for raw in events:
        if not isinstance(raw, dict):
            raise TypeError("interface event must be an object")
        request_id = _text(raw.get("request_id"), "request_id", 160)
        interface = _text(raw.get("interface"), "interface", 120)
        payload_hash = _text(raw.get("payload_hash"), "payload_hash", 64).lower()
        if len(payload_hash) != 64 or any(c not in "0123456789abcdef" for c in payload_hash):
            raise ValueError("payload_hash must be 64 hex chars")
        attempt = raw.get("attempt")
        if isinstance(attempt, bool) or not isinstance(attempt, int):
            raise TypeError("attempt must be an integer")
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        committed = raw.get("committed", False)
        if not isinstance(committed, bool):
            raise TypeError("committed must be a boolean")
        response = _text(raw.get("response"), "response", 40)
        existing = attempts.get(request_id)
        if existing:
            if existing["interface"] != interface or existing["payload_hash"] != payload_hash:
                violations.append(f"{request_id}:replay_identity_changed")
            if attempt <= existing["max_attempt"]:
                violations.append(f"{request_id}:attempt_not_monotonic")
            if existing["committed"] and committed:
                violations.append(f"{request_id}:duplicate_commit")
            existing["max_attempt"] = max(existing["max_attempt"], attempt)
            existing["committed"] = existing["committed"] or committed
            existing["responses"].append(response)
        else:
            attempts[request_id] = {
                "interface": interface, "payload_hash": payload_hash, "max_attempt": attempt,
                "committed": committed, "responses": [response],
            }
    result = {"requests": len(attempts), "violations": sorted(set(violations)), "request_state": dict(sorted(attempts.items()))}
    result["status"] = "pass" if not result["violations"] else "review_required"
    result["evidence_hash"] = sha256_json(result)
    return result


def build_uat_packet(scenarios: Iterable[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in scenarios:
        if not isinstance(raw, dict):
            raise TypeError("scenario must be an object")
        scenario_id = _text(raw.get("scenario_id"), "scenario_id", 120)
        if scenario_id in seen:
            raise ValueError(f"duplicate scenario_id: {scenario_id}")
        seen.add(scenario_id)
        status = _text(raw.get("status"), "status", 24)
        if status not in {"pass", "fail", "blocked"}:
            raise ValueError("status must be pass|fail|blocked")
        evidence_hash = _text(raw.get("evidence_hash"), "evidence_hash", 64).lower()
        if len(evidence_hash) != 64 or any(c not in "0123456789abcdef" for c in evidence_hash):
            raise ValueError("evidence_hash must be 64 hex chars")
        normalized.append({
            "scenario_id": scenario_id,
            "requirement_ref": _text(raw.get("requirement_ref"), "requirement_ref", 160),
            "status": status, "evidence_hash": evidence_hash,
        })
    normalized.sort(key=lambda x: x["scenario_id"])
    counts = {state: sum(1 for row in normalized if row["status"] == state) for state in ("pass", "fail", "blocked")}
    packet = {
        "scenarios": normalized, "counts": counts,
        "status": "pass" if normalized and counts["fail"] == 0 and counts["blocked"] == 0 else "review_required",
        "authority": "owner_review_required",
    }
    packet["evidence_hash"] = sha256_json(packet)
    return packet


def build_cutover_gate(
    source_rows: Iterable[dict[str, Any]],
    target_rows: Iterable[dict[str, Any]],
    events: Iterable[dict[str, Any]],
    scenarios: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    migration = reconcile_migration(source_rows, target_rows)
    replay = evaluate_interface_replay(events)
    uat = build_uat_packet(scenarios)
    gate = {
        "migration_hash": migration["evidence_hash"],
        "replay_hash": replay["evidence_hash"],
        "uat_hash": uat["evidence_hash"],
        "ready_for_owner_review": all(item["status"] == "pass" for item in (migration, replay, uat)),
        "input_authority": "caller_supplied_evidence_only",
        "release_authority": "owner_review_required",
        "production_cutover_authority": False,
        "county_submission_authority": False,
    }
    gate["gate_hash"] = sha256_json(gate)
    return gate
