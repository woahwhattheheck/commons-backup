"""Deterministic migration and cutover acceptance evidence for bounded ERP workshares.

This module is deliberately buyer-neutral. It does not connect to any production system,
does not ingest secrets, and does not claim compliance with a buyer's controlling RFP.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ETL_PHASES = ("profile", "cleanse", "map", "transform", "validate", "migrate")
SCHEMA_VERSION = "columbia-erp-acceptance/v2"


class AcceptanceError(ValueError):
    """Raised when evidence is malformed or cannot support an acceptance receipt."""


def _validate_utf8_text(value: str, path: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AcceptanceError(f"{path}: string is not valid UTF-8") from exc
    return value


def _assert_json_safe(value: Any, path: str = "$") -> None:
    if isinstance(value, str):
        _validate_utf8_text(value, path)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise AcceptanceError(f"{path}: non-finite float fails closed")
    if value is None or isinstance(value, (int, bool, float)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AcceptanceError(f"{path}: object keys must be strings")
            _validate_utf8_text(key, f"{path}: object key")
            _assert_json_safe(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for i, item in enumerate(value):
            _assert_json_safe(item, f"{path}[{i}]")
        return
    raise AcceptanceError(f"{path}: unsupported value type {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return canonical UTF-8-safe JSON or fail closed on unsafe values."""
    _assert_json_safe(value)
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        encoded.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AcceptanceError("value cannot be encoded as canonical UTF-8 JSON") from exc
    return encoded


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_key_field(key_field: str) -> str:
    if not isinstance(key_field, str) or not key_field.strip():
        raise AcceptanceError("key_field must be a non-empty string")
    return _validate_utf8_text(key_field, "key_field")


def _normalize_compare_fields(compare_fields: Sequence[str]) -> list[str]:
    if isinstance(compare_fields, (str, bytes, bytearray)) or not isinstance(
        compare_fields, Sequence
    ):
        raise AcceptanceError("compare_fields must be a sequence of field names")
    fields = list(compare_fields)
    if any(not isinstance(field, str) or not field for field in fields):
        raise AcceptanceError("compare_fields contains an invalid field name")
    for i, field in enumerate(fields):
        _validate_utf8_text(field, f"compare_fields[{i}]")
    return sorted(set(fields))


def _normalize_expected_interfaces(expected_interfaces: Sequence[str]) -> list[str]:
    if isinstance(expected_interfaces, (str, bytes, bytearray)) or not isinstance(
        expected_interfaces, Sequence
    ):
        raise AcceptanceError("expected_interfaces must be a sequence of names")
    names: list[str] = []
    seen: set[str] = set()
    for i, raw_name in enumerate(expected_interfaces):
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise AcceptanceError(
                f"expected_interfaces[{i}] must be a non-empty string"
            )
        name = _validate_utf8_text(raw_name.strip(), f"expected_interfaces[{i}]")
        if name in seen:
            raise AcceptanceError(f"duplicate expected interface {name!r}")
        seen.add(name)
        names.append(name)
    return sorted(names)


def _index_records(
    records: Sequence[Mapping[str, Any]], key_field: str, label: str
) -> dict[str, dict[str, Any]]:
    if isinstance(records, (str, bytes, bytearray)) or not isinstance(records, Sequence):
        raise AcceptanceError(f"{label}: records must be a sequence")
    index: dict[str, dict[str, Any]] = {}
    for i, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise AcceptanceError(f"{label}[{i}]: record must be an object")
        copied = dict(record)
        _assert_json_safe(copied, f"{label}[{i}]")
        key = copied.get(key_field)
        if not isinstance(key, str) or not key.strip():
            raise AcceptanceError(f"{label}[{i}].{key_field}: non-empty string required")
        if key in index:
            if canonical_json(index[key]) == canonical_json(copied):
                raise AcceptanceError(f"{label}: duplicate key {key!r}")
            raise AcceptanceError(f"{label}: conflicting duplicate key {key!r}")
        index[key] = copied
    return index


