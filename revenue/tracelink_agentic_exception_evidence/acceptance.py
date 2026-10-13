from __future__ import annotations

import copy
from collections import Counter

from .gate import SCHEMA, SNAPSHOT_MAX_AGE_MINUTES, SNAPSHOT_POLICY_ID, evaluate, sha256, verify_decision

AS_OF = "2026-09-13T12:00:00Z"
VERIFY_AT = "2026-09-13T12:30:00Z"
CAPTURED_AT = "2026-09-13T11:50:00Z"
D = lambda c: c * 64


def _action_hash(action_type: str, action_payload: dict) -> str:
    return sha256({"action_type": action_type, "action_payload": action_payload})


def _partner_digest(partner_id: str, authenticated: bool, trust_state: str) -> str:
    return sha256({"partner_id": partner_id, "authenticated": authenticated, "trust_state": trust_state})


def _approval_digest(approved: bool, approver_id: str, approved_action_hash: str) -> str:
    return sha256({"approved": approved, "approver_id": approver_id, "approved_action_hash": approved_action_hash})


def _snapshot_digest(object_version: str, data_snapshot_version: str, captured_at: str) -> str:
    return sha256({
        "object_version": object_version,
        "data_snapshot_version": data_snapshot_version,
        "captured_at": captured_at,
    })


def base_packet(index: int) -> dict:
    po_id = f"PO-{index:04d}"
    asn_id = f"ASN-{index:04d}"
    action_type = "REVIEW_EXCEPTION"
    action_payload = {"exception": f"EX-{index:04d}", "recommended_state": "OWNER_REVIEW"}
    recommendation_hash = _action_hash(action_type, action_payload)
    final_payload = copy.deepcopy(action_payload)
    final_hash = _action_hash(action_type, final_payload)
    object_version = "obj-v3"
    data_snapshot_version = f"snapshot-{index:04d}-v1"
    return {
        "schema_version": SCHEMA,
        "exception_id": f"EX-{index:04d}",
        "as_of": AS_OF,
        "snapshot_policy": {"policy_id": SNAPSHOT_POLICY_ID, "max_age_minutes": SNAPSHOT_MAX_AGE_MINUTES},
        "origin": {
            "po_id": po_id,
            "asn_id": asn_id,
            "epcis_event_ids": [f"EPCIS-{index:04d}-01", f"EPCIS-{index:04d}-02"],
            "quality_event_ids": [f"QEV-{index:04d}-01"],
        },
        "partner": {
            "partner_id": "partner-alpha",
            "authenticated": True,
            "trust_state": "TRUSTED",
            "identity_digest": _partner_digest("partner-alpha", True, "TRUSTED"),
        },
        "snapshot": {
            "object_version": object_version,
            "data_snapshot_version": data_snapshot_version,
            "captured_at": CAPTURED_AT,
            "snapshot_digest": _snapshot_digest(object_version, data_snapshot_version, CAPTURED_AT),
        },
        "agent": {
            "rule_version": "rule-v7",
            "agent_profile_version": "agent-profile-v4",
        },
        "permission": {
            "role_id": "supply-owner",
            "granted_permissions": ["exception.review", "exception.approve"],
            "required_permission": "exception.approve",
        },
        "basis": [
            {"source_id": "po-asn-ledger", "source_digest": D("b")},
            {"source_id": "quality-event-ledger", "source_digest": D("c")},
        ],
        "recommendation": {
            "action_type": action_type,
            "action_payload": action_payload,
            "action_hash": recommendation_hash,
            "origin_po_id": po_id,
            "origin_asn_id": asn_id,
        },
        "final_action": {
            "action_type": action_type,
            "action_payload": final_payload,
            "action_hash": final_hash,
            "recommendation_hash": recommendation_hash,
        },
        "approval": {
            "approved": True,
            "approver_id": "owner-01",
            "approved_action_hash": final_hash,
            "approval_digest": _approval_digest(True, "owner-01", final_hash),
        },
    }


def packet_for(index: int) -> dict:
    packet = base_packet(index)
    if index < 112:
        return packet
    defect = (index - 112) // 4
    if defect == 0:
        packet["partner"]["authenticated"] = False
        packet["partner"]["trust_state"] = "UNTRUSTED"
        packet["partner"]["identity_digest"] = _partner_digest(packet["partner"]["partner_id"], False, "UNTRUSTED")
    elif defect == 1:
        packet["snapshot"]["captured_at"] = "2026-09-13T10:00:00Z"
        packet["snapshot"]["snapshot_digest"] = _snapshot_digest(
            packet["snapshot"]["object_version"],
            packet["snapshot"]["data_snapshot_version"],
            packet["snapshot"]["captured_at"],
        )
    elif defect == 2:
        packet["recommendation"]["origin_asn_id"] = f"ASN-WRONG-{index:04d}"
    elif defect == 3:
        packet["agent"]["agent_profile_version"] = ""
    elif defect == 4:
        packet["permission"]["granted_permissions"] = ["exception.review"]
    elif defect == 5:
        packet["approval"]["approved"] = False
        packet["approval"]["approver_id"] = ""
        packet["approval"]["approval_digest"] = _approval_digest(False, "", packet["approval"]["approved_action_hash"])
    elif defect == 6:
        packet["final_action"]["action_hash"] = D("9")
    else:
        raise RuntimeError(f"unexpected acceptance index: {index}")
    return packet


def build_suite() -> list[dict]:
    return [packet_for(i) for i in range(140)]


def run_acceptance() -> dict:
    packets = build_suite()
    decisions = [evaluate(packet) for packet in packets]
    for packet, decision in zip(packets, decisions):
        verify_decision(packet, decision, verify_at=VERIFY_AT)

    status_counts = Counter(decision["status"] for decision in decisions)
    reason_counts = Counter(reason for decision in decisions for reason in decision["hold_reasons"])
    expected_status = Counter({"REVIEW_READY": 112, "HOLD": 28})
    expected_reasons = {
        "UNTRUSTED_PARTNER": 4,
        "STALE_SNAPSHOT": 4,
        "PO_ASN_MISMATCH": 4,
        "MISSING_AGENT_PROFILE_VERSION": 4,
        "PERMISSION_OUT_OF_SCOPE": 4,
        "MISSING_HUMAN_APPROVAL": 4,
        "FINAL_ACTION_HASH_MISMATCH": 4,
    }
    if status_counts != expected_status:
        raise RuntimeError(f"unexpected status counts: {status_counts}")
    if dict(reason_counts) != expected_reasons:
        raise RuntimeError(f"unexpected reason counts: {dict(reason_counts)}")

    replay = [evaluate(packet) for packet in copy.deepcopy(packets)]
    if [decision["receipt_digest"] for decision in replay] != [decision["receipt_digest"] for decision in decisions]:
        raise RuntimeError("receipt replay was not byte-stable")

    report = {
        "schema_version": "tracelink.agentic-exception-acceptance/v1",
        "packet_count": 140,
        "review_ready_count": 112,
        "hold_count": 28,
        "reason_counts": expected_reasons,
        "receipt_set_digest": sha256([decision["receipt_digest"] for decision in decisions]),
    }
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(run_acceptance(), sort_keys=True, indent=2))
