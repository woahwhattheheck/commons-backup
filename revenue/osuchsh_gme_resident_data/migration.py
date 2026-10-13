"""Deterministic multi-source resident migration compiler."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .codec import ALLOWED_FIELDS, DataError, _require_text, canonical_bytes, digest, validate_record

@dataclass(frozen=True)
class MigrationPlan:
    records: tuple[dict[str, Any], ...]
    conflicts: tuple[dict[str, Any], ...]
    source_rows: int
    plan_digest: str

    @property
    def status(self) -> str:
        # NO_CONFLICTS is a compile result, not a current-readiness mint.
        return "NO_CONFLICTS" if not self.conflicts else "CONFLICTS_PRESENT"


def compile_migration(rows: Iterable[Mapping[str, Any]]) -> MigrationPlan:
    """Compile source-tagged rows into a deterministic, conflict-explicit plan.

    Each input row must have `source`, `row`, and `record`. Missing values may be
    supplied by another source. Divergent non-empty values for the same resident/field
    become explicit conflicts; no source wins by ordering.
    """

    normalized: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, Mapping) or set(item) != {"source", "row", "record"}:
            raise DataError("migration row keys must be exactly source,row,record")
        source = _require_text("source", item["source"], max_len=200)
        row_no = item["row"]
        if type(row_no) is not int or row_no < 1:
            raise DataError("migration row must be a positive integer")
        record = validate_record(item["record"], require_all=False)
        if "resident_id" not in record:
            raise DataError("migration record requires resident_id")
        normalized.append({"source": source, "row": row_no, "record": record})

    normalized.sort(key=lambda x: (x["record"]["resident_id"], x["source"], x["row"]))
    by_resident: dict[str, list[dict[str, Any]]] = {}
    for row in normalized:
        by_resident.setdefault(row["record"]["resident_id"], []).append(row)

    output_records: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for resident_id in sorted(by_resident):
        rows_for_resident = by_resident[resident_id]
        merged: dict[str, Any] = {"resident_id": resident_id}
        conflicted_fields: set[str] = set()
        for field in sorted(ALLOWED_FIELDS - {"resident_id"}):
            values: dict[str, list[dict[str, Any]]] = {}
            for row in rows_for_resident:
                if field not in row["record"]:
                    continue
                value = row["record"][field]
                key = canonical_bytes(value).decode("utf-8")
                values.setdefault(key, []).append(
                    {"source": row["source"], "row": row["row"], "value": value}
                )
            if not values:
                continue
            if len(values) > 1:
                conflicted_fields.add(field)
                evidence = []
                for key in sorted(values):
                    evidence.extend(sorted(values[key], key=lambda x: (x["source"], x["row"])))
                conflicts.append(
                    {
                        "resident_id": resident_id,
                        "field": field,
                        "evidence": evidence,
                    }
                )
            else:
                merged[field] = next(iter(values.values()))[0]["value"]
        if not conflicted_fields:
            output_records.append(validate_record(merged, require_all=True))

    plan_body = {
        "records": output_records,
        "conflicts": conflicts,
        "source_rows": len(normalized),
    }
    return MigrationPlan(
        records=tuple(copy.deepcopy(output_records)),
        conflicts=tuple(copy.deepcopy(conflicts)),
        source_rows=len(normalized),
        plan_digest=digest(plan_body),
    )
