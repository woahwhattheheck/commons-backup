#!/usr/bin/env python3
"""Emit deterministic, read-only Jeffersonville adapter and benchmark plans."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
CATALOG_FILE = BASE_DIR / "frameworks.json"
TOPOLOGY_FILE = BASE_DIR / "topology.json"


def _read_local_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_records(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    records = list(catalog.get("frameworks", []))
    records.extend(catalog.get("unverified_candidates", []))
    return sorted(records, key=lambda record: record["id"])


def _observations(record: dict[str, Any]) -> list[str]:
    values = record.get("observed_primitives", [])
    if not values:
        values = record.get("observed_repository_signals", [])
    return sorted(str(value) for value in values)


def generate_plan() -> dict[str, Any]:
    """Build a stable plan using only the two adjacent catalog files."""
    catalog = _read_local_json(CATALOG_FILE)
    topology = _read_local_json(TOPOLOGY_FILE)
    records = _candidate_records(catalog)
    by_id = {record["id"]: record for record in records}

    capability_plans = []
    for record in records:
        capability_plans.append(
            {
                "plan_id": f"capability:{record['id']}",
                "candidate_id": record["id"],
                "canonical_repository": record["canonical_repository"],
                "source_revision": record["head_short_sha"],
                "license": record["license"],
                "verdict": record["verdict"],
                "deployment_status": "NOT_DEPLOYED",
                "plan_kind": "DESCRIPTIVE_COMPATIBILITY",
                "observations": _observations(record),
                "unknown_capability_fields": "ACCEPT_AND_REPORT",
                "operations": [
                    "READ_LOCAL_CATALOG",
                    "NORMALIZE_DESCRIPTORS",
                    "EMIT_PLAN"
                ]
            }
        )

    benchmark_tier = next(
        tier for tier in topology["tiers"] if tier["id"] == "benchmark_candidates"
    )
    benchmark_plans = []
    for candidate_id in sorted(benchmark_tier["candidate_ids"]):
        record = by_id[candidate_id]
        benchmark_plans.append(
            {
                "plan_id": f"benchmark:{candidate_id}",
                "candidate_id": candidate_id,
                "canonical_repository": record["canonical_repository"],
                "source_revision": record["head_short_sha"],
                "deployment_status": "NOT_DEPLOYED",
                "plan_kind": "LOCAL_CONTRACT_CHECK_PLAN",
                "checks": [
                    "CATALOG_JSON_PARSE",
                    "CAPABILITY_DESCRIPTOR_ROUND_TRIP",
                    "PLAN_OUTPUT_DETERMINISM"
                ],
                "external_candidate_execution": false_value()
            }
        )

    corrections = sorted(
        catalog["misattribution_corrections"], key=lambda correction: correction["id"]
    )
    return {
        "catalog_id": catalog["catalog_id"],
        "verified_at": catalog["verified_at"],
        "deployment_status": "NOT_DEPLOYED",
        "mode": "READ_ONLY_PLAN_EMISSION",
        "notice": "Plans describe local catalog checks only and do not install, execute, or deploy candidate code.",
        "open_door": catalog["open_door"],
        "probe_non_actions": topology["probe_non_actions"],
        "capability_plans": capability_plans,
        "benchmark_plans": benchmark_plans,
        "misattribution_corrections": corrections
    }


def false_value() -> bool:
    """Return a named false value so emitted intent is explicit and stable."""
    return False


def main() -> int:
    output = json.dumps(generate_plan(), indent=2, sort_keys=True)
    sys.stdout.write(output)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
