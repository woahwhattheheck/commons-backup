from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from .engine import canonical_sha256
    from .historical import compile_transfer
except ImportError:
    from engine import canonical_sha256
    from historical import compile_transfer


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _evidence(kind: str, i: int) -> str:
    return canonical_sha256({"synthetic": True, "kind": kind, "packet": i})


def _row(i: int, updated: str) -> dict[str, Any]:
    source_site = "chicago" if i % 2 == 0 else "rankweil"
    receiving_site = "rankweil" if source_site == "chicago" else "chicago"
    return {
        "project_id": f"project-{i % 12:02d}",
        "molecule_id": f"molecule-{i % 18:02d}",
        "batch_id": f"batch-{i:04d}",
        "site_id": source_site,
        "receiving_site_id": receiving_site,
        "process_version": f"process-v{1 + i % 4}",
        "method_version": f"method-v{1 + i % 5}",
        "container_configuration": f"synthetic-container-{i % 3}",
        "equipment_id": f"equipment-{receiving_site}-{i % 9:02d}",
        "equipment_calibration_sha256": _evidence("calibration", i),
        "operator_qualification_sha256": _evidence("operator", i),
        "qc_inspection_sha256": _evidence("qc", i),
        "microbiology_evidence_sha256": _evidence("microbiology", i),
        "storage_condition": "synthetic-controlled-2-8C",
        "transfer_evidence_sha256": _evidence("transfer", i),
        "release_evidence_sha256": _evidence("release", i),
        "last_updated_utc": updated,
    }


def _rows_sha(rows: list[dict[str, Any]]) -> str:
    ordered = sorted(
        rows,
        key=lambda r: (
            r["project_id"],
            r["molecule_id"],
            r["batch_id"],
            r["site_id"],
            canonical_sha256(r),
        ),
    )
    return canonical_sha256(ordered)


def make_acceptance(
    as_of: str = "2026-09-13T15:00:00Z",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    now = datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    captured = _fmt(now - timedelta(minutes=5))
    fresh = _fmt(now - timedelta(minutes=15))
    source_rows = [_row(i, fresh) for i in range(144)]
    receiving_rows = [dict(row) for row in source_rows]

    # 0..119 are exactly TRANSFER_READY.
    # 120..143 are 24 HOLD packets: six defect families, four each.
    for i in range(120, 124):
        receiving_rows[i]["method_version"] = f"method-mismatch-{i}"
    for i in range(124, 128):
        receiving_rows[i]["release_evidence_sha256"] = None
    for i in range(128, 132):
        receiving_rows[i]["container_configuration"] = f"synthetic-wrong-container-{i}"
    for i in range(132, 136):
        receiving_rows[i]["equipment_calibration_sha256"] = None
    for i in range(136, 140):
        receiving_rows[i]["operator_qualification_sha256"] = None
    for i in range(140, 144):
        receiving_rows[i]["microbiology_evidence_sha256"] = None

    source = {
        "snapshot_id": "synthetic-vetter-source-20260913",
        "system_role": "SOURCE_SITE",
        "schema_revision": "clinical-fill-tech-transfer-v1",
        "transfer_generation": "synthetic-transfer-g1",
        "captured_at_utc": captured,
        "complete_export": True,
        "rows_sha256": _rows_sha(source_rows),
        "rows": source_rows,
    }
    receiving = {
        "snapshot_id": "synthetic-vetter-receiving-20260913",
        "system_role": "RECEIVING_SITE",
        "schema_revision": "clinical-fill-tech-transfer-v1",
        "transfer_generation": "synthetic-transfer-g1",
        "captured_at_utc": captured,
        "complete_export": True,
        "rows_sha256": _rows_sha(receiving_rows),
        "rows": receiving_rows,
    }
    return source, receiving, {"max_evidence_age_minutes": 180}


def run_acceptance(
    as_of: str = "2026-09-13T15:00:00Z",
) -> dict[str, Any]:
    """Return an explicitly historical, non-current acceptance envelope."""
    source, receiving, policy = make_acceptance(as_of)
    return compile_transfer(source, receiving, policy, as_of=as_of)


if __name__ == "__main__":
    envelope = run_acceptance()
    print(envelope["authority_mode"])
    print(envelope["decision"]["summary"])
    print(envelope["historical_receipt_sha256"])
