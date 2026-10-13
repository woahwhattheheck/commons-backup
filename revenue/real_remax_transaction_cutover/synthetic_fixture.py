from __future__ import annotations

from typing import Any

from .schema import SCHEMA_IDENTITY_MAP, SCHEMA_POLICY, SCHEMA_SNAPSHOT


def build_synthetic_bundle(transaction_count: int = 240) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if transaction_count < 1:
        raise ValueError("transaction_count must be positive")
    policy = {
        "schema": SCHEMA_POLICY,
        "policy_id": "real-remax-synthetic-cutover",
        "generation": 1,
        "source_system": "REAL_LEGACY",
        "target_system": "REMAX_TARGET",
        "active_source_stages": ["PENDING", "UNDER_CONTRACT"],
        "stage_map": {"PENDING": "PENDING", "UNDER_CONTRACT": "UNDER_CONTRACT", "CLOSED": "CLOSED"},
        "status_map": {"ACTIVE": "ACTIVE", "HOLD": "HOLD", "COMPLETE": "COMPLETE"},
        "required_relationship_roles": ["LISTING_AGENT", "BUYER_AGENT"],
    }
    source_offices = [{"office_id": f"SO{i:02d}", "name": f"Source Office {i:02d}"} for i in range(1, 5)]
    target_offices = [{"office_id": f"TO{i:02d}", "name": f"Target Office {i:02d}"} for i in range(1, 5)]
    source_agents = [{"agent_id": f"SA{i:03d}", "office_id": f"SO{((i - 1) % 4) + 1:02d}"} for i in range(1, 33)]
    target_agents = [{"agent_id": f"TA{i:03d}", "office_id": f"TO{((i - 1) % 4) + 1:02d}"} for i in range(1, 33)]
    source_transactions = []
    target_transactions = []
    txn_map = []
    for i in range(1, transaction_count + 1):
        listing = ((i * 2 - 1) % 32) + 1
        buyer = ((i * 2) % 32) + 1
        gross = 100_000 + i * 137
        first = gross // 2
        second = gross - first
        stage = "PENDING" if i % 2 else "UNDER_CONTRACT"
        status = "HOLD" if i % 17 == 0 else "ACTIVE"
        source_transactions.append({
            "transaction_id": f"STX{i:05d}",
            "stage": stage,
            "status": status,
            "gross_commission_cents": gross,
            "relationships": [
                {"role": "LISTING_AGENT", "agent_id": f"SA{listing:03d}", "split_bps": 5000, "commission_cents": first},
                {"role": "BUYER_AGENT", "agent_id": f"SA{buyer:03d}", "split_bps": 5000, "commission_cents": second},
            ],
        })
        target_transactions.append({
            "transaction_id": f"TTX{i:05d}",
            "stage": stage,
            "status": status,
            "gross_commission_cents": gross,
            "relationships": [
                {"role": "BUYER_AGENT", "agent_id": f"TA{buyer:03d}", "split_bps": 5000, "commission_cents": second},
                {"role": "LISTING_AGENT", "agent_id": f"TA{listing:03d}", "split_bps": 5000, "commission_cents": first},
            ],
        })
        txn_map.append({"source_transaction_id": f"STX{i:05d}", "target_transaction_id": f"TTX{i:05d}"})
    source = {
        "schema": SCHEMA_SNAPSHOT,
        "snapshot_id": "source-gen-001",
        "generation": 1,
        "system": "REAL_LEGACY",
        "offices": source_offices,
        "agents": source_agents,
        "transactions": source_transactions,
    }
    target = {
        "schema": SCHEMA_SNAPSHOT,
        "snapshot_id": "target-gen-001",
        "generation": 1,
        "system": "REMAX_TARGET",
        "offices": target_offices,
        "agents": target_agents,
        "transactions": target_transactions,
    }
    identity_map = {
        "schema": SCHEMA_IDENTITY_MAP,
        "source_snapshot_id": source["snapshot_id"],
        "target_snapshot_id": target["snapshot_id"],
        "offices": [{"source_office_id": f"SO{i:02d}", "target_office_id": f"TO{i:02d}"} for i in range(1, 5)],
        "agents": [{"source_agent_id": f"SA{i:03d}", "target_agent_id": f"TA{i:03d}"} for i in range(1, 33)],
        "transactions": txn_map,
    }
    return source, target, identity_map, policy