def _record_root(index: Mapping[str, Mapping[str, Any]]) -> str:
    """Bind logical record content while remaining invariant to input record order."""
    ordered_records = [index[key] for key in sorted(index)]
    return _sha256_json(ordered_records)


def reconcile_records(
    source_records: Sequence[Mapping[str, Any]],
    target_records: Sequence[Mapping[str, Any]],
    *,
    key_field: str = "key",
    compare_fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compare two bounded record sets and emit stable exception evidence.

    ``compare_fields=None`` is an explicit contract meaning: for every shared key,
    compare the union of all non-key fields on the source and target records.
    """
    key_field = _validate_key_field(key_field)
    normalized_compare_fields = (
        None if compare_fields is None else _normalize_compare_fields(compare_fields)
    )
    source = _index_records(source_records, key_field, "source")
    target = _index_records(target_records, key_field, "target")
    source_keys = set(source)
    target_keys = set(target)

    missing = sorted(source_keys - target_keys)
    unexpected = sorted(target_keys - source_keys)
    mismatches: list[dict[str, Any]] = []

    for key in sorted(source_keys & target_keys):
        if normalized_compare_fields is None:
            fields = sorted((set(source[key]) | set(target[key])) - {key_field})
        else:
            fields = normalized_compare_fields
        for field in fields:
            left = source[key].get(field)
            right = target[key].get(field)
            if canonical_json(left) != canonical_json(right):
                mismatches.append(
                    {"key": key, "field": field, "source": left, "target": right}
                )

    payload = {
        "comparison_contract": {
            "key_field": key_field,
            "compare_fields": normalized_compare_fields,
        },
        "source_count": len(source),
        "target_count": len(target),
        "source_records_sha256": _record_root(source),
        "target_records_sha256": _record_root(target),
        "missing_target_keys": missing,
        "unexpected_target_keys": unexpected,
        "field_mismatches": mismatches,
    }
    payload["status"] = (
        "PASS" if not missing and not unexpected and not mismatches else "HOLD"
    )
    return payload


def normalize_phase_evidence(evidence: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(evidence, Mapping):
        raise AcceptanceError("phase evidence must be an object")
    if any(not isinstance(key, str) for key in evidence):
        raise AcceptanceError("phase evidence keys must be strings")
    for key in evidence:
        _validate_utf8_text(key, "phase evidence key")
    unknown = sorted(set(evidence) - set(ETL_PHASES))
    if unknown:
        raise AcceptanceError(f"unknown ETL phases: {', '.join(unknown)}")
    out: dict[str, str] = {}
    missing: list[str] = []
    for phase in ETL_PHASES:
        value = evidence.get(phase)
        if not isinstance(value, str) or not value.strip():
            missing.append(phase)
        else:
            out[phase] = _validate_utf8_text(
                value.strip(), f"phase evidence {phase!r}"
            )
    if missing:
        raise AcceptanceError(f"missing ETL evidence: {', '.join(missing)}")
    return out


def normalize_interfaces(
    interfaces: Sequence[Mapping[str, Any]],
    *,
    expected_interfaces: Sequence[str],
) -> list[dict[str, str]]:
    if isinstance(interfaces, (str, bytes, bytearray)) or not isinstance(
        interfaces, Sequence
    ):
        raise AcceptanceError("interfaces must be a sequence")
    expected = _normalize_expected_interfaces(expected_interfaces)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, item in enumerate(interfaces):
        if not isinstance(item, Mapping):
            raise AcceptanceError(f"interfaces[{i}] must be an object")
        name = item.get("name")
        status = item.get("status")
        evidence_id = item.get("evidence_id")
        if not isinstance(name, str) or not name.strip():
            raise AcceptanceError(f"interfaces[{i}].name must be non-empty")
        name = _validate_utf8_text(name.strip(), f"interfaces[{i}].name")
        if name in seen:
            raise AcceptanceError(f"duplicate interface {name!r}")
        seen.add(name)
        if status != "PASS":
            raise AcceptanceError(f"interface {name!r} is not PASS")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise AcceptanceError(f"interface {name!r} lacks evidence_id")
        evidence_id = _validate_utf8_text(
            evidence_id.strip(), f"interface {name!r} evidence_id"
        )
        out.append({"name": name, "status": "PASS", "evidence_id": evidence_id})

    actual = sorted(seen)
    if actual != expected:
        missing = sorted(set(expected) - seen)
        unexpected = sorted(seen - set(expected))
        raise AcceptanceError(
            "interface roster mismatch: "
            f"missing={canonical_json(missing)} unexpected={canonical_json(unexpected)}"
        )
    return sorted(out, key=lambda x: x["name"])


def build_receipt(
    source_records: Sequence[Mapping[str, Any]],
    target_records: Sequence[Mapping[str, Any]],
    phase_evidence: Mapping[str, Any],
    interfaces: Sequence[Mapping[str, Any]],
    *,
    expected_interfaces: Sequence[str],
    key_field: str = "key",
    compare_fields: Sequence[str] | None = None,
    scope_id: str = "bounded-migration-slice",
) -> dict[str, Any]:
    """Issue a receipt only when migration, phase, and interface evidence all pass."""
    if not isinstance(scope_id, str) or not scope_id.strip():
        raise AcceptanceError("scope_id must be a non-empty string")
    scope_id = _validate_utf8_text(scope_id.strip(), "scope_id")
    expected = _normalize_expected_interfaces(expected_interfaces)
    reconciliation = reconcile_records(
        source_records,
        target_records,
        key_field=key_field,
        compare_fields=compare_fields,
    )
    if reconciliation["status"] != "PASS":
        raise AcceptanceError("reconciliation contains blocking exceptions")
    phases = normalize_phase_evidence(phase_evidence)
    normalized_interfaces = normalize_interfaces(
        interfaces, expected_interfaces=expected
    )
    comparison = reconciliation["comparison_contract"]
    payload = {
        "schema": SCHEMA_VERSION,
        "contract": {
            "scope_id": scope_id,
            "key_field": comparison["key_field"],
            "compare_fields": comparison["compare_fields"],
            "expected_interfaces": expected,
        },
        "reconciliation": reconciliation,
        "etl_evidence": phases,
        "interfaces": normalized_interfaces,
    }
    return {"payload": payload, "sha256": _sha256_json(payload)}


def verify_receipt(receipt: Mapping[str, Any]) -> bool:
    """Verify receipt integrity; this is an integrity check, not a digital signature."""
    if not isinstance(receipt, Mapping):
        return False
    payload = receipt.get("payload")
    digest = receipt.get("sha256")
    if not isinstance(payload, Mapping) or not isinstance(digest, str):
        return False
    try:
        expected = _sha256_json(payload)
    except AcceptanceError:
        return False
    return digest == expected


def _load_json(path: str) -> Any:
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except UnicodeDecodeError as exc:
        raise AcceptanceError(f"{path}: input is not valid UTF-8") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a bounded ERP migration acceptance receipt"
    )
    parser.add_argument("--source", required=True, help="JSON array of source records")
    parser.add_argument(
        "--target", required=True, help="JSON array of migrated target records"
    )
    parser.add_argument(
        "--phases", required=True, help="JSON object with six ETL evidence ids"
    )
    parser.add_argument(
        "--interfaces", required=True, help="JSON array of interface PASS evidence"
    )
    parser.add_argument(
        "--expected-interfaces",
        required=True,
        help="JSON array defining the exact in-scope interface roster",
    )
    parser.add_argument("--scope-id", default="bounded-migration-slice")
    parser.add_argument("--key-field", default="key")
    args = parser.parse_args(argv)

    try:
        receipt = build_receipt(
            _load_json(args.source),
            _load_json(args.target),
            _load_json(args.phases),
            _load_json(args.interfaces),
            expected_interfaces=_load_json(args.expected_interfaces),
            scope_id=args.scope_id,
            key_field=args.key_field,
        )
    except (AcceptanceError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            receipt, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
