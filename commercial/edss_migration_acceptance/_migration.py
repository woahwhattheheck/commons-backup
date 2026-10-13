"""Source-to-target migration row reconciliation."""
from typing import Any
from ._core import canonical_json_bytes

def _row_signature(row: dict[str, Any]) -> bytes:
    return canonical_json_bytes(row["fields"])


def _group_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["record_id"], []).append(row)
    return grouped


def _record_results(source_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], expected_ids: list[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    source = _group_rows(source_rows)
    target = _group_rows(target_rows)
    ids = sorted(set(source) | set(target) | set(expected_ids))
    results: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for record_id in ids:
        srows = source.get(record_id, [])
        trows = target.get(record_id, [])
        if len(srows) > 1:
            status = "CONFLICT_SOURCE" if len({_row_signature(row) for row in srows}) > 1 else "DUPLICATE_SOURCE"
            diff_fields: list[str] = []
        elif len(trows) > 1:
            status = "CONFLICT_TARGET" if len({_row_signature(row) for row in trows}) > 1 else "DUPLICATE_TARGET"
            diff_fields = []
        elif record_id not in expected_ids:
            status = "UNEXPECTED_RECORD"
            diff_fields = []
        elif not srows:
            status = "EXPECTED_SOURCE_MISSING"
            diff_fields = []
        elif not trows:
            status = "MISSING_TARGET"
            diff_fields = []
        else:
            sfields = {item["field_id"]: item["value_sha256"] for item in srows[0]["fields"]}
            tfields = {item["field_id"]: item["value_sha256"] for item in trows[0]["fields"]}
            diff_fields = sorted(field_id for field_id in set(sfields) | set(tfields) if sfields.get(field_id) != tfields.get(field_id))
            status = "FIELD_MISMATCH" if diff_fields else "PARITY_OK"
        counts[status] = counts.get(status, 0) + 1
        results.append({"record_id": record_id, "status": status, "differing_field_ids": diff_fields})
    return results, dict(sorted(counts.items()))



__all__ = ["_record_results"]
