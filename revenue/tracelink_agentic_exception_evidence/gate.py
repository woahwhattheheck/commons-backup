from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA = "tracelink.agentic-exception-evidence/v1"
DECISION_SCHEMA = "tracelink.agentic-exception-decision/v1"
SNAPSHOT_POLICY_ID = "snapshot-freshness-v1"
SNAPSHOT_MAX_AGE_MINUTES = 30

_REASON_ORDER = (
    "UNTRUSTED_PARTNER",
    "STALE_SNAPSHOT",
    "PO_ASN_MISMATCH",
    "MISSING_AGENT_PROFILE_VERSION",
    "PERMISSION_OUT_OF_SCOPE",
    "MISSING_HUMAN_APPROVAL",
    "FINAL_ACTION_HASH_MISMATCH",
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,95}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,95}$")
_PERMISSION_RE = re.compile(r"^[a-z][a-z0-9_.:-]{1,95}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class EvidenceError(ValueError):
    def __init__(self, code: str, detail: str | None = None):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


def _fail(code: str, detail: str | None = None) -> None:
    raise EvidenceError(code, detail)


def _obj(value: Any, code: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(code)
    return value


def _exact_keys(value: dict[str, Any], keys: tuple[str, ...], code: str) -> None:
    if set(value) != set(keys):
        _fail(code)


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        _fail("STRING_REQUIRED", field)
    if not allow_empty and not value:
        _fail("STRING_REQUIRED", field)
    if len(value) > 512:
        _fail("STRING_TOO_LONG", field)
    return value


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        _fail("INVALID_IDENTIFIER", field)
    return value


def _version(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        _fail("INVALID_VERSION", field)
    return value


def _permission(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _PERMISSION_RE.fullmatch(value):
        _fail("INVALID_PERMISSION", field)
    return value


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        _fail("INVALID_DIGEST", field)
    return value


def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        _fail("BOOLEAN_REQUIRED", field)
    return value


def _positive_int(value: Any, field: str, *, maximum: int = 10080) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 1 or value > maximum:
        _fail("INVALID_POSITIVE_INTEGER", field)
    return value


def _timestamp(value: Any, field: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not _TS_RE.fullmatch(value):
        _fail("NONCANONICAL_TIMESTAMP", field)
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail("INVALID_TIMESTAMP", field)
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail("NONCANONICAL_TIMESTAMP", field)
    return value, dt


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EvidenceError("NONCANONICAL_VALUE", str(exc)) from exc


def sha256(value: Any) -> str:
    payload = value if isinstance(value, (bytes, bytearray)) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_id_list(raw: Any, field: str) -> list[str]:
    if not isinstance(raw, list):
        _fail("LIST_REQUIRED", field)
    values = [_identifier(value, f"{field}[{i}]") for i, value in enumerate(raw)]
    if len(set(values)) != len(values):
        _fail("DUPLICATE_IDENTIFIER", field)
    return sorted(values)


def _normalize_payload(raw: Any, field: str) -> dict[str, Any]:
    payload = _obj(copy.deepcopy(raw), "ACTION_PAYLOAD_REQUIRED")
    if not payload:
        _fail("ACTION_PAYLOAD_REQUIRED", field)
    for key in payload:
        if not isinstance(key, str) or not _ID_RE.fullmatch(key):
            _fail("INVALID_PAYLOAD_KEY", field)
    canonical_json(payload)
    return payload


def normalize_packet(raw: Any) -> dict[str, Any]:
    packet = _obj(copy.deepcopy(raw), "PACKET_REQUIRED")
    _exact_keys(
        packet,
        (
            "schema_version",
            "exception_id",
            "as_of",
            "snapshot_policy",
            "origin",
            "partner",
            "snapshot",
            "agent",
            "permission",
            "basis",
            "recommendation",
            "final_action",
            "approval",
        ),
        "PACKET_FIELDS",
    )
    if packet["schema_version"] != SCHEMA:
        _fail("SCHEMA_MISMATCH")

    exception_id = _identifier(packet["exception_id"], "exception_id")
    as_of, as_of_dt = _timestamp(packet["as_of"], "as_of")

    policy = _obj(packet["snapshot_policy"], "SNAPSHOT_POLICY_REQUIRED")
    _exact_keys(policy, ("policy_id", "max_age_minutes"), "SNAPSHOT_POLICY_FIELDS")
    policy_id = _string(policy["policy_id"], "snapshot_policy.policy_id")
    max_age_minutes = _positive_int(policy["max_age_minutes"], "snapshot_policy.max_age_minutes")
    if policy_id != SNAPSHOT_POLICY_ID or max_age_minutes != SNAPSHOT_MAX_AGE_MINUTES:
        _fail("SNAPSHOT_POLICY_MISMATCH")
    policy_n = {"policy_id": policy_id, "max_age_minutes": max_age_minutes}

    origin = _obj(packet["origin"], "ORIGIN_REQUIRED")
    _exact_keys(origin, ("po_id", "asn_id", "epcis_event_ids", "quality_event_ids"), "ORIGIN_FIELDS")
    origin_n = {
        "po_id": _identifier(origin["po_id"], "origin.po_id"),
        "asn_id": _identifier(origin["asn_id"], "origin.asn_id"),
        "epcis_event_ids": _normalize_id_list(origin["epcis_event_ids"], "origin.epcis_event_ids"),
        "quality_event_ids": _normalize_id_list(origin["quality_event_ids"], "origin.quality_event_ids"),
    }
    if not origin_n["epcis_event_ids"]:
        _fail("EPCIS_EVIDENCE_REQUIRED")

    partner = _obj(packet["partner"], "PARTNER_REQUIRED")
    _exact_keys(partner, ("partner_id", "authenticated", "trust_state", "identity_digest"), "PARTNER_FIELDS")
    trust_state = _string(partner["trust_state"], "partner.trust_state")
    if trust_state not in {"TRUSTED", "UNTRUSTED"}:
        _fail("INVALID_TRUST_STATE")
    partner_n = {
        "partner_id": _identifier(partner["partner_id"], "partner.partner_id"),
        "authenticated": _bool(partner["authenticated"], "partner.authenticated"),
        "trust_state": trust_state,
        "identity_digest": _digest(partner["identity_digest"], "partner.identity_digest"),
    }
    expected_partner_digest = sha256({
        "partner_id": partner_n["partner_id"],
        "authenticated": partner_n["authenticated"],
        "trust_state": partner_n["trust_state"],
    })
    if partner_n["identity_digest"] != expected_partner_digest:
        _fail("PARTNER_IDENTITY_DIGEST_MISMATCH")

    snapshot = _obj(packet["snapshot"], "SNAPSHOT_REQUIRED")
    _exact_keys(snapshot, ("object_version", "data_snapshot_version", "captured_at", "snapshot_digest"), "SNAPSHOT_FIELDS")
    captured_at, captured_dt = _timestamp(snapshot["captured_at"], "snapshot.captured_at")
    if captured_dt > as_of_dt:
        _fail("EVIDENCE_AFTER_AS_OF", "snapshot.captured_at")
    snapshot_n = {
        "object_version": _version(snapshot["object_version"], "snapshot.object_version"),
        "data_snapshot_version": _version(snapshot["data_snapshot_version"], "snapshot.data_snapshot_version"),
        "captured_at": captured_at,
        "snapshot_digest": _digest(snapshot["snapshot_digest"], "snapshot.snapshot_digest"),
    }
    expected_snapshot_digest = sha256({
        "object_version": snapshot_n["object_version"],
        "data_snapshot_version": snapshot_n["data_snapshot_version"],
        "captured_at": snapshot_n["captured_at"],
    })
    if snapshot_n["snapshot_digest"] != expected_snapshot_digest:
        _fail("SNAPSHOT_DIGEST_MISMATCH")

    agent = _obj(packet["agent"], "AGENT_REQUIRED")
    _exact_keys(agent, ("rule_version", "agent_profile_version"), "AGENT_FIELDS")
    agent_n = {
        "rule_version": _version(agent["rule_version"], "agent.rule_version"),
        "agent_profile_version": _version(agent["agent_profile_version"], "agent.agent_profile_version", allow_empty=True),
    }

    permission = _obj(packet["permission"], "PERMISSION_REQUIRED")
    _exact_keys(permission, ("role_id", "granted_permissions", "required_permission"), "PERMISSION_FIELDS")
    raw_grants = permission["granted_permissions"]
    if not isinstance(raw_grants, list):
        _fail("LIST_REQUIRED", "permission.granted_permissions")
    grants = [_permission(value, f"permission.granted_permissions[{i}]") for i, value in enumerate(raw_grants)]
    if len(set(grants)) != len(grants):
        _fail("DUPLICATE_PERMISSION")
    permission_n = {
        "role_id": _identifier(permission["role_id"], "permission.role_id"),
        "granted_permissions": sorted(grants),
        "required_permission": _permission(permission["required_permission"], "permission.required_permission"),
    }

    basis = packet["basis"]
    if not isinstance(basis, list) or not basis:
        _fail("BASIS_REQUIRED")
    basis_n: list[dict[str, str]] = []
    seen_sources: set[str] = set()
    for i, raw_item in enumerate(basis):
        item = _obj(raw_item, "BASIS_ITEM_REQUIRED")
        _exact_keys(item, ("source_id", "source_digest"), "BASIS_ITEM_FIELDS")
        source_id = _identifier(item["source_id"], f"basis[{i}].source_id")
        if source_id in seen_sources:
            _fail("DUPLICATE_BASIS_SOURCE", source_id)
        seen_sources.add(source_id)
        basis_n.append({
            "source_id": source_id,
            "source_digest": _digest(item["source_digest"], f"basis[{i}].source_digest"),
        })
    basis_n.sort(key=lambda item: item["source_id"])

    recommendation = _obj(packet["recommendation"], "RECOMMENDATION_REQUIRED")
    _exact_keys(
        recommendation,
        ("action_type", "action_payload", "action_hash", "origin_po_id", "origin_asn_id"),
        "RECOMMENDATION_FIELDS",
    )
    recommendation_payload = _normalize_payload(recommendation["action_payload"], "recommendation.action_payload")
    recommendation_n = {
        "action_type": _identifier(recommendation["action_type"], "recommendation.action_type"),
        "action_payload": recommendation_payload,
        "action_hash": _digest(recommendation["action_hash"], "recommendation.action_hash"),
        "origin_po_id": _identifier(recommendation["origin_po_id"], "recommendation.origin_po_id"),
        "origin_asn_id": _identifier(recommendation["origin_asn_id"], "recommendation.origin_asn_id"),
    }
    expected_recommendation_hash = sha256({
        "action_type": recommendation_n["action_type"],
        "action_payload": recommendation_n["action_payload"],
    })
    if recommendation_n["action_hash"] != expected_recommendation_hash:
        _fail("RECOMMENDATION_HASH_MISMATCH")

    final_action = _obj(packet["final_action"], "FINAL_ACTION_REQUIRED")
    _exact_keys(final_action, ("action_type", "action_payload", "action_hash", "recommendation_hash"), "FINAL_ACTION_FIELDS")
    final_payload = _normalize_payload(final_action["action_payload"], "final_action.action_payload")
    final_action_n = {
        "action_type": _identifier(final_action["action_type"], "final_action.action_type"),
        "action_payload": final_payload,
        "action_hash": _digest(final_action["action_hash"], "final_action.action_hash"),
        "recommendation_hash": _digest(final_action["recommendation_hash"], "final_action.recommendation_hash"),
    }

    approval = _obj(packet["approval"], "APPROVAL_REQUIRED")
    _exact_keys(approval, ("approved", "approver_id", "approved_action_hash", "approval_digest"), "APPROVAL_FIELDS")
    approver_id = _string(approval["approver_id"], "approval.approver_id", allow_empty=True)
    if approver_id and not _ID_RE.fullmatch(approver_id):
        _fail("INVALID_IDENTIFIER", "approval.approver_id")
    approval_n = {
        "approved": _bool(approval["approved"], "approval.approved"),
        "approver_id": approver_id,
        "approved_action_hash": _digest(approval["approved_action_hash"], "approval.approved_action_hash"),
        "approval_digest": _digest(approval["approval_digest"], "approval.approval_digest"),
    }
    expected_approval_digest = sha256({
        "approved": approval_n["approved"],
        "approver_id": approval_n["approver_id"],
        "approved_action_hash": approval_n["approved_action_hash"],
    })
    if approval_n["approval_digest"] != expected_approval_digest:
        _fail("APPROVAL_DIGEST_MISMATCH")

    return {
        "schema_version": SCHEMA,
        "exception_id": exception_id,
        "as_of": as_of,
        "snapshot_policy": policy_n,
        "origin": origin_n,
        "partner": partner_n,
        "snapshot": snapshot_n,
        "agent": agent_n,
        "permission": permission_n,
        "basis": basis_n,
        "recommendation": recommendation_n,
        "final_action": final_action_n,
        "approval": approval_n,
    }


def evaluate(raw_packet: Any) -> dict[str, Any]:
    packet = normalize_packet(raw_packet)
    reasons: list[str] = []

    partner = packet["partner"]
    if not partner["authenticated"] or partner["trust_state"] != "TRUSTED":
        reasons.append("UNTRUSTED_PARTNER")

    as_of_dt = _timestamp(packet["as_of"], "as_of")[1]
    captured_dt = _timestamp(packet["snapshot"]["captured_at"], "snapshot.captured_at")[1]
    snapshot_age_minutes = int((as_of_dt - captured_dt).total_seconds() // 60)
    if snapshot_age_minutes > packet["snapshot_policy"]["max_age_minutes"]:
        reasons.append("STALE_SNAPSHOT")

    origin = packet["origin"]
    recommendation = packet["recommendation"]
    if recommendation["origin_po_id"] != origin["po_id"] or recommendation["origin_asn_id"] != origin["asn_id"]:
        reasons.append("PO_ASN_MISMATCH")

    if packet["agent"]["agent_profile_version"] == "":
        reasons.append("MISSING_AGENT_PROFILE_VERSION")

    permission = packet["permission"]
    if permission["required_permission"] not in permission["granted_permissions"]:
        reasons.append("PERMISSION_OUT_OF_SCOPE")

    approval = packet["approval"]
    if not approval["approved"] or approval["approver_id"] == "":
        reasons.append("MISSING_HUMAN_APPROVAL")

    final_action = packet["final_action"]
    derived_final_action_hash = sha256({
        "action_type": final_action["action_type"],
        "action_payload": final_action["action_payload"],
    })
    if (
        final_action["action_hash"] != derived_final_action_hash
        or final_action["recommendation_hash"] != recommendation["action_hash"]
        or (approval["approved"] and approval["approved_action_hash"] != final_action["action_hash"])
    ):
        reasons.append("FINAL_ACTION_HASH_MISMATCH")

    reasons = [reason for reason in _REASON_ORDER if reason in reasons]
    evidence_digests = sorted(
        [partner["identity_digest"], packet["snapshot"]["snapshot_digest"], approval["approval_digest"]]
        + [item["source_digest"] for item in packet["basis"]]
    )
    source_digest = sha256(packet)
    core = {
        "schema_version": DECISION_SCHEMA,
        "exception_id": packet["exception_id"],
        "as_of": packet["as_of"],
        "status": "REVIEW_READY" if not reasons else "HOLD",
        "hold_reasons": reasons,
        "snapshot_age_minutes": snapshot_age_minutes,
        "source_digest": source_digest,
        "evidence_digests": evidence_digests,
        "decision_bindings": {
            "rule_version": packet["agent"]["rule_version"],
            "agent_profile_version": packet["agent"]["agent_profile_version"],
            "recommended_action_hash": recommendation["action_hash"],
            "final_action_declared_hash": final_action["action_hash"],
            "final_action_derived_hash": derived_final_action_hash,
            "approved_action_hash": approval["approved_action_hash"],
        },
        "authority": {
            "order_change": False,
            "shipment_change": False,
            "allocation_change": False,
            "recall": False,
            "dscsa_filing": False,
            "quality_disposition": False,
            "partner_message": False,
            "provider_mutation": False,
        },
    }
    return {**core, "receipt_digest": sha256(core)}


def verify_decision(
    raw_packet: Any,
    raw_decision: Any,
    *,
    verify_at: str,
    max_decision_age_minutes: int = 24 * 60,
) -> dict[str, Any]:
    if type(max_decision_age_minutes) is not int or isinstance(max_decision_age_minutes, bool) or max_decision_age_minutes < 1:
        _fail("INVALID_MAX_DECISION_AGE")
    decision = _obj(copy.deepcopy(raw_decision), "DECISION_REQUIRED")
    expected = evaluate(raw_packet)
    if canonical_json(decision) != canonical_json(expected):
        _fail("DECISION_MISMATCH")
    verify_at_s, verify_dt = _timestamp(verify_at, "verify_at")
    as_of_dt = _timestamp(expected["as_of"], "decision.as_of")[1]
    if verify_dt < as_of_dt:
        _fail("VERIFY_BEFORE_AS_OF")
    age_minutes = int((verify_dt - as_of_dt).total_seconds() // 60)
    if age_minutes > max_decision_age_minutes:
        _fail("DECISION_STALE")
    return {
        "valid": True,
        "fresh": True,
        "verify_at": verify_at_s,
        "age_minutes": age_minutes,
        "receipt_digest": expected["receipt_digest"],
        "status": expected["status"],
    }
