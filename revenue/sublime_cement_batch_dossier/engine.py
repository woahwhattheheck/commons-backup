#!/usr/bin/env python3
"""Deterministic read-only batch evidence dossier assembler.

This module does not decide ASTM conformance, batch disposition, shipment release,
or any process setting. It only validates a bounded evidence packet and projects
source-reported evidence availability into complete dossiers or explicit HOLD rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

PACKET_VERSION = "sublime-cement-batch-evidence/v1"
RESULT_VERSION = "sublime-cement-batch-dossier-result/v1"
MAX_INPUT_BYTES = 2_000_000
MAX_TEXT = 240

SECTIONS: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("feedstock", "FEEDSTOCK_ASSAY", ("lot_id",), ("mineral_assay_sha256",)),
    ("recipe", "RECIPE_REVISION", ("revision_id",), ("recipe_sha256",)),
    ("reagent", "REAGENT_LOT", ("lot_id",), ("coa_sha256",)),
    ("equipment", "CALIBRATION", ("equipment_id", "calibration_id"), ("calibration_record_sha256",)),
    ("in_process", "IN_PROCESS_CHEMISTRY", ("chemistry_record_id",), ("chemistry_record_sha256",)),
    ("physical_tests", "PHYSICAL_TESTS", ("fineness_record_id", "strength_record_id"), ("fineness_record_sha256", "strength_record_sha256")),
    ("astm_evidence", "ASTM_EVIDENCE", ("evidence_id", "standard"), ("evidence_sha256",)),
    ("delivery", "COA_DELIVERY_MAPPING", ("coa_id", "delivery_lot_id"), ("coa_sha256", "mapping_evidence_sha256")),
)
SECTION_NAMES = tuple(item[0] for item in SECTIONS)
FAULT_CLASSES = tuple(item[1] for item in SECTIONS)

AUTHORITY = {
    "process_control": False,
    "reagent_dosing": False,
    "blend_instruction": False,
    "equipment_command": False,
    "astm_conformance_decision": False,
    "structural_suitability_judgment": False,
    "batch_disposition": False,
    "shipment_approval": False,
    "external_action": False,
    "payment": False,
    "revenue_recognition": False,
}


class EvidenceError(ValueError):
    """Fail-closed packet or result validation error."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EvidenceError(f"non-finite JSON number: {token}")
            ),
        )
    except EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON: {exc.msg}") from exc


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or type(value) in {bool, str, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise EvidenceError(f"{path}: non-finite number")
        return
    if type(value) is list:
        for i, item in enumerate(value):
            _validate_json_value(item, f"{path}[{i}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise EvidenceError(f"{path}: non-string object key")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise EvidenceError(f"{path}: unsupported JSON type {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    _validate_json_value(value, "$")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{path}: expected object")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise EvidenceError(f"{path}: expected array")
    return value


def _expect_str(value: Any, path: str, *, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str:
        raise EvidenceError(f"{path}: expected string")
    if not value or value.strip() != value:
        raise EvidenceError(f"{path}: empty or surrounding whitespace")
    if len(value) > max_len:
        raise EvidenceError(f"{path}: too long")
    if any(ord(ch) < 32 for ch in value):
        raise EvidenceError(f"{path}: control character")
    return value


def _expect_keys(obj: Mapping[str, Any], required: set[str], path: str) -> None:
    keys = set(obj)
    missing = sorted(required - keys)
    unknown = sorted(keys - required)
    if missing:
        raise EvidenceError(f"{path}: missing fields {missing}")
    if unknown:
        raise EvidenceError(f"{path}: unknown fields {unknown}")


def _sha(value: Any, path: str) -> str:
    s = _expect_str(value, path, max_len=64)
    if len(s) != 64 or any(ch not in "0123456789abcdef" for ch in s):
        raise EvidenceError(f"{path}: expected lowercase sha256")
    return s


def _source_status(value: Any, path: str) -> str:
    s = _expect_str(value, path, max_len=18)
    if s not in {"AVAILABLE", "HOLD"}:
        raise EvidenceError(f"{path}: expected AVAILABLE or HOLD")
    return s


def _validate_section(
    raw: Any,
    path: str,
    text_fields: tuple[str, ...],
    hash_fields: tuple[str, ...],
) -> dict[str, Any]:
    obj = _expect_dict(raw, path)
    required = {"source_id", "source_sha256", "source_status", *text_fields, *hash_fields}
    _expect_keys(obj, required, path)
    _expect_str(obj["source_id"], f"{path}.source_id", max_len=120)
    _sha(obj["source_sha256"], f"{path}.source_sha256")
    _source_status(obj["source_status"], f"{path}.source_status")
    for field in text_fields:
        value = _expect_str(obj[field], f"{path}.{field}", max_len=160)
        if field == "standard" and value != "ASTM C1157":
            raise EvidenceError(f"{path}.standard: expected exact ASTM C1157 evidence label")
    for field in hash_fields:
        _sha(obj[field], f"{path}.{field}")
    return dict(obj)


def _validate_batch(raw: Any, index: int) -> dict[str, Any]:
    path = f"$.batches[{index}]"
    obj = _expect_dict(raw, path)
    _expect_keys(obj, {"batch_id", *SECTION_NAMES}, path)
    _expect_str(obj["batch_id"], f"{path}.batch_id", max_len=100)
    out: dict[str, Any] = {"batch_id": obj["batch_id"]}
    for section, _fault, texts, hashes in SECTIONS:
        out[section] = _validate_section(obj[section], f"{path}.{section}", texts, hashes)
    return out


def _validate_packet(packet: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = _expect_dict(packet, "$")
    _expect_keys(root, {"schema_version", "batches"}, "$")
    if root["schema_version"] != PACKET_VERSION:
        raise EvidenceError("$.schema_version: unsupported")
    rows = _expect_list(root["batches"], "$.batches")
    if not rows:
        raise EvidenceError("$.batches: must not be empty")
    if len(rows) > 10_000:
        raise EvidenceError("$.batches: too many rows")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, raw in enumerate(rows):
        row = _validate_batch(raw, i)
        batch_id = row["batch_id"]
        if batch_id in seen:
            raise EvidenceError(f"$.batches: duplicate batch_id {batch_id}")
        seen.add(batch_id)
        validated.append(row)
    return dict(root), validated


def _lineage(batch: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section, _fault, _texts, _hashes in SECTIONS:
        evidence = batch[section]
        rows.append(
            {
                "section": section,
                "source_id": evidence["source_id"],
                "source_sha256": evidence["source_sha256"],
            }
        )
    return rows


def assemble(packet: Any) -> dict[str, Any]:
    """Validate packet and emit deterministic complete dossiers / explicit HOLDs."""
    root, batches = _validate_packet(packet)
    dossiers: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []

    for batch in sorted(batches, key=lambda row: row["batch_id"]):
        batch_id = batch["batch_id"]
        batch_sha = digest(batch)
        holds: list[tuple[str, str]] = []
        for section, fault_class, _texts, _hashes in SECTIONS:
            if batch[section]["source_status"] == "HOLD":
                holds.append((fault_class, section))

        if holds:
            for fault_class, section in holds:
                source = batch[section]
                exceptions.append(
                    {
                        "batch_id": batch_id,
                        "fault_class": fault_class,
                        "state": "HOLD",
                        "source_section": section,
                        "source_id": source["source_id"],
                        "source_sha256": source["source_sha256"],
                        "batch_sha256": batch_sha,
                    }
                )
        else:
            dossier = {
                "batch_id": batch_id,
                "state": "DOSSIER_COMPLETE",
                "batch_sha256": batch_sha,
                "raw_source_lineage": _lineage(batch),
                "evidence": {name: batch[name] for name in SECTION_NAMES},
            }
            dossier["dossier_sha256"] = digest(dossier)
            dossiers.append(dossier)

    exceptions.sort(key=lambda row: (row["batch_id"], row["fault_class"]))
    outcome = {
        "result_version": RESULT_VERSION,
        "source_packet_sha256": digest(root),
        "batch_count": len(batches),
        "dossier_count": len(dossiers),
        "exception_count": len(exceptions),
        "dossiers": dossiers,
        "exceptions": exceptions,
        "authority": dict(AUTHORITY),
    }
    outcome["decisions_sha256"] = digest(
        {
            "dossiers": [
                {"batch_id": row["batch_id"], "dossier_sha256": row["dossier_sha256"]}
                for row in dossiers
            ],
            "exceptions": exceptions,
        }
    )
    outcome["receipt_sha256"] = digest(outcome)
    return outcome


def verify_result(packet: Any, result: Any) -> bool:
    """Verify an output by exact canonical recomputation."""
    if type(result) is not dict:
        return False
    try:
        expected = assemble(packet)
        return canonical_bytes(expected) == canonical_bytes(result)
    except EvidenceError:
        return False


def _read_bounded(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise EvidenceError(f"cannot stat input: {exc}") from exc
    if size > MAX_INPUT_BYTES:
        raise EvidenceError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise EvidenceError(f"cannot read input: {exc}") from exc
    if len(data) > MAX_INPUT_BYTES:
        raise EvidenceError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError("input must be UTF-8") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="strict JSON evidence packet")
    args = parser.parse_args(argv)
    try:
        packet = loads_strict(_read_bounded(args.packet))
        result = assemble(packet)
    except EvidenceError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
