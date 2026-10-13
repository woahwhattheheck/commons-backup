"""Deterministic synthetic laboratory-interface UAT evidence engine."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

SCHEMA = "lab-interface-uat-core/v1"
SOURCE_SCHEMA = "lab-interface-source-event/v1"
TARGET_SCHEMA = "lab-interface-target-event/v1"
RECEIPT_SCHEMA = "lab-interface-uat-receipt/v1"
AUTHORITY = "INTERFACE_UAT_ONLY_NO_CLINICAL_OR_PRODUCTION_AUTHORITY"

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DEC_RE = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d{1,12})?$")
REQUIRED_SOURCE_FIELDS = {
    "schema", "event_id", "source_system", "logical_id", "revision", "supersedes_event_id",
    "accession_id", "specimen_type", "test_code", "result_value", "unit",
    "reference_low", "reference_high", "status", "site",
}
REQUIRED_TARGET_FIELDS = {
    "schema", "event_id", "target_system", "source_event_id", "logical_id", "revision",
    "contract_id", "contract_version", "mapping_sha256", "accession_id",
    "specimen_type", "test_code", "result_value", "unit", "reference_low",
    "reference_high", "status", "site",
}


class UATError(ValueError):
    """Raised when evidence cannot be interpreted canonically."""


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise UATError("evidence must be canonical JSON") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _exact(value: Any, keys: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise UATError(f"{field} must contain exactly {sorted(keys)}")
    return value


def _text(value: Any, field: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > limit:
        raise UATError(f"{field} must be a bounded non-empty string")
    return value


def _id(value: Any, field: str) -> str:
    value = _text(value, field, 128)
    if not ID_RE.fullmatch(value):
        raise UATError(f"{field} is not a canonical identifier")
    return value


def _hash(value: Any, field: str) -> str:
    value = _text(value, field, 64)
    if not HASH_RE.fullmatch(value):
        raise UATError(f"{field} must be lowercase sha256")
    return value


def _int(value: Any, field: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise UATError(f"{field} must be an integer in [{lo},{hi}]")
    return value


def _decimal(value: Any, field: str) -> str:
    if not isinstance(value, str) or not DEC_RE.fullmatch(value):
        raise UATError(f"{field} must be a canonical decimal string")
    try:
        d = Decimal(value)
    except InvalidOperation as exc:
        raise UATError(f"{field} is not decimal") from exc
    if not d.is_finite():
        raise UATError(f"{field} must be finite")
    normalized = format(d.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized == "-0":
        normalized = "0"
    return normalized


def _mapping(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not 1 <= len(value) <= 256:
        raise UATError(f"{field} must be a bounded non-empty mapping")
    out: dict[str, str] = {}
    for k, v in value.items():
        src = _id(k, f"{field}.source")
        dst = _id(v, f"{field}.{src}")
        if src in out:
            raise UATError(f"duplicate {field} key")
        out[src] = dst
    return dict(sorted(out.items()))


def _normalize_contract(raw: Mapping[str, Any]) -> dict[str, Any]:
    obj = _exact(dict(raw) if isinstance(raw, Mapping) else raw, {
        "schema", "contract_id", "version", "source_system", "target_system",
        "mapping_version", "mapping_sha256", "code_map", "unit_map",
        "allowed_statuses", "allowed_specimen_types",
    }, "contract")
    if obj["schema"] != SCHEMA:
        raise UATError("unsupported contract schema")
    statuses_raw = obj["allowed_statuses"]
    specimens_raw = obj["allowed_specimen_types"]
    if not isinstance(statuses_raw, list) or not 1 <= len(statuses_raw) <= 32:
        raise UATError("allowed_statuses must be a bounded non-empty list")
    if not isinstance(specimens_raw, list) or not 1 <= len(specimens_raw) <= 64:
        raise UATError("allowed_specimen_types must be a bounded non-empty list")
    statuses = sorted({_id(v, "allowed_status") for v in statuses_raw})
    specimens = sorted({_id(v, "allowed_specimen_type") for v in specimens_raw})
    if len(statuses) != len(statuses_raw) or len(specimens) != len(specimens_raw):
        raise UATError("contract lists must not contain duplicates")
    code_map = _mapping(obj["code_map"], "code_map")
    unit_map = _mapping(obj["unit_map"], "unit_map")
    mapping_version = _text(obj["mapping_version"], "mapping_version", 128)
    declared_mapping_sha256 = _hash(obj["mapping_sha256"], "mapping_sha256")
    computed_mapping_sha256 = _sha({
        "mapping_version": mapping_version,
        "code_map": code_map,
        "unit_map": unit_map,
    })
    if declared_mapping_sha256 != computed_mapping_sha256:
        raise UATError("mapping_sha256 does not match mapping content")
    return {
        "schema": SCHEMA,
        "contract_id": _id(obj["contract_id"], "contract_id"),
        "version": _text(obj["version"], "version", 128),
        "source_system": _id(obj["source_system"], "source_system"),
        "target_system": _id(obj["target_system"], "target_system"),
        "mapping_version": mapping_version,
        "mapping_sha256": declared_mapping_sha256,
        "code_map": code_map,
        "unit_map": unit_map,
        "allowed_statuses": statuses,
        "allowed_specimen_types": specimens,
    }


def _normalize_source(raw: Any) -> dict[str, Any]:
    e = _exact(raw, REQUIRED_SOURCE_FIELDS, "source event")
    if e["schema"] != SOURCE_SCHEMA:
        raise UATError("unsupported source event schema")
    revision = _int(e["revision"], "source.revision", 1, 1_000_000)
    supersedes = e["supersedes_event_id"]
    if supersedes is not None:
        supersedes = _id(supersedes, "source.supersedes_event_id")
    if revision == 1 and supersedes is not None:
        raise UATError("revision 1 cannot supersede another event")
    if revision > 1 and supersedes is None:
        raise UATError("revision >1 must cite predecessor")
    low = _decimal(e["reference_low"], "source.reference_low")
    high = _decimal(e["reference_high"], "source.reference_high")
    if Decimal(low) > Decimal(high):
        raise UATError("reference interval is inverted")
    return {
        "schema": SOURCE_SCHEMA,
        "event_id": _id(e["event_id"], "source.event_id"),
        "source_system": _id(e["source_system"], "source.source_system"),
        "logical_id": _id(e["logical_id"], "source.logical_id"),
        "revision": revision,
        "supersedes_event_id": supersedes,
        "accession_id": _id(e["accession_id"], "source.accession_id"),
        "specimen_type": _id(e["specimen_type"], "source.specimen_type"),
        "test_code": _id(e["test_code"], "source.test_code"),
        "result_value": _decimal(e["result_value"], "source.result_value"),
        "unit": _id(e["unit"], "source.unit"),
        "reference_low": low,
        "reference_high": high,
        "status": _id(e["status"], "source.status"),
        "site": _id(e["site"], "source.site"),
    }


def _normalize_target(raw: Any) -> dict[str, Any]:
    e = _exact(raw, REQUIRED_TARGET_FIELDS, "target event")
    if e["schema"] != TARGET_SCHEMA:
        raise UATError("unsupported target event schema")
    low = _decimal(e["reference_low"], "target.reference_low")
    high = _decimal(e["reference_high"], "target.reference_high")
    if Decimal(low) > Decimal(high):
        raise UATError("target reference interval is inverted")
    return {
        "schema": TARGET_SCHEMA,
        "event_id": _id(e["event_id"], "target.event_id"),
        "target_system": _id(e["target_system"], "target.target_system"),
        "source_event_id": _id(e["source_event_id"], "target.source_event_id"),
        "logical_id": _id(e["logical_id"], "target.logical_id"),
        "revision": _int(e["revision"], "target.revision", 1, 1_000_000),
        "contract_id": _id(e["contract_id"], "target.contract_id"),
        "contract_version": _text(e["contract_version"], "target.contract_version", 128),
        "mapping_sha256": _hash(e["mapping_sha256"], "target.mapping_sha256"),
        "accession_id": _id(e["accession_id"], "target.accession_id"),
        "specimen_type": _id(e["specimen_type"], "target.specimen_type"),
        "test_code": _id(e["test_code"], "target.test_code"),
        "result_value": _decimal(e["result_value"], "target.result_value"),
        "unit": _id(e["unit"], "target.unit"),
        "reference_low": low,
        "reference_high": high,
        "status": _id(e["status"], "target.status"),
        "site": _id(e["site"], "target.site"),
    }


def _dedupe(
    raw_events: Iterable[Any],
    normalizer: Any,
    label: str,
    *,
    allow_empty: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    raw = list(raw_events)
    minimum = 0 if allow_empty else 1
    if not minimum <= len(raw) <= 100_000:
        raise UATError(f"{label} events must contain {minimum}..100000 entries")
    variants: dict[str, dict[bytes, dict[str, Any]]] = defaultdict(dict)
    for item in raw:
        e = normalizer(item)
        if len(_canon(e)) > 32_768:
            raise UATError(f"{label} event exceeds byte ceiling")
        variants[e["event_id"]][_canon(e)] = e
    events: list[dict[str, Any]] = []
    conflicts: list[str] = []
    for event_id in sorted(variants):
        group = variants[event_id]
        if len(group) > 1:
            conflicts.append(event_id)
        events.append(group[min(group)])
    return events, conflicts


def _expected_target(source: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    if source["test_code"] not in contract["code_map"]:
        reasons.append("UNMAPPED_TEST_CODE")
    if source["unit"] not in contract["unit_map"]:
        reasons.append("UNMAPPED_UNIT")
    if source["status"] not in contract["allowed_statuses"]:
        reasons.append("STATUS_OUTSIDE_CONTRACT")
    if source["specimen_type"] not in contract["allowed_specimen_types"]:
        reasons.append("SPECIMEN_OUTSIDE_CONTRACT")
    if reasons:
        return None, reasons
    return {
        "schema": TARGET_SCHEMA,
        "target_system": contract["target_system"],
        "source_event_id": source["event_id"],
        "logical_id": source["logical_id"],
        "revision": source["revision"],
        "contract_id": contract["contract_id"],
        "contract_version": contract["version"],
        "mapping_sha256": contract["mapping_sha256"],
        "accession_id": source["accession_id"],
        "specimen_type": source["specimen_type"],
        "test_code": contract["code_map"][source["test_code"]],
        "result_value": source["result_value"],
        "unit": contract["unit_map"][source["unit"]],
        "reference_low": source["reference_low"],
        "reference_high": source["reference_high"],
        "status": source["status"],
        "site": source["site"],
    }, []


def evaluate(
    contract_raw: Mapping[str, Any],
    source_raw: Iterable[Any],
    target_raw: Iterable[Any],
) -> dict[str, Any]:
    """Evaluate one complete synthetic source→target interface evidence bundle."""
    contract = _normalize_contract(contract_raw)
    sources, source_conflicts = _dedupe(source_raw, _normalize_source, "source")
    targets, target_conflicts = _dedupe(
        target_raw, _normalize_target, "target", allow_empty=True
    )
    reasons: set[str] = set()
    details: dict[str, list[str]] = defaultdict(list)

    if source_conflicts:
        reasons.add("SOURCE_EVENT_IDENTITY_CONFLICT")
        details["source_conflicts"].extend(source_conflicts)
    if target_conflicts:
        reasons.add("TARGET_EVENT_IDENTITY_CONFLICT")
        details["target_conflicts"].extend(target_conflicts)

    by_logical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in sources:
        by_logical[source["logical_id"]].append(source)
    for logical_id, rows in sorted(by_logical.items()):
        rows = sorted(rows, key=lambda x: x["revision"])
        revisions = [r["revision"] for r in rows]
        if revisions != list(range(1, len(rows) + 1)):
            reasons.add("NONCONTIGUOUS_REVISION_LINEAGE")
            details["lineage"].append(logical_id)
            continue
        for idx, row in enumerate(rows):
            if idx == 0:
                continue
            if row["supersedes_event_id"] != rows[idx - 1]["event_id"]:
                reasons.add("BROKEN_CORRECTION_LINEAGE")
                details["lineage"].append(f"{logical_id}:r{row['revision']}")

    source_by_id = {s["event_id"]: s for s in sources}
    target_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in targets:
        target_by_source[target["source_event_id"]].append(target)

    for source in sources:
        if source["source_system"] != contract["source_system"]:
            reasons.add("SOURCE_SYSTEM_MISMATCH")
            details["source_system"].append(source["event_id"])
            continue
        expected, mapping_reasons = _expected_target(source, contract)
        if mapping_reasons:
            reasons.add("SOURCE_QUARANTINED")
            details["quarantine"].append(source["event_id"] + ":" + ",".join(sorted(mapping_reasons)))
            continue
        rows = target_by_source.get(source["event_id"], [])
        if not rows:
            reasons.add("MISSING_TARGET_EVENT")
            details["missing_target"].append(source["event_id"])
            continue
        if len(rows) != 1:
            reasons.add("MULTIPLE_TARGETS_FOR_SOURCE")
            details["multiple_targets"].append(source["event_id"])
            continue
        target = rows[0]
        comparable = {k: target[k] for k in expected}
        if comparable != expected:
            reasons.add("SOURCE_TARGET_PARITY_MISMATCH")
            diffs = sorted(k for k in expected if comparable.get(k) != expected[k])
            details["parity"].append(source["event_id"] + ":" + ",".join(diffs))

    for target in targets:
        if target["source_event_id"] not in source_by_id:
            reasons.add("UNEXPECTED_TARGET_EVENT")
            details["unexpected_target"].append(target["event_id"])

    status = "PASS" if not reasons else "HOLD"
    core = {
        "schema": RECEIPT_SCHEMA,
        "authority": AUTHORITY,
        "status": status,
        "reasons": sorted(reasons),
        "contract_id": contract["contract_id"],
        "contract_version": contract["version"],
        "contract_digest": _sha(contract),
        "source_digest": _sha(sources),
        "target_digest": _sha(targets),
        "source_unique_count": len(sources),
        "target_unique_count": len(targets),
        "source_conflicting_event_ids": source_conflicts,
        "target_conflicting_event_ids": target_conflicts,
        "details": {k: sorted(v) for k, v in sorted(details.items())},
    }
    return {**core, "receipt_sha256": _sha(core)}


def verify_receipt(
    receipt: Mapping[str, Any],
    contract: Mapping[str, Any],
    source_events: Iterable[Any],
    target_events: Iterable[Any],
    *,
    require_pass: bool = True,
) -> bool:
    """Re-evaluate the bound bundle and compare the whole content-addressed receipt."""
    try:
        expected = evaluate(contract, source_events, target_events)
        if expected != dict(receipt):
            return False
        core = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        if receipt.get("receipt_sha256") != _sha(core):
            return False
        return not require_pass or receipt.get("status") == "PASS"
    except (UATError, KeyError, TypeError, ValueError):
        return False
