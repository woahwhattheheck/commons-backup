"""Deterministic evidence for bounded federal-asset migration acceptance workshares.

This module checks continuity against a caller-frozen normalized contract. It does not
certify FAR/DFARS/NIST/508 or any other legal, security, accounting, audit, or buyer
compliance requirement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "gtri-inventory-acceptance/v1"


class AcceptanceError(ValueError):
    """Raised when evidence cannot safely support an acceptance decision."""


def _validate_utf8(value: str, path: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AcceptanceError(f"{path}: string is not valid UTF-8") from exc
    return value


def _assert_json_safe(value: Any, path: str = "$") -> None:
    if isinstance(value, str):
        _validate_utf8(value, path)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise AcceptanceError(f"{path}: non-finite float cannot be encoded as JSON")
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AcceptanceError(f"{path}: object keys must be strings")
            _validate_utf8(key, f"{path}: object key")
            _assert_json_safe(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for i, item in enumerate(value):
            _assert_json_safe(item, f"{path}[{i}]")
        return
    raise AcceptanceError(f"{path}: unsupported value type {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Canonical UTF-8 JSON used for logical evidence commitments."""
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


def _normalize_names(values: Sequence[str], label: str) -> list[str]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise AcceptanceError(f"{label} must be a sequence")
    out: list[str] = []
    seen: set[str] = set()
    for i, raw in enumerate(values):
        if not isinstance(raw, str) or not raw.strip():
            raise AcceptanceError(f"{label}[{i}] must be a non-empty string")
        name = _validate_utf8(raw.strip(), f"{label}[{i}]")
        if name in seen:
            raise AcceptanceError(f"{label}: duplicate value {name!r}")
        seen.add(name)
        out.append(name)
    return sorted(out)


def _normalize_expected_history(
    expected_history_events: Mapping[str, Sequence[str]],
    expected_asset_ids: Sequence[str],
) -> dict[str, list[str]]:
    if not isinstance(expected_history_events, Mapping):
        raise AcceptanceError("expected_history_events must be an object")
    if any(not isinstance(key, str) for key in expected_history_events):
        raise AcceptanceError("expected_history_events keys must be strings")
    expected_assets = set(expected_asset_ids)
    actual_assets = set(expected_history_events)
    if actual_assets != expected_assets:
        missing = sorted(expected_assets - actual_assets)
        unexpected = sorted(actual_assets - expected_assets)
        raise AcceptanceError(
            "history roster asset mismatch: "
            f"missing={canonical_json(missing)} unexpected={canonical_json(unexpected)}"
        )
    return {
        asset_id: _normalize_names(
            expected_history_events[asset_id],
            f"expected_history_events[{asset_id!r}]",
        )
        for asset_id in sorted(expected_assets)
    }


