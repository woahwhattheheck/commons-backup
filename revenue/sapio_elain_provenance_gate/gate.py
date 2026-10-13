from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = 1
RECEIPT_SCHEMA = "sapio-elain-provenance-receipt/v1"
MAX_EVENTS = 2_000
MAX_COMPONENTS = 256
MAX_SOURCES = 2_000
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_SOURCE_AGE = timedelta(days=30)
MAX_FUTURE_SKEW = timedelta(minutes=5)
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_COMPONENT_KINDS = frozenset({"connector", "model", "tool", "prompt_policy"})
ALLOWED_RISK_CLASSES = frozenset({"LOW", "MODERATE", "HIGH"})
SECRET_KEY_RE = re.compile(r"(?:^|[_-])(password|passwd|secret|token|api[_-]?key|private[_-]?key)(?:$|[_-])", re.I)


class ProvenanceInputError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProvenanceInputError("value is not canonical JSON") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise ProvenanceInputError("canonical JSON exceeds size limit")
    return raw


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _token(value: Any, field: str) -> str:
    if type(value) is not str or not TOKEN_RE.fullmatch(value):
        raise ProvenanceInputError(f"{field} must be a canonical token")
    return value


def _digest(value: Any, field: str) -> str:
    if type(value) is not str or not SHA_RE.fullmatch(value):
        raise ProvenanceInputError(f"{field} must be lowercase SHA-256")
    return value


def _text(value: Any, field: str, max_len: int = 512) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > max_len:
        raise ProvenanceInputError(f"{field} must be bounded non-empty text")
    if any(not c.isprintable() for c in value):
        raise ProvenanceInputError(f"{field} contains non-printable text")
    return value


def _time(value: Any, field: str) -> datetime:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ProvenanceInputError(f"{field} must be canonical UTC seconds")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ProvenanceInputError(f"{field} must be a real UTC timestamp") from exc
    return parsed


def _time_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strict_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ProvenanceInputError(f"{field} fields do not match schema")
    return value


