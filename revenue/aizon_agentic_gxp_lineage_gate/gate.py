"""Deterministic, evidence-only lineage gate for synthetic agentic/GxP fixtures."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

AUTHORITY = "EVIDENCE_ONLY_NO_GXP_RELEASE"
SCHEMA = "aizon-agentic-gxp-lineage-gate/v1"
KINDS = {"SOURCE", "CHANGE_CONTROL", "EXECUTION", "HUMAN_APPROVAL"}
RISKS = {"LOW", "MEDIUM", "HIGH"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    pass


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise EvidenceError("evidence must be canonical JSON") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _str(value: Any, field: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > limit:
        raise EvidenceError(f"{field} must be a bounded non-empty string")
    return value


def _id(value: Any, field: str) -> str:
    value = _str(value, field, 128)
    if not ID_RE.fullmatch(value):
        raise EvidenceError(f"{field} is not a canonical identifier")
    return value


def _hash(value: Any, field: str) -> str:
    value = _str(value, field, 64)
    if not HASH_RE.fullmatch(value):
        raise EvidenceError(f"{field} must be lowercase sha256 hex")
    return value


def _time(value: Any, field: str) -> datetime:
    text = _str(value, field, 40)
    if not text.endswith("Z"):
        raise EvidenceError(f"{field} must be UTC RFC3339 ending in Z")
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise EvidenceError(f"{field} must be RFC3339") from exc


def _fmt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _int(value: Any, field: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise EvidenceError(f"{field} must be an integer in [{lo}, {hi}]")
    return value


def _exact(value: Any, keys: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise EvidenceError(f"{field} must contain exactly {sorted(keys)}")
    return value


def _values(value: Any, field: str, allowed: set[str] | None = None) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 32:
        raise EvidenceError(f"{field} must be a bounded non-empty list")
    items = [_str(v, field, 128) for v in value]
    if len(items) != len(set(items)) or (allowed is not None and not set(items) <= allowed):
        raise EvidenceError(f"{field} contains duplicate or unsupported values")
    return sorted(items)


def _tools(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value or len(value) > 16:
        raise EvidenceError(f"{field} must be a bounded non-empty mapping")
    return {_id(k, f"{field}.name"): _str(v, f"{field}.{k}", 128) for k, v in value.items()}


def _policy(raw: Mapping[str, Any]) -> dict[str, Any]:
    obj = _exact(dict(raw) if isinstance(raw, Mapping) else raw, {
        "schema", "policy_id", "version", "valid_from", "valid_until",
        "allowed_execution_roles", "allowed_approver_roles", "allowed_risks",
        "max_source_age_s", "max_execution_age_s", "max_approval_age_s", "max_future_skew_s",
    }, "policy")
    if obj["schema"] != SCHEMA:
        raise EvidenceError("unsupported policy schema")
    start, end = _time(obj["valid_from"], "policy.valid_from"), _time(obj["valid_until"], "policy.valid_until")
    if end <= start:
        raise EvidenceError("policy validity window is inverted")
    return {
        "policy_id": _id(obj["policy_id"], "policy.policy_id"),
        "version": _str(obj["version"], "policy.version", 128),
        "valid_from": start, "valid_until": end,
        "execution_roles": _values(obj["allowed_execution_roles"], "policy.allowed_execution_roles"),
        "approver_roles": _values(obj["allowed_approver_roles"], "policy.allowed_approver_roles"),
        "risks": _values(obj["allowed_risks"], "policy.allowed_risks", RISKS),
        "source_age": _int(obj["max_source_age_s"], "policy.max_source_age_s", 1, 31_536_000),
        "execution_age": _int(obj["max_execution_age_s"], "policy.max_execution_age_s", 1, 2_592_000),
        "approval_age": _int(obj["max_approval_age_s"], "policy.max_approval_age_s", 1, 604_800),
        "skew": _int(obj["max_future_skew_s"], "policy.max_future_skew_s", 0, 3600),
    }


def _policy_payload(p: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA, "policy_id": p["policy_id"], "version": p["version"],
        "valid_from": _fmt(p["valid_from"]), "valid_until": _fmt(p["valid_until"]),
        "allowed_execution_roles": p["execution_roles"], "allowed_approver_roles": p["approver_roles"],
        "allowed_risks": p["risks"], "max_source_age_s": p["source_age"],
        "max_execution_age_s": p["execution_age"], "max_approval_age_s": p["approval_age"],
        "max_future_skew_s": p["skew"],
    }


def _norm(raw: Any) -> dict[str, Any]:
    e = _exact(raw, {"event_id", "kind", "artifact_id", "occurred_at", "body"}, "event")
    if len(_canon(e)) > 65_536:
        raise EvidenceError("event exceeds byte ceiling")
    event_id, artifact = _id(e["event_id"], "event.event_id"), _id(e["artifact_id"], "event.artifact_id")
    kind, occurred = _str(e["kind"], "event.kind", 32), _fmt(_time(e["occurred_at"], "event.occurred_at"))
    if kind not in KINDS:
        raise EvidenceError("unsupported event kind")
    body = e["body"]
    if kind == "SOURCE":
        body = _exact(body, {"source_snapshot_hash", "batch_context_hash", "dataset_version"}, "SOURCE.body")
        out = {"source_snapshot_hash": _hash(body["source_snapshot_hash"], "SOURCE.source_snapshot_hash"),
               "batch_context_hash": _hash(body["batch_context_hash"], "SOURCE.batch_context_hash"),
               "dataset_version": _str(body["dataset_version"], "SOURCE.dataset_version", 128)}
    elif kind == "CHANGE_CONTROL":
        body = _exact(body, {"status", "model_version", "tools", "prompt_policy_version", "allowed_risks", "approved_at", "expires_at"}, "CHANGE_CONTROL.body")
        if body["status"] != "APPROVED":
            raise EvidenceError("change control status must be APPROVED")
        approved, expires = _time(body["approved_at"], "CHANGE_CONTROL.approved_at"), _time(body["expires_at"], "CHANGE_CONTROL.expires_at")
        if expires <= approved:
            raise EvidenceError("change control expiry must follow approval")
        out = {"status": "APPROVED", "model_version": _str(body["model_version"], "CHANGE_CONTROL.model_version", 128),
               "tools": _tools(body["tools"], "CHANGE_CONTROL.tools"),
               "prompt_policy_version": _str(body["prompt_policy_version"], "CHANGE_CONTROL.prompt_policy_version", 128),
               "allowed_risks": _values(body["allowed_risks"], "CHANGE_CONTROL.allowed_risks", RISKS),
               "approved_at": _fmt(approved), "expires_at": _fmt(expires)}
    elif kind == "EXECUTION":
        body = _exact(body, {"source_event_id", "change_event_id", "model_version", "tools", "prompt_policy_version", "query_hash", "result_hash", "actor_id", "actor_role", "intended_use_risk"}, "EXECUTION.body")
        risk = _str(body["intended_use_risk"], "EXECUTION.intended_use_risk", 16)
        if risk not in RISKS:
            raise EvidenceError("unsupported intended-use risk")
        out = {"source_event_id": _id(body["source_event_id"], "EXECUTION.source_event_id"),
               "change_event_id": _id(body["change_event_id"], "EXECUTION.change_event_id"),
               "model_version": _str(body["model_version"], "EXECUTION.model_version", 128),
               "tools": _tools(body["tools"], "EXECUTION.tools"),
               "prompt_policy_version": _str(body["prompt_policy_version"], "EXECUTION.prompt_policy_version", 128),
               "query_hash": _hash(body["query_hash"], "EXECUTION.query_hash"), "result_hash": _hash(body["result_hash"], "EXECUTION.result_hash"),
               "actor_id": _id(body["actor_id"], "EXECUTION.actor_id"), "actor_role": _str(body["actor_role"], "EXECUTION.actor_role", 128),
               "intended_use_risk": risk}
    else:
        body = _exact(body, {"execution_event_id", "approver_id", "approver_role", "decision", "lineage_digest", "approved_at", "expires_at"}, "HUMAN_APPROVAL.body")
        if body["decision"] != "APPROVE":
            raise EvidenceError("human approval decision must be APPROVE")
        approved, expires = _time(body["approved_at"], "HUMAN_APPROVAL.approved_at"), _time(body["expires_at"], "HUMAN_APPROVAL.expires_at")
        if expires <= approved:
            raise EvidenceError("human approval expiry must follow approval")
        out = {"execution_event_id": _id(body["execution_event_id"], "HUMAN_APPROVAL.execution_event_id"),
               "approver_id": _id(body["approver_id"], "HUMAN_APPROVAL.approver_id"),
               "approver_role": _str(body["approver_role"], "HUMAN_APPROVAL.approver_role", 128), "decision": "APPROVE",
               "lineage_digest": _hash(body["lineage_digest"], "HUMAN_APPROVAL.lineage_digest"),
               "approved_at": _fmt(approved), "expires_at": _fmt(expires)}
    return {"event_id": event_id, "kind": kind, "artifact_id": artifact, "occurred_at": occurred, "body": out}


def _dedupe(events: Iterable[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    raw = list(events)
    if not 1 <= len(raw) <= 64:
        raise EvidenceError("events must contain 1..64 entries")
    variants: dict[str, dict[bytes, dict[str, Any]]] = {}
    for item in raw:
        e = _norm(item); variants.setdefault(e["event_id"], {})[_canon(e)] = e
    normalized, conflicts = [], []
    for event_id in sorted(variants):
        group = variants[event_id]
        if len(group) > 1:
            conflicts.append(event_id)
        normalized.append(group[min(group)])
    return normalized, conflicts


def compute_lineage_digest(source: Mapping[str, Any], change: Mapping[str, Any], execution: Mapping[str, Any]) -> str:
    return _sha({"source": _norm(dict(source)), "change_control": _norm(dict(change)), "execution": _norm(dict(execution))})


def evaluate(events: Iterable[Any], policy: Mapping[str, Any], *, evaluated_at: str) -> dict[str, Any]:
    now, p = _time(evaluated_at, "evaluated_at"), _policy(policy)
    normalized, conflicts = _dedupe(events)
    reasons: set[str] = {"EVENT_IDENTITY_CONFLICT"} if conflicts else set()
    artifacts = {e["artifact_id"] for e in normalized}
    artifact = next(iter(artifacts)) if len(artifacts) == 1 else "MULTIPLE"
    if len(artifacts) != 1:
        reasons.add("ARTIFACT_IDENTITY_CONFLICT")
    by_kind = {k: [e for e in normalized if e["kind"] == k] for k in KINDS}
    for e in normalized:
        if _time(e["occurred_at"], "event.occurred_at") > now + timedelta(seconds=p["skew"]): reasons.add("FUTURE_EVENT")
    for kind, rows in by_kind.items():
        if len(rows) != 1: reasons.add(f"{kind}_COUNT")
    if not p["valid_from"] <= now <= p["valid_until"]: reasons.add("POLICY_NOT_CURRENT")
    deadlines = [p["valid_until"]]; lineage = "0" * 64
    if len(artifacts) == 1 and all(len(by_kind[k]) == 1 for k in KINDS):
        source, change, execution, approval = (by_kind[k][0] for k in ("SOURCE", "CHANGE_CONTROL", "EXECUTION", "HUMAN_APPROVAL"))
        st, et, at = (_time(source["occurred_at"], "source.time"), _time(execution["occurred_at"], "execution.time"), _time(approval["occurred_at"], "approval.time"))
        sa, ea, aa = st + timedelta(seconds=p["source_age"]), et + timedelta(seconds=p["execution_age"]), _time(approval["body"]["approved_at"], "approval.approved_at") + timedelta(seconds=p["approval_age"])
        deadlines += [sa, ea, aa]
        if now > sa: reasons.add("SOURCE_STALE")
        if now > ea: reasons.add("EXECUTION_STALE")
        if now > aa: reasons.add("APPROVAL_STALE")
        if execution["body"]["source_event_id"] != source["event_id"]: reasons.add("SOURCE_LINEAGE_MISMATCH")
        if execution["body"]["change_event_id"] != change["event_id"]: reasons.add("CHANGE_LINEAGE_MISMATCH")
        if approval["body"]["execution_event_id"] != execution["event_id"]: reasons.add("APPROVAL_LINEAGE_MISMATCH")
        ca, ce = _time(change["body"]["approved_at"], "change.approved_at"), _time(change["body"]["expires_at"], "change.expires_at")
        ha, he = _time(approval["body"]["approved_at"], "approval.approved_at"), _time(approval["body"]["expires_at"], "approval.expires_at")
        deadlines += [ce, he]
        if not (ca <= et <= ce and now <= ce): reasons.add("CHANGE_CONTROL_NOT_CURRENT")
        if not (et <= ha <= at + timedelta(seconds=p["skew"])): reasons.add("APPROVAL_TIME_INVALID")
        if now > he: reasons.add("APPROVAL_EXPIRED")
        pairs = (("model_version", "MODEL_OUTSIDE_CHANGE_CONTROL"), ("tools", "TOOLS_OUTSIDE_CHANGE_CONTROL"), ("prompt_policy_version", "PROMPT_POLICY_OUTSIDE_CHANGE_CONTROL"))
        for field, reason in pairs:
            if execution["body"][field] != change["body"][field]: reasons.add(reason)
        risk = execution["body"]["intended_use_risk"]
        if risk not in change["body"]["allowed_risks"]: reasons.add("RISK_OUTSIDE_CHANGE_CONTROL")
        if risk not in p["risks"]: reasons.add("RISK_OUTSIDE_POLICY")
        if execution["body"]["actor_role"] not in p["execution_roles"]: reasons.add("EXECUTION_ROLE_NOT_ALLOWED")
        if approval["body"]["approver_role"] not in p["approver_roles"]: reasons.add("APPROVER_ROLE_NOT_ALLOWED")
        lineage = compute_lineage_digest(source, change, execution)
        if approval["body"]["lineage_digest"] != lineage: reasons.add("APPROVAL_DIGEST_MISMATCH")
    core = {"schema": SCHEMA, "authority": AUTHORITY, "status": "READY" if not reasons else "HOLD", "artifact_id": artifact,
            "reasons": sorted(reasons), "evaluated_at": _fmt(now), "valid_until": _fmt(min(deadlines)),
            "evidence_digest": _sha(normalized), "policy_digest": _sha(_policy_payload(p)), "lineage_digest": lineage,
            "unique_event_count": len(normalized), "conflicting_event_ids": conflicts}
    return {**core, "receipt_sha256": _sha(core)}


def verify_receipt(receipt: Mapping[str, Any], events: Iterable[Any], policy: Mapping[str, Any], *, evaluated_at: str, require_ready: bool = True) -> bool:
    required = {"schema", "authority", "status", "artifact_id", "reasons", "evaluated_at", "valid_until", "evidence_digest", "policy_digest", "lineage_digest", "unique_event_count", "conflicting_event_ids", "receipt_sha256"}
    if not isinstance(receipt, Mapping) or set(receipt) != required or receipt.get("schema") != SCHEMA or receipt.get("authority") != AUTHORITY:
        return False
    core = {k: receipt[k] for k in required - {"receipt_sha256"}}
    if _sha(core) != receipt.get("receipt_sha256"): return False
    try:
        if evaluate(events, policy, evaluated_at=str(receipt["evaluated_at"])) != dict(receipt): return False
        now, issued, valid, p = _time(evaluated_at, "evaluated_at"), _time(receipt["evaluated_at"], "receipt.evaluated_at"), _time(receipt["valid_until"], "receipt.valid_until"), _policy(policy)
        if issued > now + timedelta(seconds=p["skew"]) or now > valid: return False
        if require_ready:
            if receipt["status"] != "READY": return False
            current = evaluate(events, policy, evaluated_at=_fmt(now))
            if current["status"] != "READY": return False
            if any(current[k] != receipt[k] for k in ("artifact_id", "evidence_digest", "policy_digest", "lineage_digest")): return False
    except (EvidenceError, KeyError, TypeError, ValueError):
        return False
    return True
