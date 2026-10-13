#!/usr/bin/env python3
"""Read-only E-Jet batch provenance dossier compiler.

The compiler validates eight evidence classes, emits immutable evidence dossiers
only for complete records, and writes a reason-coded exception ledger for
incomplete records. It never makes a regulatory, release, disposition, blending,
shipment, PLC, DCS, tank, or valve decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

REQUIRED_HANDOFF_STAGES = ("production_release", "carrier_pickup", "buyer_receipt")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _timestamp(value: Any) -> datetime | None:
    if not _nonempty(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _nested(batch: dict[str, Any], key: str) -> dict[str, Any]:
    value = batch.get(key)
    return value if isinstance(value, dict) else {}


def _fault(code: str, input_class: str, field: str, detail: str) -> dict[str, str]:
    return {"reason_code": code, "input_class": input_class, "field": field, "detail": detail}


def validate_batch_identity(batch: dict[str, Any]) -> dict[str, str] | None:
    return None if _nonempty(batch.get("batch_id")) else _fault("BATCH_ID_INVALID", "batch_identity", "$.batch_id", "batch_id must be a non-empty string")


def validate_co2_source(batch: dict[str, Any]) -> dict[str, str] | None:
    source = _nested(batch, "co2_source")
    if not _nonempty(source.get("certificate_id")):
        return _fault("CO2_CERT_MISSING", "co2_source_certificate", "$.co2_source.certificate_id", "CO2 source certificate_id is required")
    if not _nonempty(source.get("source_id")):
        return _fault("CO2_SOURCE_MISSING", "co2_source_certificate", "$.co2_source.source_id", "CO2 source_id is required")
    if _timestamp(source.get("issued_at")) is None:
        return _fault("CO2_CERT_TIME_INVALID", "co2_source_certificate", "$.co2_source.issued_at", "issued_at must be offset-aware RFC3339")
    return None


def validate_renewable_power(batch: dict[str, Any]) -> dict[str, str] | None:
    power = _nested(batch, "renewable_power")
    if not _nonempty(power.get("certificate_id")):
        return _fault("POWER_CERT_MISSING", "renewable_power_certificate", "$.renewable_power.certificate_id", "renewable-power certificate_id is required")
    mwh = _decimal(power.get("mwh"))
    if mwh is None or mwh < 0:
        return _fault("POWER_MWH_INVALID", "renewable_power_certificate", "$.renewable_power.mwh", "mwh must be non-negative")
    start, end = _timestamp(power.get("window_start")), _timestamp(power.get("window_end"))
    if start is None or end is None or end < start:
        return _fault("POWER_WINDOW_INVALID", "renewable_power_certificate", "$.renewable_power.window_start|window_end", "power certificate window must be valid and ordered")
    return None


def validate_process_lots(batch: dict[str, Any]) -> dict[str, str] | None:
    lots = _nested(batch, "process_lots")
    if not _nonempty(lots.get("catalyst_lot")):
        return _fault("CATALYST_LOT_MISSING", "catalyst_electrolyzer_lot", "$.process_lots.catalyst_lot", "catalyst_lot is required")
    if not _nonempty(lots.get("electrolyzer_lot")):
        return _fault("ELECTROLYZER_LOT_MISSING", "catalyst_electrolyzer_lot", "$.process_lots.electrolyzer_lot", "electrolyzer_lot is required")
    return None


def validate_recipe(batch: dict[str, Any]) -> dict[str, str] | None:
    return None if _nonempty(batch.get("recipe_revision")) else _fault("RECIPE_REVISION_MISSING", "recipe_revision", "$.recipe_revision", "recipe_revision is required")


def validate_in_process_lab(batch: dict[str, Any]) -> dict[str, str] | None:
    lab = _nested(batch, "in_process_lab")
    if not _nonempty(lab.get("sample_id")):
        return _fault("IN_PROCESS_SAMPLE_MISSING", "in_process_lab", "$.in_process_lab.sample_id", "in-process sample_id is required")
    if lab.get("result") != "PASS":
        return _fault("IN_PROCESS_LAB_NOT_PASS", "in_process_lab", "$.in_process_lab.result", "in-process lab result must equal PASS")
    if _timestamp(lab.get("measured_at")) is None:
        return _fault("IN_PROCESS_TIME_INVALID", "in_process_lab", "$.in_process_lab.measured_at", "measured_at must be offset-aware RFC3339")
    return None


def validate_final_coa(batch: dict[str, Any]) -> dict[str, str] | None:
    coa = _nested(batch, "final_coa")
    if not _nonempty(coa.get("coa_id")):
        return _fault("COA_ID_MISSING", "final_fuel_spec_coa", "$.final_coa.coa_id", "coa_id is required")
    if not _nonempty(coa.get("spec_id")):
        return _fault("COA_SPEC_MISSING", "final_fuel_spec_coa", "$.final_coa.spec_id", "fuel spec_id is required")
    if coa.get("result") != "PASS":
        return _fault("FINAL_COA_NOT_PASS", "final_fuel_spec_coa", "$.final_coa.result", "final COA result must equal PASS")
    if _timestamp(coa.get("issued_at")) is None:
        return _fault("COA_TIME_INVALID", "final_fuel_spec_coa", "$.final_coa.issued_at", "issued_at must be offset-aware RFC3339")
    return None


def validate_custody(batch: dict[str, Any]) -> dict[str, str] | None:
    custody = _nested(batch, "custody")
    if not _nonempty(custody.get("tank_id")):
        return _fault("TANK_ID_MISSING", "tank_shipment_chain_of_custody", "$.custody.tank_id", "tank_id is required")
    if not _nonempty(custody.get("shipment_id")):
        return _fault("SHIPMENT_ID_MISSING", "tank_shipment_chain_of_custody", "$.custody.shipment_id", "shipment_id is required")
    handoffs = custody.get("handoffs") if isinstance(custody.get("handoffs"), list) else []
    by_stage = {h.get("stage"): h for h in handoffs if isinstance(h, dict) and _nonempty(h.get("stage"))}
    ordered: list[tuple[str, datetime]] = []
    for stage in REQUIRED_HANDOFF_STAGES:
        handoff = by_stage.get(stage)
        if not isinstance(handoff, dict):
            return _fault("CUSTODY_STAGE_MISSING", "tank_shipment_chain_of_custody", f"$.custody.handoffs[{stage}]", f"required handoff {stage} is missing")
        if not _nonempty(handoff.get("owner")):
            return _fault("CUSTODY_OWNER_MISSING", "tank_shipment_chain_of_custody", f"$.custody.handoffs[{stage}].owner", f"handoff {stage} needs a named owner")
        ts = _timestamp(handoff.get("timestamp"))
        if ts is None:
            return _fault("CUSTODY_TIME_INVALID", "tank_shipment_chain_of_custody", f"$.custody.handoffs[{stage}].timestamp", f"handoff {stage} needs an offset-aware RFC3339 timestamp")
        ordered.append((stage, ts))
    for (prev_stage, prev_ts), (stage, ts) in zip(ordered, ordered[1:]):
        if ts < prev_ts:
            return _fault("CUSTODY_SEQUENCE_INVALID", "tank_shipment_chain_of_custody", "$.custody.handoffs", f"{stage} timestamp precedes {prev_stage}")
    return None


VALIDATORS: tuple[Callable[[dict[str, Any]], dict[str, str] | None], ...] = (
    validate_batch_identity,
    validate_co2_source,
    validate_renewable_power,
    validate_process_lots,
    validate_recipe,
    validate_in_process_lab,
    validate_final_coa,
    validate_custody,
)

LINEAGE_PATHS = (
    "$.batch_id",
    "$.co2_source.certificate_id",
    "$.co2_source.source_id",
    "$.co2_source.issued_at",
    "$.renewable_power.certificate_id",
    "$.renewable_power.window_start",
    "$.renewable_power.window_end",
    "$.renewable_power.mwh",
    "$.process_lots.catalyst_lot",
    "$.process_lots.electrolyzer_lot",
    "$.recipe_revision",
    "$.in_process_lab.sample_id",
    "$.in_process_lab.result",
    "$.in_process_lab.measured_at",
    "$.final_coa.coa_id",
    "$.final_coa.spec_id",
    "$.final_coa.result",
    "$.final_coa.issued_at",
    "$.custody.tank_id",
    "$.custody.shipment_id",
    "$.custody.handoffs",
)


def resolve_path(batch: dict[str, Any], path: str) -> Any:
    if not path.startswith("$."):
        raise ValueError(f"unsupported lineage path: {path}")
    value: Any = batch
    for part in path[2:].split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(path)
        value = value[part]
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def compile_batch(batch: dict[str, Any], record_index: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    faults = [fault for validator in VALIDATORS if (fault := validator(batch)) is not None]
    batch_ref = batch.get("batch_id") if _nonempty(batch.get("batch_id")) else batch.get("record_id", f"record-{record_index:03d}")
    exceptions = [{"batch_ref": batch_ref, **fault, "automated_release": False, "release_decision": None} for fault in faults]
    if exceptions:
        return None, exceptions
    lineage = {path: {"source": path, "value": resolve_path(batch, path)} for path in LINEAGE_PATHS}
    evidence_hash = hashlib.sha256(_canonical_bytes(lineage)).hexdigest()
    dossier = {
        "schema": "ejet-batch-provenance-dossier/v2",
        "batch_id": batch["batch_id"],
        "evidence_status": "COMPLETE",
        "evidence_sha256": evidence_hash,
        "lineage": lineage,
        "automated_release": False,
        "release_decision": None,
        "boundary": "evidence compilation only; named-human disposition and authorization required",
    }
    return dossier, []


def compile_run(batches: list[dict[str, Any]]) -> dict[str, Any]:
    dossiers: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    for index, batch in enumerate(batches):
        if not isinstance(batch, dict):
            exceptions.append({"batch_ref": f"record-{index:03d}", "reason_code": "RECORD_NOT_OBJECT", "input_class": "record_envelope", "field": "$", "detail": "record must be a JSON object", "automated_release": False, "release_decision": None})
            continue
        dossier, batch_exceptions = compile_batch(batch, index)
        if dossier is not None:
            dossiers.append(dossier)
        exceptions.extend(batch_exceptions)
    class_counts = Counter(item["input_class"] for item in exceptions)
    summary = {
        "input_batches": len(batches),
        "complete_dossiers": len(dossiers),
        "exceptions": len(exceptions),
        "unique_exception_batches": len({item["batch_ref"] for item in exceptions}),
        "exception_counts_by_input_class": dict(sorted(class_counts.items())),
        "automated_release_performed": False,
    }
    return {"summary": summary, "dossiers": dossiers, "exceptions": exceptions}


def write_bundle(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    dossiers_dir = output_dir / "dossiers"
    dossiers_dir.mkdir(exist_ok=True)
    for dossier in result["dossiers"]:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", dossier["batch_id"])[:80]
        (dossiers_dir / f"{safe_id}.json").write_bytes(_canonical_bytes(dossier) + b"\n")
    (output_dir / "exceptions.jsonl").write_text("".join(json.dumps(item, sort_keys=True, ensure_ascii=True) + "\n" for item in result["exceptions"]), encoding="ascii")
    (output_dir / "summary.json").write_bytes(json.dumps(result["summary"], sort_keys=True, indent=2).encode("ascii") + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON array of batch evidence records")
    parser.add_argument("--out", type=Path, default=Path("out"), help="output bundle directory")
    args = parser.parse_args()
    batches = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(batches, list):
        raise SystemExit("input must be a JSON array")
    result = compile_run(batches)
    write_bundle(result, args.out)
    print(json.dumps(result["summary"], sort_keys=True))
    return 0 if not result["exceptions"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
