from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from .schema import (
    CutoverError, MAX_FINDINGS, SCHEMA_REPORT, _sha, _unique_index,
    _validate_identity_map, _validate_policy, _validate_snapshot, canonical_bytes, digest,
)

def _finding(code: str, *, transaction_id: str | None = None, detail: str) -> dict[str, Any]:
    row: dict[str, Any] = {"code": code, "detail": detail}
    if transaction_id is not None:
        row["transaction_id"] = transaction_id
    return row


def _add_finding(findings: list[dict[str, Any]], row: dict[str, Any]) -> None:
    findings.append(row)
    if len(findings) > MAX_FINDINGS:
        raise CutoverError(f"cutover produces more than {MAX_FINDINGS} findings")


def _relationship_key(rel: Mapping[str, Any], agent_map: Mapping[str, str]) -> tuple[str, str, int, int]:
    source_agent = str(rel["agent_id"])
    target_agent = agent_map.get(source_agent, "")
    return (str(rel["role"]), target_agent, int(rel["split_bps"]), int(rel["commission_cents"]))


def _policy_evidence(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **policy,
        "active_source_stages": sorted(policy["active_source_stages"]),
        "required_relationship_roles": sorted(policy["required_relationship_roles"]),
    }


def _snapshot_evidence(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    transactions = []
    for txn in snapshot["transactions"]:
        transactions.append({
            **txn,
            "relationships": sorted(
                (dict(rel) for rel in txn["relationships"]),
                key=lambda rel: (rel["role"], rel["agent_id"], rel["split_bps"], rel["commission_cents"]),
            ),
        })
    return {
        **snapshot,
        "offices": sorted((dict(row) for row in snapshot["offices"]), key=lambda row: row["office_id"]),
        "agents": sorted((dict(row) for row in snapshot["agents"]), key=lambda row: row["agent_id"]),
        "transactions": sorted(transactions, key=lambda row: row["transaction_id"]),
    }


def _map_evidence(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **mapping,
        "offices": sorted((dict(row) for row in mapping["offices"]), key=lambda row: (row["source_office_id"], row["target_office_id"])),
        "agents": sorted((dict(row) for row in mapping["agents"]), key=lambda row: (row["source_agent_id"], row["target_agent_id"])),
        "transactions": sorted((dict(row) for row in mapping["transactions"]), key=lambda row: (row["source_transaction_id"], row["target_transaction_id"])),
    }


def compile_cutover(
    source_snapshot: Any,
    target_snapshot: Any,
    identity_map: Any,
    policy: Any,
) -> dict[str, Any]:
    p = _validate_policy(policy)
    source = _validate_snapshot(source_snapshot, name="source_snapshot", expected_system=str(p["source_system"]))
    target = _validate_snapshot(target_snapshot, name="target_snapshot", expected_system=str(p["target_system"]))
    mapping, office_map, agent_map, txn_map = _validate_identity_map(identity_map, source, target)

    source_offices = _unique_index(source["offices"], "office_id", name="source office")
    target_offices = _unique_index(target["offices"], "office_id", name="target office")
    source_agents = _unique_index(source["agents"], "agent_id", name="source agent")
    target_agents = _unique_index(target["agents"], "agent_id", name="target agent")
    source_txns = _unique_index(source["transactions"], "transaction_id", name="source transaction")
    target_txns = _unique_index(target["transactions"], "transaction_id", name="target transaction")

    for source_id, target_id in office_map.items():
        if source_id not in source_offices:
            raise CutoverError(f"identity map office source does not exist: {source_id}")
        if target_id not in target_offices:
            raise CutoverError(f"identity map office target does not exist: {target_id}")
    for source_id, target_id in agent_map.items():
        if source_id not in source_agents:
            raise CutoverError(f"identity map agent source does not exist: {source_id}")
        if target_id not in target_agents:
            raise CutoverError(f"identity map agent target does not exist: {target_id}")
    for source_id, target_id in txn_map.items():
        if source_id not in source_txns:
            raise CutoverError(f"identity map transaction source does not exist: {source_id}")
        if target_id not in target_txns:
            raise CutoverError(f"identity map transaction target does not exist: {target_id}")

    findings: list[dict[str, Any]] = []
    active_source_stages = set(str(v) for v in p["active_source_stages"])
    stage_map = {str(k): str(v) for k, v in p["stage_map"].items()}
    status_map = {str(k): str(v) for k, v in p["status_map"].items()}
    required_roles = set(str(v) for v in p["required_relationship_roles"])

    for source_office_id, source_office in sorted(source_offices.items()):
        target_office_id = office_map.get(source_office_id)
        if target_office_id is None:
            _add_finding(findings, _finding("OFFICE_MAP_MISSING", detail=f"source office {source_office_id} has no target mapping"))
        elif target_office_id not in target_offices:
            _add_finding(findings, _finding("OFFICE_TARGET_MISSING", detail=f"mapped target office {target_office_id} does not exist"))

    for source_agent_id, source_agent in sorted(source_agents.items()):
        target_agent_id = agent_map.get(source_agent_id)
        if target_agent_id is None:
            _add_finding(findings, _finding("AGENT_MAP_MISSING", detail=f"source agent {source_agent_id} has no target mapping"))
            continue
        target_agent = target_agents.get(target_agent_id)
        if target_agent is None:
            _add_finding(findings, _finding("AGENT_TARGET_MISSING", detail=f"mapped target agent {target_agent_id} does not exist"))
            continue
        expected_target_office = office_map.get(str(source_agent["office_id"]))
        if expected_target_office is None:
            continue
        if target_agent["office_id"] != expected_target_office:
            _add_finding(findings, _finding("AGENT_OFFICE_MISMATCH", detail=f"source agent {source_agent_id} maps to target agent {target_agent_id} in wrong target office"))

    active_ids: list[str] = []
    parity_ids: list[str] = []
    for source_txn_id, source_txn in sorted(source_txns.items()):
        if source_txn["stage"] not in active_source_stages:
            continue
        active_ids.append(source_txn_id)
        transaction_findings_start = len(findings)
        target_txn_id = txn_map.get(source_txn_id)
        if target_txn_id is None:
            _add_finding(findings, _finding("TRANSACTION_MAP_MISSING", transaction_id=source_txn_id, detail="active source transaction has no target mapping"))
            continue
        target_txn = target_txns.get(target_txn_id)
        if target_txn is None:
            _add_finding(findings, _finding("TRANSACTION_TARGET_MISSING", transaction_id=source_txn_id, detail=f"mapped target transaction {target_txn_id} does not exist"))
            continue

        expected_stage = stage_map.get(str(source_txn["stage"]))
        if expected_stage is None:
            _add_finding(findings, _finding("STAGE_POLICY_MISSING", transaction_id=source_txn_id, detail=f"policy has no stage mapping for {source_txn['stage']}"))
        elif target_txn["stage"] != expected_stage:
            _add_finding(findings, _finding("STAGE_MISMATCH", transaction_id=source_txn_id, detail=f"expected target stage {expected_stage}, got {target_txn['stage']}"))

        expected_status = status_map.get(str(source_txn["status"]))
        if expected_status is None:
            _add_finding(findings, _finding("STATUS_POLICY_MISSING", transaction_id=source_txn_id, detail=f"policy has no status mapping for {source_txn['status']}"))
        elif target_txn["status"] != expected_status:
            _add_finding(findings, _finding("STATUS_MISMATCH", transaction_id=source_txn_id, detail=f"expected target status {expected_status}, got {target_txn['status']}"))

        if target_txn["gross_commission_cents"] != source_txn["gross_commission_cents"]:
            _add_finding(findings, _finding("GROSS_COMMISSION_MISMATCH", transaction_id=source_txn_id, detail=f"expected {source_txn['gross_commission_cents']} cents, got {target_txn['gross_commission_cents']}"))

        source_roles = Counter(str(rel["role"]) for rel in source_txn["relationships"])
        for role in sorted(required_roles):
            if source_roles[role] == 0:
                _add_finding(findings, _finding("REQUIRED_SOURCE_ROLE_MISSING", transaction_id=source_txn_id, detail=f"required role {role} missing in source"))

        expected_relationships: list[tuple[str, str, int, int]] = []
        unmapped_agent = False
        for rel in source_txn["relationships"]:
            source_agent_id = str(rel["agent_id"])
            if source_agent_id not in agent_map:
                _add_finding(findings, _finding("RELATIONSHIP_AGENT_MAP_MISSING", transaction_id=source_txn_id, detail=f"source relationship agent {source_agent_id} has no target mapping"))
                unmapped_agent = True
                continue
            target_agent_id = agent_map[source_agent_id]
            target_agent = target_agents.get(target_agent_id)
            if target_agent is None:
                _add_finding(findings, _finding("RELATIONSHIP_AGENT_TARGET_MISSING", transaction_id=source_txn_id, detail=f"mapped target relationship agent {target_agent_id} does not exist"))
                unmapped_agent = True
                continue
            source_agent = source_agents[source_agent_id]
            expected_target_office = office_map.get(str(source_agent["office_id"]))
            if expected_target_office is None:
                _add_finding(findings, _finding("RELATIONSHIP_OFFICE_MAP_MISSING", transaction_id=source_txn_id, detail=f"source relationship agent {source_agent_id} office has no target mapping"))
            elif target_agent["office_id"] != expected_target_office:
                _add_finding(findings, _finding("RELATIONSHIP_AGENT_OFFICE_MISMATCH", transaction_id=source_txn_id, detail=f"source relationship agent {source_agent_id} maps to target agent {target_agent_id} in wrong target office"))
            expected_relationships.append(_relationship_key(rel, agent_map))
        actual_relationships = sorted(
            (str(rel["role"]), str(rel["agent_id"]), int(rel["split_bps"]), int(rel["commission_cents"]))
            for rel in target_txn["relationships"]
        )
        if not unmapped_agent and sorted(expected_relationships) != actual_relationships:
            _add_finding(findings, _finding("RELATIONSHIP_MISMATCH", transaction_id=source_txn_id, detail="role/agent/split/commission relationship set differs after identity mapping"))

        if len(findings) == transaction_findings_start:
            parity_ids.append(source_txn_id)

    findings.sort(key=lambda row: (row.get("transaction_id", ""), row["code"], row["detail"]))
    code_counts = Counter(row["code"] for row in findings)
    report: dict[str, Any] = {
        "schema": SCHEMA_REPORT,
        "decision": "PARITY" if not findings else "HOLD",
        "authority": {
            "production_mutation_authorized": False,
            "buyer_acceptance_proven": False,
            "payment_proven": False,
            "revenue_proven": False,
        },
        "evidence": {
            "policy_sha256": digest(_policy_evidence(p)),
            "source_snapshot_sha256": digest(_snapshot_evidence(source)),
            "target_snapshot_sha256": digest(_snapshot_evidence(target)),
            "identity_map_sha256": digest(_map_evidence(mapping)),
        },
        "summary": {
            "active_source_transactions": len(active_ids),
            "parity_transactions": len(parity_ids),
            "hold_transactions": len(active_ids) - len(parity_ids),
            "finding_count": len(findings),
            "finding_code_counts": dict(sorted(code_counts.items())),
        },
        "active_source_transaction_ids": sorted(active_ids),
        "parity_transaction_ids": sorted(parity_ids),
        "findings": findings,
    }
    report["receipt_sha256"] = digest(report)
    return report


def verify_report(
    source_snapshot: Any,
    target_snapshot: Any,
    identity_map: Any,
    policy: Any,
    report: Any,
) -> bool:
    if type(report) is not dict:
        return False
    supplied = dict(report)
    receipt = supplied.pop("receipt_sha256", None)
    if type(receipt) is not str or len(receipt) != 64:
        return False
    try:
        _sha(receipt, name="report.receipt_sha256")
        if digest(supplied) != receipt:
            return False
        expected = compile_cutover(source_snapshot, target_snapshot, identity_map, policy)
    except CutoverError:
        return False
    return canonical_bytes(expected) == canonical_bytes(report)