def _reject_secret_shaped(value: Any, path: str = "bundle") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str:
                raise ProvenanceInputError(f"{path} has non-string key")
            if SECRET_KEY_RE.search(key) and child not in (None, "", False):
                raise ProvenanceInputError(f"secret-shaped field is forbidden: {path}.{key}")
            _reject_secret_shaped(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _reject_secret_shaped(child, f"{path}[{i}]")


def _normalize_components(raw: Any) -> tuple[list[dict[str, str]], dict[tuple[str, str], dict[str, str]]]:
    if not isinstance(raw, list) or len(raw) > MAX_COMPONENTS:
        raise ProvenanceInputError("components must be a bounded list")
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    normalized: list[dict[str, str]] = []
    for i, item in enumerate(raw):
        item = _strict_keys(item, {"kind", "component_id", "version", "sha256"}, f"components[{i}]")
        kind = item["kind"]
        if kind not in ALLOWED_COMPONENT_KINDS:
            raise ProvenanceInputError("component kind is unsupported")
        component_id = _token(item["component_id"], "component_id")
        version = _token(item["version"], "component version")
        sha256 = _digest(item["sha256"], "component sha256")
        key = (kind, component_id)
        row = {"kind": kind, "component_id": component_id, "version": version, "sha256": sha256}
        if key in by_key:
            if by_key[key] != row:
                raise ProvenanceInputError("component identity has conflicting definitions")
            raise ProvenanceInputError("component identity is duplicated")
        by_key[key] = row
        normalized.append(row)
    return normalized, by_key


def _normalize_sources(raw: Any) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    if not isinstance(raw, list) or len(raw) > MAX_SOURCES:
        raise ProvenanceInputError("source_snapshots must be a bounded list")
    by_id: dict[str, dict[str, str]] = {}
    normalized: list[dict[str, str]] = []
    for i, item in enumerate(raw):
        item = _strict_keys(item, {"source_id", "sha256", "captured_at"}, f"source_snapshots[{i}]")
        source_id = _token(item["source_id"], "source_id")
        row = {
            "source_id": source_id,
            "sha256": _digest(item["sha256"], "source sha256"),
            "captured_at": _time_text(_time(item["captured_at"], "source captured_at")),
        }
        if source_id in by_id:
            if by_id[source_id] != row:
                raise ProvenanceInputError("source identity has conflicting definitions")
            raise ProvenanceInputError("source identity is duplicated")
        by_id[source_id] = row
        normalized.append(row)
    return normalized, by_id


def _normalize_ref(raw: Any, kind: str, components: dict[tuple[str, str], dict[str, str]]) -> dict[str, str]:
    raw = _strict_keys(raw, {"component_id", "sha256"}, f"{kind}_ref")
    component_id = _token(raw["component_id"], f"{kind}_ref component_id")
    sha256 = _digest(raw["sha256"], f"{kind}_ref sha256")
    component = components.get((kind, component_id))
    if component is None:
        raise ProvenanceInputError(f"{kind}_ref is not declared")
    if component["sha256"] != sha256:
        raise ProvenanceInputError(f"{kind}_ref digest does not match declaration")
    return {"component_id": component_id, "sha256": sha256}


def _normalize_event(raw: Any, components: dict[tuple[str, str], dict[str, str]], sources: dict[str, dict[str, str]], evaluated_at: datetime) -> tuple[dict[str, Any], list[str]]:
    expected = {
        "event_id", "source_id", "source_sha256", "query_sha256", "result_sha256",
        "connector_ref", "model_ref", "tool_ref", "prompt_policy_ref",
        "actor_ref", "actor_role", "intended_use", "risk_class", "change_control_ref",
        "generated_at", "approval",
    }
    raw = _strict_keys(raw, expected, "event")
    event_id = _token(raw["event_id"], "event_id")
    source_id = _token(raw["source_id"], "event source_id")
    source_sha = _digest(raw["source_sha256"], "event source_sha256")
    source = sources.get(source_id)
    if source is None:
        raise ProvenanceInputError("event source is not declared")
    holds: list[str] = []
    if source["sha256"] != source_sha:
        holds.append("SOURCE_DIGEST_MISMATCH")
    source_time = _time(source["captured_at"], "source captured_at")
    generated_at = _time(raw["generated_at"], "generated_at")
    if source_time > generated_at:
        holds.append("SOURCE_AFTER_GENERATION")
    if source_time > evaluated_at + MAX_FUTURE_SKEW:
        holds.append("SOURCE_FROM_FUTURE")
    if evaluated_at - source_time > MAX_SOURCE_AGE:
        holds.append("SOURCE_STALE")
    if generated_at > evaluated_at + MAX_FUTURE_SKEW:
        holds.append("GENERATION_FROM_FUTURE")

    actor_ref = _token(raw["actor_ref"], "actor_ref")
    if "@" in actor_ref:
        raise ProvenanceInputError("actor_ref must be pseudonymous, not an email")
    actor_role = _text(raw["actor_role"], "actor_role", 96)
    intended_use = _text(raw["intended_use"], "intended_use", 256)
    risk_class = raw["risk_class"]
    if risk_class not in ALLOWED_RISK_CLASSES:
        raise ProvenanceInputError("risk_class is unsupported")
    change_control_ref = _token(raw["change_control_ref"], "change_control_ref")

    approval = _strict_keys(raw["approval"], {"approval_id", "reviewer_ref", "reviewer_role", "reviewer_type", "decision", "approved_at", "artifact_sha256"}, "approval")
    approval_id = _token(approval["approval_id"], "approval_id")
    reviewer_ref = _token(approval["reviewer_ref"], "reviewer_ref")
    reviewer_role = _text(approval["reviewer_role"], "reviewer_role", 96)
    reviewer_type = approval["reviewer_type"]
    decision = approval["decision"]
    approved_at = _time(approval["approved_at"], "approved_at")
    artifact_sha = _digest(approval["artifact_sha256"], "approval artifact_sha256")
    result_sha = _digest(raw["result_sha256"], "result_sha256")
    if reviewer_type != "human":
        holds.append("HUMAN_APPROVAL_REQUIRED")
    if decision != "APPROVED":
        holds.append("APPROVAL_NOT_GRANTED")
    if artifact_sha != result_sha:
        holds.append("APPROVAL_ARTIFACT_MISMATCH")
    if approved_at < generated_at:
        holds.append("APPROVAL_BEFORE_GENERATION")
    if approved_at > evaluated_at + MAX_FUTURE_SKEW:
        holds.append("APPROVAL_FROM_FUTURE")

    refs = {
        kind: _normalize_ref(raw[f"{kind}_ref"], kind, components)
        for kind in ("connector", "model", "tool", "prompt_policy")
    }
    event = {
        "event_id": event_id,
        "source_id": source_id,
        "source_sha256": source_sha,
        "query_sha256": _digest(raw["query_sha256"], "query_sha256"),
        "result_sha256": result_sha,
        "connector_ref": refs["connector"],
        "model_ref": refs["model"],
        "tool_ref": refs["tool"],
        "prompt_policy_ref": refs["prompt_policy"],
        "actor_ref": actor_ref,
        "actor_role": actor_role,
        "intended_use": intended_use,
        "risk_class": risk_class,
        "change_control_ref": change_control_ref,
        "generated_at": _time_text(generated_at),
        "approval": {
            "approval_id": approval_id,
            "reviewer_ref": reviewer_ref,
            "reviewer_role": reviewer_role,
            "reviewer_type": reviewer_type,
            "decision": decision,
            "approved_at": _time_text(approved_at),
            "artifact_sha256": artifact_sha,
        },
    }
    return event, sorted(set(holds))


def _assess_at(bundle: Any, evaluated_at: datetime) -> dict[str, Any]:
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ProvenanceInputError("evaluation time must be timezone-aware")
    evaluated_at = evaluated_at.astimezone(timezone.utc).replace(microsecond=0)
    bundle = _strict_keys(bundle, {"schema_version", "bundle_id", "components", "source_snapshots", "events"}, "bundle")
    if type(bundle["schema_version"]) is not int or bundle["schema_version"] != SCHEMA_VERSION:
        raise ProvenanceInputError("schema_version must be integer 1")
    _reject_secret_shaped(bundle)
    bundle_id = _token(bundle["bundle_id"], "bundle_id")
    components, component_map = _normalize_components(bundle["components"])
    sources, source_map = _normalize_sources(bundle["source_snapshots"])
    raw_events = bundle["events"]
    if not isinstance(raw_events, list) or not raw_events or len(raw_events) > MAX_EVENTS:
        raise ProvenanceInputError("events must be a non-empty bounded list")

    event_by_id: dict[str, dict[str, Any]] = {}
    event_holds: dict[str, list[str]] = {}
    replay_count = 0
    conflict_ids: set[str] = set()
    for raw in raw_events:
        event, holds = _normalize_event(raw, component_map, source_map, evaluated_at)
        eid = event["event_id"]
        prior = event_by_id.get(eid)
        if prior is not None:
            if prior == event:
                replay_count += 1
                continue
            conflict_ids.add(eid)
            continue
        event_by_id[eid] = event
        event_holds[eid] = holds

    for eid in conflict_ids:
        event_holds.setdefault(eid, []).append("EVENT_ID_CONFLICT")

    normalized_events = [event_by_id[eid] for eid in sorted(event_by_id)]
    results = []
    hold_codes: set[str] = set()
    ready_events = 0
    for event in normalized_events:
        holds = sorted(set(event_holds[event["event_id"]]))
        status = "EVIDENCE_COMPLETE" if not holds else "HOLD"
        if status == "EVIDENCE_COMPLETE":
            ready_events += 1
        else:
            hold_codes.update(holds)
        results.append({
            "event_id": event["event_id"],
            "status": status,
            "hold_codes": holds,
            "event_sha256": _sha(event),
        })

    normalized_bundle = {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "components": sorted(components, key=lambda row: (row["kind"], row["component_id"])),
        "source_snapshots": sorted(sources, key=lambda row: row["source_id"]),
        "events": normalized_events,
    }
    outcome = "QA_REVIEW_READY_EVIDENCE_ONLY" if not hold_codes else "HOLD"
    receipt_core = {
        "schema": RECEIPT_SCHEMA,
        "bundle_id": bundle_id,
        "evaluated_at": _time_text(evaluated_at),
        "outcome": outcome,
        "hold_codes": sorted(hold_codes),
        "stats": {
            "input_events": len(raw_events),
            "unique_events": len(normalized_events),
            "exact_replays_collapsed": replay_count,
            "evidence_complete_events": ready_events,
            "hold_events": len(normalized_events) - ready_events,
        },
        "bundle_sha256": _sha(normalized_bundle),
        "event_results": results,
        "authority": {
            "batch_release_authorized": False,
            "qa_disposition_authorized": False,
            "gxp_validation_certified": False,
            "regulatory_compliance_certified": False,
            "production_deployment_authorized": False,
            "buyer_acceptance_inferred": False,
            "payment_inferred": False,
            "recognized_revenue_inferred": False,
        },
        "integrity_classification": "CONTENT_HASH_AND_CONTRACT_CHECK_ONLY",
    }
    return {**receipt_core, "receipt_sha256": _sha(receipt_core)}


def assess_bundle(bundle: Any) -> dict[str, Any]:
    """Evaluate a bundle using the process clock; callers cannot backdate readiness."""
    return _assess_at(bundle, datetime.now(timezone.utc))


def verify_receipt(bundle: Any, receipt: Any) -> bool:
    """Verify receipt integrity only. This does not grant current release authority."""
    if not isinstance(receipt, dict) or type(receipt.get("evaluated_at")) is not str:
        return False
    try:
        evaluated_at = _time(receipt["evaluated_at"], "receipt evaluated_at")
        expected = _assess_at(bundle, evaluated_at)
    except ProvenanceInputError:
        return False
    return expected == receipt


def authority_is_non_effecting(receipt: Any) -> bool:
    if not isinstance(receipt, dict) or not isinstance(receipt.get("authority"), dict):
        return False
    return all(value is False for value in receipt["authority"].values())


def clone(value: Any) -> Any:
    return deepcopy(value)
