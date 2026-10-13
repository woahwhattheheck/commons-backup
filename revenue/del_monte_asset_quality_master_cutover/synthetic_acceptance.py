from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from .engine import canonical_sha256, compile_cutover
except ImportError:
    from engine import canonical_sha256, compile_cutover


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(i: int, updated: str) -> dict[str, Any]:
    return {
        "item_id": f"item-{i % 200:03d}",
        "batch_id": f"batch-{i:05d}",
        "site_id": f"site-{i % 7:02d}",
        "process_revision": f"proc-r{1 + (i % 5)}",
        "quality_master_revision": f"qm-r{1 + (i % 9)}",
        "inspection_evidence_sha256": canonical_sha256({"synthetic_inspection": i}),
        "disposition": "SYNTHETIC-ACCEPTED",
        "last_updated_utc": updated,
    }


def _rows_sha(rows: list[dict[str, Any]]) -> str:
    ordered = sorted(rows, key=lambda r: (r["item_id"], r["batch_id"], r["site_id"], canonical_sha256(r)))
    return canonical_sha256(ordered)


def make_acceptance(as_of: str = "2026-09-13T14:30:00Z") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    now = datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    captured = _fmt(now - timedelta(minutes=5))
    fresh = _fmt(now - timedelta(minutes=15))
    stale = _fmt(now - timedelta(hours=5))
    source_rows = [_row(i, fresh) for i in range(2000)]
    target_rows: list[dict[str, Any]] = []

    # 0..1799 => 1800 READY
    target_rows.extend(dict(source_rows[i]) for i in range(1800))
    # 1800..1849 => 50 MISSING_TARGET
    # 1850..1909 => 60 CONFLICT
    for i in range(1850, 1910):
        row = dict(source_rows[i])
        row["quality_master_revision"] = f"qm-conflict-{i:04d}"
        target_rows.append(row)
    # 1910..1949 => 40 DUPLICATE_KEY
    for i in range(1910, 1950):
        row = dict(source_rows[i])
        target_rows.extend([dict(row), dict(row)])
    # 1950..1999 => 50 STALE_TARGET
    for i in range(1950, 2000):
        source_rows[i] = dict(source_rows[i])
        source_rows[i]["last_updated_utc"] = stale
        row = dict(source_rows[i])
        target_rows.append(row)

    source = {
        "snapshot_id": "synthetic-current-20260913",
        "system_role": "SOURCE_CURRENT",
        "schema_revision": "quality-master-cutover-v1",
        "release_generation": "synthetic-cutover-g17",
        "captured_at_utc": captured,
        "complete_export": True,
        "rows_sha256": _rows_sha(source_rows),
        "rows": source_rows,
    }
    target = {
        "snapshot_id": "synthetic-target-20260913",
        "system_role": "TARGET_CUTOVER",
        "schema_revision": "quality-master-cutover-v1",
        "release_generation": "synthetic-cutover-g17",
        "captured_at_utc": captured,
        "complete_export": True,
        "rows_sha256": _rows_sha(target_rows),
        "rows": target_rows,
    }
    return source, target, {"max_target_age_minutes": 180}


def run_acceptance(as_of: str = "2026-09-13T14:30:00Z") -> dict[str, Any]:
    source, target, policy = make_acceptance(as_of)
    return compile_cutover(source, target, policy, as_of=as_of)


if __name__ == "__main__":
    report = run_acceptance()
    print(report["summary"])
    print(report["receipt_sha256"])
