"""Rebuild the fictional sample catalog; no institutional data is consumed."""
from pathlib import Path
from fixture_lab import BOUNDARY, SCHEMA, canonical


def item(key, group, generator, **changes):
    record = {
        "id": key, "group": group, "service": f"Fictional {group} service",
        "version": "1.0.0", "generator": generator,
        "purpose": "Exercise effective-time boundaries with explicitly fictional records.",
        "owner_role": f"Proposed {group} fixture maintainer",
        "last_refreshed": "2026-09-10", "review_interval_days": 14,
        "source_interface_version": "fictional-api-v1", "target_interface_version": "fictional-api-v1",
        "required_boundaries": list(BOUNDARY), "maintenance_hours": {"low": 2, "high": 5},
        "retired_on": None, "cleanup_after_days": 7,
        "cleanup_evidence": None, "refresh_evidence": f"SYNTHETIC-NOTE-{key}-001 (fictional pointer)",
        "parameters": {"start": "2026-10-01T00:00:00-05:00", "end": "2026-10-02T00:00:00-05:00"},
    }
    record.update(changes)
    return record


def example():
    return {"schema": SCHEMA, "catalog_id": "UIOWA-047-FICTIONAL", "synthetic": True, "fixtures": [
        item("ESS-TERM", "ESS", "term_window"),
        item("ESS-LEGACY", "ESS", "term_window", last_refreshed="2026-08-01",
             owner_role=None, source_interface_version="fictional-api-v0",
             required_boundaries=["at_start", "inside", "at_end"], refresh_evidence=None),
        item("RIS-FUNDING", "RIS", "funding_window", target_interface_version=None,
             parameters={"start": "2026-12-31T00:00:00Z", "end": "2027-01-01T00:00:00Z"}),
        item("RIS-RETIRED", "RIS", "funding_window", last_refreshed="2026-08-01",
             retired_on="2026-09-01", cleanup_evidence=None),
        item("IAM-CONTRACTOR", "IAM", "role_transition", maintenance_hours={"low": 3, "high": 8}),
        item("IAM-UNKNOWN", "IAM", "role_transition", last_refreshed=None,
             owner_role=None, refresh_evidence=None, maintenance_hours=None),
    ]}


if __name__ == "__main__":
    Path(__file__).with_name("example_catalog.json").write_bytes(canonical(example()))
