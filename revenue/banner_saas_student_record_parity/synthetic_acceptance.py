from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from .engine import canonical_sha256, compile_parity
except ImportError:
    from engine import canonical_sha256, compile_parity


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(i: int, last_sync: str) -> dict[str, Any]:
    return {
        "student_id": f"student-{i:04d}",
        "term": "2026FA",
        "program": f"PROGRAM-{i % 12:02d}",
        "enrollment_status": "ACTIVE" if i % 7 else "PART_TIME",
        "holds": [] if i % 11 else ["SYNTHETIC-HOLD"],
        "advisor": f"advisor-{i % 37:02d}",
        "last_sync_utc": last_sync,
    }


def make_acceptance(as_of: str = "2026-09-13T14:00:00Z") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    now = datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    captured = _fmt(now - timedelta(minutes=5))
    fresh = _fmt(now - timedelta(minutes=10))
    stale = _fmt(now - timedelta(hours=4))
    source_rows = [_record(i, fresh) for i in range(2000)]
    target_rows: list[dict[str, Any]] = []

    # 0..1849 => 1850 PARITY_OK
    target_rows.extend(dict(source_rows[i]) for i in range(1850))
    # 1850..1889 => 40 MISSING_TARGET (omitted)
    # 1890..1924 => 35 FIELD_MISMATCH
    for i in range(1890, 1925):
        row = dict(source_rows[i])
        row["program"] = f"MISMATCH-{i:04d}"
        target_rows.append(row)
    # 1925..1949 => 25 DUPLICATE_ID (two target rows per source key)
    for i in range(1925, 1950):
        row = dict(source_rows[i])
        target_rows.extend([dict(row), dict(row)])
    # 1950..1999 => 50 STALE_SYNC
    for i in range(1950, 2000):
        row = dict(source_rows[i])
        row["last_sync_utc"] = stale
        target_rows.append(row)

    source_rows_sha = canonical_sha256(sorted(source_rows, key=lambda r: (r["student_id"], r["term"], canonical_sha256(r))))
    target_rows_sha = canonical_sha256(sorted(target_rows, key=lambda r: (r["student_id"], r["term"], canonical_sha256(r))))
    source = {
        "snapshot_id": "synthetic-banner-source-20260913",
        "system_role": "SOURCE_BANNER",
        "schema_revision": "student-parity-v1",
        "captured_at_utc": captured,
        "complete_export": True,
        "rows_sha256": source_rows_sha,
        "rows": source_rows,
    }
    target = {
        "snapshot_id": "synthetic-saas-target-20260913",
        "system_role": "TARGET_SAAS",
        "schema_revision": "student-parity-v1",
        "captured_at_utc": captured,
        "complete_export": True,
        "rows_sha256": target_rows_sha,
        "rows": target_rows,
    }
    policy = {"max_sync_age_minutes": 120}
    return source, target, policy


def run_acceptance(as_of: str = "2026-09-13T14:00:00Z") -> dict[str, Any]:
    source, target, policy = make_acceptance(as_of)
    return compile_parity(source, target, policy, as_of=as_of)


if __name__ == "__main__":
    report = run_acceptance()
    print(report["summary"])
    print(report["receipt_sha256"])
