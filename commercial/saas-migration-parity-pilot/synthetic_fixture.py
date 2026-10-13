#!/usr/bin/env python3
"""Emit the deterministic 500-source/500-target synthetic acceptance fixture."""
from __future__ import annotations

import json
import sys
from typing import Any


def build_manifest() -> dict[str, Any]:
    source = []
    target = []
    plans = ("basic", "pro", "team")
    for i in range(1, 501):
        rid = f"R{i:04d}"
        source.append({"fields": {
            "legacy_id": rid,
            "customer_name": f"Customer {i:04d}",
            "amount_cents": 10000 + i * 7,
            "active": i % 3 != 0,
            "plan": plans[i % 3],
        }})
    for i in range(1, 496):
        rid = f"R{i:04d}"
        amount = 10000 + i * 7
        if 491 <= i <= 495:
            amount += 100 + i
        target.append({"fields": {
            "external_id": rid,
            "name": f"Customer {i:04d}",
            "balance_cents": amount,
            "enabled": i % 3 != 0,
            "plan_code": plans[i % 3],
        }})
    for i in range(501, 506):
        rid = f"R{i:04d}"
        target.append({"fields": {
            "external_id": rid,
            "name": f"Customer {i:04d}",
            "balance_cents": 10000 + i * 7,
            "enabled": i % 3 != 0,
            "plan_code": plans[i % 3],
        }})
    return {
        "schema": "saas-migration-parity-pilot/v1",
        "cutover_at_utc": "2026-09-15T18:00:00Z",
        "max_snapshot_age_seconds": 86400,
        "key_map": [{"source": "legacy_id", "target": "external_id", "type": "string"}],
        "field_map": [
            {"source": "customer_name", "target": "name", "type": "string"},
            {"source": "amount_cents", "target": "balance_cents", "type": "integer"},
            {"source": "active", "target": "enabled", "type": "boolean"},
            {"source": "plan", "target": "plan_code", "type": "string"},
        ],
        "source_snapshot": {
            "snapshot_id": "source-export-20260915",
            "schema_revision": "legacy-v7",
            "captured_at_utc": "2026-09-15T12:00:00Z",
            "complete": True,
            "records": source,
        },
        "target_snapshot": {
            "snapshot_id": "target-export-20260915",
            "schema_revision": "saas-v3",
            "captured_at_utc": "2026-09-15T12:05:00Z",
            "complete": True,
            "records": target,
        },
    }


def fixture_bytes() -> bytes:
    return (json.dumps(build_manifest(), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


if __name__ == "__main__":
    sys.stdout.buffer.write(fixture_bytes())
