"""Record and snapshot schema normalization for EDSS acceptance evidence."""
from typing import Any
from ._core import *

def _validate_fields(raw: Any, *, where: str, policy: dict[str, Any]) -> list[dict[str, str]]:
    if type(raw) is not list or not raw or len(raw) > policy["max_fields_per_row"]:
        raise EdssAcceptanceError(f"{where} must be a nonempty bounded list")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, value in enumerate(raw):
        obj = _exact_object(value, {"field_id", "value_sha256"}, where=f"{where}[{index}]")
        field_id = _safe_id(obj["field_id"], where=f"{where}[{index}].field_id", maximum=policy["max_id_chars"])
        if field_id in seen:
            raise EdssAcceptanceError(f"duplicate field_id in {where}: {field_id}")
        seen.add(field_id)
        out.append({"field_id": field_id, "value_sha256": _sha(obj["value_sha256"], where=f"{where}[{index}].value_sha256")})
    return sorted(out, key=lambda item: item["field_id"])


def _validate_rows(raw: Any, *, where: str, policy: dict[str, Any]) -> list[dict[str, Any]]:
    if type(raw) is not list or len(raw) > policy["max_rows"]:
        raise EdssAcceptanceError(f"{where} must be a bounded list")
    out: list[dict[str, Any]] = []
    for index, value in enumerate(raw):
        obj = _exact_object(value, {"record_id", "fields"}, where=f"{where}[{index}]")
        out.append({
            "record_id": _safe_id(obj["record_id"], where=f"{where}[{index}].record_id", maximum=policy["max_id_chars"]),
            "fields": _validate_fields(obj["fields"], where=f"{where}[{index}].fields", policy=policy),
        })
    return sorted(out, key=lambda item: (item["record_id"], canonical_json_bytes(item["fields"])))


def rows_digest(rows: list[dict[str, Any]]) -> str:
    # Adapter-facing helper: make semantically identical field order hash identically.
    normalized = [
        {"record_id": row["record_id"], "fields": sorted(row["fields"], key=lambda item: item["field_id"])}
        for row in rows
    ]
    ordered = sorted(normalized, key=lambda item: (item["record_id"], canonical_json_bytes(item["fields"])))
    return sha256_hex(canonical_json_bytes(ordered))


def _validate_snapshot(raw: Any, *, role: str, where: str, policy: dict[str, Any]) -> dict[str, Any]:
    obj = _exact_object(raw, {"snapshot_id", "system_role", "schema_revision", "captured_at", "complete_export", "record_count", "rows_sha256", "rows"}, where=where)
    if obj["system_role"] != role:
        raise EdssAcceptanceError(f"{where}.system_role must be {role}")
    rows = _validate_rows(obj["rows"], where=f"{where}.rows", policy=policy)
    count = _integer(obj["record_count"], where=f"{where}.record_count", minimum=0, maximum=policy["max_rows"])
    if count != len(rows):
        raise EdssAcceptanceError(f"{where}.record_count does not match rows")
    digest = _sha(obj["rows_sha256"], where=f"{where}.rows_sha256")
    if digest != rows_digest(rows):
        raise EdssAcceptanceError(f"{where}.rows_sha256 does not match rows")
    return {
        "snapshot_id": _safe_id(obj["snapshot_id"], where=f"{where}.snapshot_id", maximum=policy["max_id_chars"]),
        "system_role": role,
        "schema_revision": _safe_id(obj["schema_revision"], where=f"{where}.schema_revision", maximum=policy["max_id_chars"]),
        "captured_at": _utc_text(_parse_utc(obj["captured_at"], where=f"{where}.captured_at")),
        "complete_export": _boolean(obj["complete_export"], where=f"{where}.complete_export"),
        "record_count": count,
        "rows_sha256": digest,
        "rows": rows,
    }



__all__ = ["rows_digest", "_validate_snapshot"]