def _index_records(
    records: Sequence[Mapping[str, Any]],
    key_field: str,
    label: str,
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
        key = _validate_utf8(key.strip(), f"{label}[{i}].{key_field}")
        copied[key_field] = key
        if key in index:
            if canonical_json(index[key]) == canonical_json(copied):
                raise AcceptanceError(f"{label}: duplicate key {key!r}")
            raise AcceptanceError(f"{label}: conflicting duplicate key {key!r}")
        index[key] = copied
    return index


def _root(index: Mapping[str, Mapping[str, Any]]) -> str:
    return _sha256_json([index[key] for key in sorted(index)])


def _history_key(
    record: Mapping[str, Any], asset_field: str, event_field: str, label: str
) -> tuple[str, str]:
    asset_id = record.get(asset_field)
    event_id = record.get(event_field)
    if not isinstance(asset_id, str) or not asset_id.strip():
        raise AcceptanceError(f"{label}.{asset_field}: non-empty string required")
    if not isinstance(event_id, str) or not event_id.strip():
        raise AcceptanceError(f"{label}.{event_field}: non-empty string required")
    return (
        _validate_utf8(asset_id.strip(), f"{label}.{asset_field}"),
        _validate_utf8(event_id.strip(), f"{label}.{event_field}"),
    )


def _index_history(
    records: Sequence[Mapping[str, Any]],
    *,
    asset_field: str,
    event_field: str,
    label: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    if isinstance(records, (str, bytes, bytearray)) or not isinstance(records, Sequence):
        raise AcceptanceError(f"{label}: records must be a sequence")
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for i, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise AcceptanceError(f"{label}[{i}]: record must be an object")
        copied = dict(record)
        _assert_json_safe(copied, f"{label}[{i}]")
        key = _history_key(copied, asset_field, event_field, f"{label}[{i}]")
        copied[asset_field], copied[event_field] = key
        if key in index:
            if canonical_json(index[key]) == canonical_json(copied):
                raise AcceptanceError(f"{label}: duplicate event {key!r}")
            raise AcceptanceError(f"{label}: conflicting duplicate event {key!r}")
        index[key] = copied
    return index


def _history_root(index: Mapping[tuple[str, str], Mapping[str, Any]]) -> str:
    ordered = [index[key] for key in sorted(index)]
    return _sha256_json(ordered)


def _require_fields(
    record: Mapping[str, Any], fields: Sequence[str], label: str
) -> list[str]:
    missing: list[str] = []
    for field in fields:
        if field not in record:
            missing.append(field)
            continue
        value = record[field]
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


def _normalize_interfaces(
    interfaces: Sequence[Mapping[str, Any]], expected_interfaces: Sequence[str]
) -> list[dict[str, str]]:
    if isinstance(interfaces, (str, bytes, bytearray)) or not isinstance(
        interfaces, Sequence
    ):
        raise AcceptanceError("interfaces must be a sequence")
    expected = _normalize_names(expected_interfaces, "expected_interfaces")
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
        name = _validate_utf8(name.strip(), f"interfaces[{i}].name")
        if name in seen:
            raise AcceptanceError(f"duplicate interface {name!r}")
        seen.add(name)
        if status != "PASS":
            raise AcceptanceError(f"interface {name!r} is not PASS")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise AcceptanceError(f"interface {name!r} lacks evidence_id")
        evidence_id = _validate_utf8(
            evidence_id.strip(), f"interface {name!r} evidence_id"
        )
        out.append({"name": name, "status": "PASS", "evidence_id": evidence_id})
    if sorted(seen) != expected:
        missing = sorted(set(expected) - seen)
        unexpected = sorted(seen - set(expected))
        raise AcceptanceError(
            "interface roster mismatch: "
            f"missing={canonical_json(missing)} unexpected={canonical_json(unexpected)}"
        )
    return sorted(out, key=lambda item: item["name"])


def reconcile(
    source_assets: Sequence[Mapping[str, Any]],
    target_assets: Sequence[Mapping[str, Any]],
    source_history: Sequence[Mapping[str, Any]],
    target_history: Sequence[Mapping[str, Any]],
    *,
    expected_asset_ids: Sequence[str],
    expected_history_events: Mapping[str, Sequence[str]],
    compared_asset_fields: Sequence[str],
    required_asset_fields: Sequence[str],
    history_compare_fields: Sequence[str],
    preserve_asset_id: bool,
) -> dict[str, Any]:
    """Reconcile a normalized migration slice without asserting buyer compliance."""
    expected_assets = _normalize_names(expected_asset_ids, "expected_asset_ids")
    expected_history = _normalize_expected_history(
        expected_history_events, expected_assets
    )
    compared_fields = _normalize_names(
        compared_asset_fields, "compared_asset_fields"
    )
    required_fields = _normalize_names(required_asset_fields, "required_asset_fields")
    history_fields = _normalize_names(history_compare_fields, "history_compare_fields")

    source = _index_records(source_assets, "asset_id", "source_assets")
    target = _index_records(target_assets, "source_asset_id", "target_assets")

    source_roster = sorted(source)
    target_roster = sorted(target)
    roster_errors: list[dict[str, Any]] = []
    for label, actual in (("source", source_roster), ("target", target_roster)):
        missing = sorted(set(expected_assets) - set(actual))
        unexpected = sorted(set(actual) - set(expected_assets))
        if missing or unexpected:
            roster_errors.append(
                {"side": label, "missing": missing, "unexpected": unexpected}
            )

    target_ids: dict[str, str] = {}
    target_id_errors: list[dict[str, Any]] = []
    field_errors: list[dict[str, Any]] = []
    field_mismatches: list[dict[str, Any]] = []

    for source_id in sorted(set(source) & set(target)):
        source_record = source[source_id]
        target_record = target[source_id]
        target_asset_id = target_record.get("asset_id")
        if not isinstance(target_asset_id, str) or not target_asset_id.strip():
            target_id_errors.append(
                {"source_asset_id": source_id, "error": "missing_target_asset_id"}
            )
        else:
            target_asset_id = _validate_utf8(
                target_asset_id.strip(), f"target asset id for {source_id!r}"
            )
            prior = target_ids.get(target_asset_id)
            if prior is not None and prior != source_id:
                target_id_errors.append(
                    {
                        "source_asset_id": source_id,
                        "target_asset_id": target_asset_id,
                        "error": "target_asset_id_reused",
                        "first_source_asset_id": prior,
                    }
                )
            else:
                target_ids[target_asset_id] = source_id
            if preserve_asset_id and target_asset_id != source_id:
                target_id_errors.append(
                    {
                        "source_asset_id": source_id,
                        "target_asset_id": target_asset_id,
                        "error": "asset_id_not_preserved",
                    }
                )

        for side, record in (("source", source_record), ("target", target_record)):
            missing = _require_fields(
                record, required_fields, f"{side}:{source_id}"
            )
            if missing:
                field_errors.append(
                    {
                        "side": side,
                        "source_asset_id": source_id,
                        "missing_required_fields": missing,
                    }
                )
        for field in compared_fields:
            left = source_record.get(field)
            right = target_record.get(field)
            if canonical_json(left) != canonical_json(right):
                field_mismatches.append(
                    {
                        "source_asset_id": source_id,
                        "field": field,
                        "source": left,
                        "target": right,
                    }
                )

    src_hist = _index_history(
        source_history,
        asset_field="asset_id",
        event_field="event_id",
        label="source_history",
    )
    tgt_hist = _index_history(
        target_history,
        asset_field="source_asset_id",
        event_field="source_event_id",
        label="target_history",
    )

    expected_event_keys = {
        (asset_id, event_id)
        for asset_id, event_ids in expected_history.items()
        for event_id in event_ids
    }
    src_event_keys = set(src_hist)
    tgt_event_keys = set(tgt_hist)
    history_roster_errors: list[dict[str, Any]] = []
    for label, actual in (("source", src_event_keys), ("target", tgt_event_keys)):
        missing = sorted(expected_event_keys - actual)
        unexpected = sorted(actual - expected_event_keys)
        if missing or unexpected:
            history_roster_errors.append(
                {
                    "side": label,
                    "missing": [[a, e] for a, e in missing],
                    "unexpected": [[a, e] for a, e in unexpected],
                }
            )

    history_mismatches: list[dict[str, Any]] = []
    for key in sorted(src_event_keys & tgt_event_keys):
        source_event = src_hist[key]
        target_event = tgt_hist[key]
        for field in history_fields:
            left = source_event.get(field)
            right = target_event.get(field)
            if canonical_json(left) != canonical_json(right):
                history_mismatches.append(
                    {
                        "source_asset_id": key[0],
                        "source_event_id": key[1],
                        "field": field,
                        "source": left,
                        "target": right,
                    }
                )

    result = {
        "contract": {
            "expected_asset_ids": expected_assets,
            "expected_history_events": expected_history,
            "compared_asset_fields": compared_fields,
            "required_asset_fields": required_fields,
            "history_compare_fields": history_fields,
            "preserve_asset_id": preserve_asset_id,
        },
        "roots": {
            "source_assets_sha256": _root(source),
            "target_assets_sha256": _root(target),
            "source_history_sha256": _history_root(src_hist),
            "target_history_sha256": _history_root(tgt_hist),
        },
        "counts": {
            "source_assets": len(source),
            "target_assets": len(target),
            "source_history_events": len(src_hist),
            "target_history_events": len(tgt_hist),
        },
        "exceptions": {
            "asset_roster": roster_errors,
            "target_identity": target_id_errors,
            "required_fields": field_errors,
            "asset_field_mismatches": field_mismatches,
            "history_roster": history_roster_errors,
            "history_field_mismatches": history_mismatches,
        },
    }
    result["status"] = (
        "PASS"
        if all(not rows for rows in result["exceptions"].values())
        else "HOLD"
    )
    return result


def build_receipt(
    source_assets: Sequence[Mapping[str, Any]],
    target_assets: Sequence[Mapping[str, Any]],
    source_history: Sequence[Mapping[str, Any]],
    target_history: Sequence[Mapping[str, Any]],
    interfaces: Sequence[Mapping[str, Any]],
    *,
    scope_id: str,
    expected_asset_ids: Sequence[str],
    expected_history_events: Mapping[str, Sequence[str]],
    compared_asset_fields: Sequence[str],
    required_asset_fields: Sequence[str],
    history_compare_fields: Sequence[str],
    expected_interfaces: Sequence[str],
    preserve_asset_id: bool = False,
) -> dict[str, Any]:
    if not isinstance(scope_id, str) or not scope_id.strip():
        raise AcceptanceError("scope_id must be a non-empty string")
    scope_id = _validate_utf8(scope_id.strip(), "scope_id")
    if not isinstance(preserve_asset_id, bool):
        raise AcceptanceError("preserve_asset_id must be a boolean")
    reconciliation = reconcile(
        source_assets,
        target_assets,
        source_history,
        target_history,
        expected_asset_ids=expected_asset_ids,
        expected_history_events=expected_history_events,
        compared_asset_fields=compared_asset_fields,
        required_asset_fields=required_asset_fields,
        history_compare_fields=history_compare_fields,
        preserve_asset_id=preserve_asset_id,
    )
    if reconciliation["status"] != "PASS":
        raise AcceptanceError("migration reconciliation contains blocking exceptions")
    normalized_interfaces = _normalize_interfaces(interfaces, expected_interfaces)
    payload = {
        "schema": SCHEMA_VERSION,
        "scope_id": scope_id,
        "reconciliation": reconciliation,
        "expected_interfaces": _normalize_names(
            expected_interfaces, "expected_interfaces"
        ),
        "interfaces": normalized_interfaces,
    }
    return {"payload": payload, "sha256": _sha256_json(payload)}


def verify_receipt_integrity(
    receipt: Mapping[str, Any],
    authority_root: object = True,
) -> bool:
    """Check receipt self-integrity only; this is not evidence authenticity."""
    if not authority_root:
        return False
    if not isinstance(receipt, Mapping):
        return False
    payload = receipt.get("payload")
    digest = receipt.get("sha256")
    if not isinstance(payload, Mapping) or not isinstance(digest, str):
        return False
    if payload.get("schema") != SCHEMA_VERSION:
        return False
    observed_at = datetime.now(timezone.utc)
    try:
        expected = hashlib.sha256(
            json.dumps(
                dict(payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        return False
    return (
        bool(authority_root)
        and digest == expected
        and observed_at.tzinfo is timezone.utc
    )


def _load_json(path: str) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a bounded federal-asset migration acceptance receipt"
    )
    parser.add_argument("--source-assets", required=True)
    parser.add_argument("--target-assets", required=True)
    parser.add_argument("--source-history", required=True)
    parser.add_argument("--target-history", required=True)
    parser.add_argument("--interfaces", required=True)
    parser.add_argument("--contract", required=True)
    args = parser.parse_args(argv)

    try:
        contract = _load_json(args.contract)
        if not isinstance(contract, Mapping):
            raise AcceptanceError("contract must be a JSON object")
        receipt = build_receipt(
            _load_json(args.source_assets),
            _load_json(args.target_assets),
            _load_json(args.source_history),
            _load_json(args.target_history),
            _load_json(args.interfaces),
            scope_id=contract.get("scope_id"),
            expected_asset_ids=contract.get("expected_asset_ids"),
            expected_history_events=contract.get("expected_history_events"),
            compared_asset_fields=contract.get("compared_asset_fields"),
            required_asset_fields=contract.get("required_asset_fields"),
            history_compare_fields=contract.get("history_compare_fields"),
            expected_interfaces=contract.get("expected_interfaces"),
            preserve_asset_id=contract.get("preserve_asset_id", False),
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
