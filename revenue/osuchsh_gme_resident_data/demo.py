"""Synthetic end-to-end demo. Emits one deterministic receipt as canonical JSON."""

from __future__ import annotations

from .core import ResidentStore, canonical_bytes, compile_migration
from .qualification import current_qualification


def synthetic_rows():
    return [
        {
            "source": "legacy_roster.csv",
            "row": 2,
            "record": {
                "resident_id": "R001",
                "first_name": "Avery",
                "last_name": "Quinn",
                "email": "avery@example.test",
                "program": "Family Medicine",
                "pgy_level": 2,
                "start_date": "2025-07-01",
                "expected_end_date": "2028-06-30",
                "training_status": "ACTIVE",
                "license_status": "CURRENT",
                "coordinator_notes": "synthetic fixture only",
            },
        },
        {
            "source": "license_export.csv",
            "row": 9,
            "record": {
                "resident_id": "R001",
                "license_status": "CURRENT",
            },
        },
        {
            "source": "legacy_roster.csv",
            "row": 3,
            "record": {
                "resident_id": "R002",
                "first_name": "Morgan",
                "last_name": "Lee",
                "email": "morgan@example.test",
                "program": "Internal Medicine",
                "pgy_level": 1,
                "start_date": "2026-07-01",
                "expected_end_date": "2029-06-30",
                "training_status": "ACTIVE",
                "license_status": "PENDING",
                "coordinator_notes": "synthetic fixture only",
            },
        },
    ]


def build_demo_receipt() -> dict:
    rows = synthetic_rows()
    plan = compile_migration(rows)
    store = ResidentStore(rows)
    initial = store.apply_migration(plan)
    store.update("R002", expected_version=1, patch={"license_status": "CURRENT"}, actor_role="coordinator")
    return {
        "schema": "osuchsh-gme-demo-v1",
        "migration_plan_digest": plan.plan_digest,
        "initial_receipt": initial,
        "final_receipt": store.receipt(),
        "analytics": store.analytics_export(role="auditor"),
        "qualification": current_qualification(),
    }


def main() -> int:
    print(canonical_bytes(build_demo_receipt()).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())