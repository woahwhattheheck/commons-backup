"""Strict schemas and normalization helpers for the SaaS migration parity pilot."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from errors import ParityError

ENGINE_VERSION = "1.0.0"
INPUT_SCHEMA = "saas-migration-parity-pilot/v1"
REPORT_SCHEMA = "saas-migration-parity-report/v1"
RECEIPT_SCHEMA = "saas-migration-parity-receipt/v1"
MAX_INPUT_BYTES = 4_000_000
MAX_RECORDS = 500
MAX_FIELDS_PER_RECORD = 64
MAX_KEY_MAPS = 4
MAX_FIELD_MAPS = 32
MAX_STRING = 2048
MAX_ID = 96
MAX_FIELD_NAME = 64
MAX_AGE_SECONDS = 31_536_000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
FIELD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
TYPES = {"string", "integer", "boolean"}
CLASSIFICATIONS = (
    "PARITY",
    "MISSING_TARGET",
    "UNEXPECTED_TARGET",
    "FIELD_MISMATCH",
    "STALE_EVIDENCE",
    "DUPLICATE_KEY",
    "INVALID_EVIDENCE",
)


def _reject_constant(value: str) -> None:
    raise ParityError(f"non-finite JSON number rejected: {value}")


def _reject_float(value: str) -> None:
    raise ParityError(f"floating-point JSON numbers rejected: {value}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ParityError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ParityError("input must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except ParityError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError, ValueError) as exc:
        raise ParityError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
        return text.encode("utf-8", errors="strict")
    except (UnicodeEncodeError, RecursionError, TypeError, ValueError) as exc:
        raise ParityError(f"value is not canonical JSON: {exc}") from exc


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exact_keys(obj: dict[str, Any], required: set[str], where: str) -> None:
    if type(obj) is not dict:
        raise ParityError(f"{where} must be object")
    got = set(obj)
    if got != required:
        missing = sorted(required - got)
        extra = sorted(got - required)
        raise ParityError(f"{where} keys mismatch; missing={missing} extra={extra}")


def _safe_string(value: Any, where: str, *, max_len: int) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise ParityError(f"{where} must be non-empty string <= {max_len} chars")
    if any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise ParityError(f"{where} contains control or non-scalar Unicode characters")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ParityError(f"{where} is not UTF-8 encodable") from exc
    return value


def _string(value: Any, where: str, *, max_len: int = MAX_STRING) -> str:
    return _safe_string(value, where, max_len=max_len)


def _identifier(value: Any, where: str) -> str:
    value = _string(value, where, max_len=MAX_ID)
    if not ID_RE.fullmatch(value):
        raise ParityError(f"{where} must match {ID_RE.pattern}")
    return value


def _field_name(value: Any, where: str) -> str:
    value = _string(value, where, max_len=MAX_FIELD_NAME)
    if not FIELD_RE.fullmatch(value):
        raise ParityError(f"{where} must match {FIELD_RE.pattern}")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ParityError(f"{where} must be boolean")
    return value


def _int(value: Any, where: str, *, low: int, high: int) -> int:
    if type(value) is not int or not (low <= value <= high):
        raise ParityError(f"{where} must be integer in [{low}, {high}]")
    return value


def _timestamp(value: Any, where: str) -> tuple[str, dt.datetime]:
    value = _string(value, where, max_len=20)
    if not UTC_RE.fullmatch(value):
        raise ParityError(f"{where} must be canonical UTC seconds YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise ParityError(f"{where} invalid timestamp") from exc
    return value, parsed


def _cell_type_ok(value: Any, declared: str) -> bool:
    if declared == "string":
        if type(value) is not str or not value or len(value) > MAX_STRING:
            return False
        if any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value):
            return False
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            return False
        return True
    if declared == "integer":
        return type(value) is int and -(2**63) <= value <= 2**63 - 1
    if declared == "boolean":
        return type(value) is bool
    return False


def _normalize_mapping(rows: Any, where: str, *, max_rows: int) -> list[dict[str, str]]:
    if type(rows) is not list or not (1 <= len(rows) <= max_rows):
        raise ParityError(f"{where} must be list with 1..{max_rows} entries")
    normalized: list[dict[str, str]] = []
    src_seen: set[str] = set()
    dst_seen: set[str] = set()
    for idx, row in enumerate(rows):
        _exact_keys(row, {"source", "target", "type"}, f"{where}[{idx}]")
        src = _field_name(row["source"], f"{where}[{idx}].source")
        dst = _field_name(row["target"], f"{where}[{idx}].target")
        typ = _string(row["type"], f"{where}[{idx}].type", max_len=16)
        if typ not in TYPES:
            raise ParityError(f"{where}[{idx}].type unsupported: {typ}")
        if src in src_seen or dst in dst_seen:
            raise ParityError(f"{where} contains duplicate source or target field")
        src_seen.add(src)
        dst_seen.add(dst)
        normalized.append({"source": src, "target": dst, "type": typ})
    return sorted(normalized, key=lambda row: (row["source"], row["target"], row["type"]))


def _normalize_record(record: Any, where: str) -> dict[str, Any]:
    _exact_keys(record, {"fields"}, where)
    fields = record["fields"]
    if type(fields) is not dict or not (1 <= len(fields) <= MAX_FIELDS_PER_RECORD):
        raise ParityError(f"{where}.fields must be object with 1..{MAX_FIELDS_PER_RECORD} fields")
    out: dict[str, Any] = {}
    for key, value in fields.items():
        name = _field_name(key, f"{where}.fields key")
        if type(value) is float:
            raise ParityError(f"{where}.fields.{name} floating-point values rejected")
        if type(value) not in (str, int, bool) or not _cell_type_ok(value, {str:"string", int:"integer", bool:"boolean"}[type(value)]):
            raise ParityError(f"{where}.fields.{name} unsupported value type/value")
        out[name] = value
    return {"fields": out}


def _normalize_snapshot(value: Any, where: str) -> dict[str, Any]:
    _exact_keys(value, {"snapshot_id", "schema_revision", "captured_at_utc", "complete", "records"}, where)
    snapshot_id = _identifier(value["snapshot_id"], f"{where}.snapshot_id")
    schema_revision = _identifier(value["schema_revision"], f"{where}.schema_revision")
    captured_s, captured = _timestamp(value["captured_at_utc"], f"{where}.captured_at_utc")
    complete = _bool(value["complete"], f"{where}.complete")
    records = value["records"]
    if type(records) is not list or len(records) > MAX_RECORDS:
        raise ParityError(f"{where}.records must be list <= {MAX_RECORDS}")
    normalized_records = [_normalize_record(rec, f"{where}.records[{idx}]") for idx, rec in enumerate(records)]
    normalized_records.sort(key=lambda rec: canonical_bytes(rec))
    return {
        "snapshot_id": snapshot_id,
        "schema_revision": schema_revision,
        "captured_at_utc": captured_s,
        "_captured": captured,
        "complete": complete,
        "records": normalized_records,
    }


def _normalize_manifest(obj: Any) -> dict[str, Any]:
    _exact_keys(obj, {"schema", "cutover_at_utc", "max_snapshot_age_seconds", "key_map", "field_map", "source_snapshot", "target_snapshot"}, "manifest")
    if obj["schema"] != INPUT_SCHEMA:
        raise ParityError(f"manifest.schema must be {INPUT_SCHEMA}")
    cutover_s, cutover = _timestamp(obj["cutover_at_utc"], "manifest.cutover_at_utc")
    max_age = _int(obj["max_snapshot_age_seconds"], "manifest.max_snapshot_age_seconds", low=0, high=MAX_AGE_SECONDS)
    key_map = _normalize_mapping(obj["key_map"], "manifest.key_map", max_rows=MAX_KEY_MAPS)
    if any(row["type"] == "boolean" for row in key_map):
        raise ParityError("boolean key fields are not supported")
    field_map = _normalize_mapping(obj["field_map"], "manifest.field_map", max_rows=MAX_FIELD_MAPS)
    source = _normalize_snapshot(obj["source_snapshot"], "manifest.source_snapshot")
    target = _normalize_snapshot(obj["target_snapshot"], "manifest.target_snapshot")
    if source["snapshot_id"] == target["snapshot_id"]:
        raise ParityError("source and target snapshot_id must differ")
    return {
        "schema": INPUT_SCHEMA,
        "cutover_at_utc": cutover_s,
        "_cutover": cutover,
        "max_snapshot_age_seconds": max_age,
        "key_map": key_map,
        "field_map": field_map,
        "source_snapshot": source,
        "target_snapshot": target,
    }


def _strip_runtime(norm: dict[str, Any]) -> dict[str, Any]:
    out = dict(norm)
    out.pop("_cutover", None)
    for name in ("source_snapshot", "target_snapshot"):
        snap = dict(out[name])
        snap.pop("_captured", None)
        out[name] = snap
    return out


def _record_key(record: dict[str, Any], mapping: list[dict[str, str]], side: str) -> tuple[bool, list[Any]]:
    fields = record["fields"]
    key_values: list[Any] = []
    for row in mapping:
        name = row[side]
        declared = row["type"]
        if name not in fields or not _cell_type_ok(fields[name], declared):
            return False, []
        key_values.append(fields[name])
    return True, key_values


def _key_commitment(key_values: list[Any], key_map: list[dict[str, str]]) -> str:
    semantic = [
        {"type": row["type"], "value": value}
        for row, value in zip(key_map, key_values, strict=True)
    ]
    return sha256(canonical_bytes(semantic))


def _index_records(records: list[dict[str, Any]], key_map: list[dict[str, str]], side: str) -> tuple[dict[str, list[dict[str, Any]]], int]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    invalid = 0
    for record in records:
        ok, key_values = _record_key(record, key_map, side)
        if not ok:
            invalid += 1
            key = "invalid:" + sha256(canonical_bytes(record))
        else:
            key = _key_commitment(key_values, key_map)
        index[key].append(record)
    return dict(index), invalid


def _snapshot_public(snapshot: dict[str, Any]) -> dict[str, Any]:
    semantic_records = snapshot["records"]
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "schema_revision": snapshot["schema_revision"],
        "captured_at_utc": snapshot["captured_at_utc"],
        "complete": snapshot["complete"],
        "record_count": len(semantic_records),
        "records_sha256": sha256(canonical_bytes(semantic_records)),
    }


def _mismatch_fields(source: dict[str, Any], target: dict[str, Any], mapping: list[dict[str, str]]) -> tuple[bool, list[dict[str, str]]]:
    out: list[dict[str, str]] = []
    valid = True
    sf = source["fields"]
    tf = target["fields"]
    for row in mapping:
        sname, tname, typ = row["source"], row["target"], row["type"]
        if sname not in sf or tname not in tf or not _cell_type_ok(sf.get(sname), typ) or not _cell_type_ok(tf.get(tname), typ):
            valid = False
            continue
        if sf[sname] != tf[tname] or type(sf[sname]) is not type(tf[tname]):
            out.append({
                "source_field": sname,
                "target_field": tname,
                "source_value_sha256": sha256(canonical_bytes(sf[sname])),
                "target_value_sha256": sha256(canonical_bytes(tf[tname])),
            })
    return valid, out


def _age_state(snapshot: dict[str, Any], cutover: dt.datetime, max_age: int) -> tuple[bool, int]:
    captured = snapshot["_captured"]
    age = int((cutover - captured).total_seconds())
    return 0 <= age <= max_age, age
