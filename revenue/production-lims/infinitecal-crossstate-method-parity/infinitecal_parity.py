#!/usr/bin/env python3
"""Deterministic synthetic InfiniteCAL cross-state method parity bridge.

This module is intentionally read-only and synthetic. It reconciles immutable
fixture records and stages review artifacts; it never writes to state systems
or makes a compliance decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping
import argparse
import copy
import hashlib
import json
import re

TASK_ID = "infinitecal-crossstate-method-parity-lims-01"
STATES = ("CA", "MI", "NY")
CLEAN = "PARITY_CLEAN"
METHOD_MISMATCH = "METHOD_VERSION_MISMATCH"
UNIT_ROUNDING_MISMATCH = "UNIT_ROUNDING_MISMATCH"
DUPLICATE_ACCESSION = "DUPLICATE_ACCESSION"
MISSING_SOURCE_FILE = "MISSING_SOURCE_FILE"
STAGED = "STAGED_HUMAN_REVIEW"
RELEASED = "RELEASED_BY_NAMED_HUMAN"
_RESERVED_AUTOMATION_REVIEWER_TOKENS = frozenset(
    {"agent", "ai", "auto", "automated", "automation", "bot", "robot", "service", "system"}
)


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Ledger:
    processed_record_ids: set[str] = field(default_factory=set)
    accepted_by_accession: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    holds: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    drafts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        return {
            "processed": len(self.processed_record_ids),
            "accepted": len(self.accepted_by_accession),
            "holds": len(self.holds),
            "drafts": len(self.drafts),
            "events": len(self.events),
        }


def validate_fixture_hash(fixture_path: Path, manifest_path: Path) -> Mapping[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = sha256_file(fixture_path)
    expected = manifest.get("fixture_sha256")
    if actual != expected:
        raise ValueError(f"FIXTURE_HASH_MISMATCH expected={expected} actual={actual}")
    return manifest


def _expand_recipe(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    states = payload.get("states")
    materials = payload.get("materials")
    analytes = payload.get("analytes")
    fault_plan = payload.get("fault_plan")
    rule_pack_version = payload.get("rule_pack_version")
    if states != list(STATES) or not isinstance(materials, list) or len(materials) != 20:
        raise ValueError("FIXTURE_RECIPE_SHAPE_MISMATCH")
    if not isinstance(analytes, list) or len(analytes) != 3 or not isinstance(fault_plan, dict):
        raise ValueError("FIXTURE_RECIPE_SHAPE_MISMATCH")

    records: List[Dict[str, Any]] = []
    for state in states:
        state_faults = fault_plan.get(state)
        if not isinstance(state_faults, dict):
            raise ValueError("FIXTURE_FAULT_PLAN_MISSING")
        fault_by_index: Dict[int, str] = {}
        for code in (METHOD_MISMATCH, UNIT_ROUNDING_MISMATCH, DUPLICATE_ACCESSION, MISSING_SOURCE_FILE):
            indices = state_faults.get(code, [])
            if not isinstance(indices, list):
                raise ValueError("FIXTURE_FAULT_PLAN_INVALID")
            for raw_index in indices:
                index = int(raw_index)
                if index in fault_by_index:
                    raise ValueError("FIXTURE_FAULT_PLAN_OVERLAP")
                fault_by_index[index] = code

        local_index = 0
        for material_number, material_id in enumerate(materials, start=1):
            for analyte in analytes:
                local_index += 1
                fault = fault_by_index.get(local_index)
                canonical_value = f"{(material_number * 17 + int(analyte['offset'])) / 13:.4f}"
                canonical = {
                    "analyte": analyte["name"],
                    "loq": analyte["loq"],
                    "method_id": analyte["method_id"],
                    "method_version": analyte["method_version"],
                    "rounding": analyte["rounding"],
                    "unit": analyte["unit"],
                    "value": canonical_value,
                }
                state_output = {
                    "instrument_result_id": f"{state}-IR-{material_id}-{analyte['name']}",
                    "loq": analyte["loq"],
                    "material_id": material_id,
                    "method_id": analyte["method_id"],
                    "method_version": analyte["method_version"],
                    "rounding": analyte["rounding"],
                    "rule_pack_id": f"{state}-PARITY-RULES",
                    "rule_pack_version": rule_pack_version,
                    "unit": analyte["unit"],
                    "value": canonical_value,
                }
                if fault == METHOD_MISMATCH:
                    state_output["method_version"] = f"{analyte['method_version']}-STALE"
                elif fault == UNIT_ROUNDING_MISMATCH:
                    state_output["rounding"] = int(analyte["rounding"]) + 1

                accession_index = local_index - 1 if fault == DUPLICATE_ACCESSION else local_index
                records.append(
                    {
                        "accession_id": f"{state}-ACC-{accession_index:03d}",
                        "canonical": canonical,
                        "material_id": material_id,
                        "record_id": f"{state}-REC-{local_index:03d}",
                        "seeded_fault": fault,
                        "source_file": None if fault == MISSING_SOURCE_FILE else f"synthetic://source/{material_id}/{analyte['name']}.json",
                        "state": state,
                        "state_output": state_output,
                    }
                )
        if local_index != 60 or set(fault_by_index) - set(range(1, 61)):
            raise ValueError("FIXTURE_FAULT_INDEX_OUT_OF_RANGE")
    return records


def load_fixture(fixture_path: Path, manifest_path: Path) -> List[Dict[str, Any]]:
    validate_fixture_hash(fixture_path, manifest_path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if payload.get("task_id") != TASK_ID:
        raise ValueError("TASK_ID_MISMATCH")
    records = payload.get("records")
    if isinstance(records, list):
        return records
    if payload.get("schema_version") == 2:
        return _expand_recipe(payload)
    raise ValueError("RECORDS_NOT_LIST")


def parity_hashes(record: Mapping[str, Any]) -> Dict[str, str]:
    canonical = record["canonical"]
    return {
        "analyte_hash": sha256_json(canonical["analyte"]),
        "unit_hash": sha256_json(canonical["unit"]),
        "loq_hash": sha256_json(canonical["loq"]),
        "result_hash": sha256_json(
            {
                "material_id": record["material_id"],
                "analyte": canonical["analyte"],
                "value": canonical["value"],
                "unit": canonical["unit"],
                "loq": canonical["loq"],
            }
        ),
    }


def lineage_hash(record: Mapping[str, Any]) -> str:
    state_output = record["state_output"]
    return sha256_json(
        {
            "state": record["state"],
            "rule_pack_id": state_output["rule_pack_id"],
            "rule_pack_version": state_output["rule_pack_version"],
            "method_id": state_output["method_id"],
            "method_version": state_output["method_version"],
            "instrument_result_id": state_output["instrument_result_id"],
        }
    )


def classify(record: Mapping[str, Any], ledger: Ledger) -> str:
    """Return the deterministic first failing gate without mutating the record."""
    accession = record["accession_id"]
    canonical = record["canonical"]
    state_output = record["state_output"]

    if accession in ledger.accepted_by_accession:
        return DUPLICATE_ACCESSION
    if not record.get("source_file"):
        return MISSING_SOURCE_FILE
    if state_output["method_id"] != canonical["method_id"] or state_output["method_version"] != canonical["method_version"]:
        return METHOD_MISMATCH
    if state_output["unit"] != canonical["unit"] or state_output["rounding"] != canonical["rounding"]:
        return UNIT_ROUNDING_MISMATCH
    return CLEAN


def process_record(record: Mapping[str, Any], ledger: Ledger) -> Dict[str, Any]:
    record_id = record["record_id"]
    if record_id in ledger.processed_record_ids:
        return {"record_id": record_id, "status": "IDEMPOTENT_REPLAY", "mutated": False}

    ledger.processed_record_ids.add(record_id)
    status = classify(record, ledger)
    hashes = parity_hashes(record)
    lin_hash = lineage_hash(record)

    if status != CLEAN:
        hold = {
            "record_id": record_id,
            "accession_id": record["accession_id"],
            "state": record["state"],
            "material_id": record["material_id"],
            "hold_code": status,
            "lineage_hash": lin_hash,
            **hashes,
        }
        ledger.holds[record_id] = hold
        ledger.events.append({"record_id": record_id, "event": "HOLD", "code": status})
        return {"record_id": record_id, "status": status, "mutated": True}

    accepted = {
        "record_id": record_id,
        "accession_id": record["accession_id"],
        "state": record["state"],
        "material_id": record["material_id"],
        "source_file": record["source_file"],
        "rule_pack_id": record["state_output"]["rule_pack_id"],
        "rule_pack_version": record["state_output"]["rule_pack_version"],
        "method_id": record["state_output"]["method_id"],
        "method_version": record["state_output"]["method_version"],
        "lineage_hash": lin_hash,
        **hashes,
    }
    ledger.accepted_by_accession[record["accession_id"]] = accepted
    ledger.drafts[record_id] = {
        "record_id": record_id,
        "state": record["state"],
        "material_id": record["material_id"],
        "status": STAGED,
        "reviewer": None,
        "result_hash": hashes["result_hash"],
        "lineage_hash": lin_hash,
    }
    ledger.events.append({"record_id": record_id, "event": "STAGE_DRAFT", "status": STAGED})
    return {"record_id": record_id, "status": CLEAN, "mutated": True}


def run_records(records: Iterable[Mapping[str, Any]], ledger: Ledger | None = None) -> Dict[str, Any]:
    ledger = ledger or Ledger()
    before = ledger.counts()
    outcomes = [process_record(record, ledger) for record in records]
    after = ledger.counts()
    delta = {key: after[key] - before[key] for key in before}
    statuses: Dict[str, int] = {}
    for outcome in outcomes:
        statuses[outcome["status"]] = statuses.get(outcome["status"], 0) + 1
    return {"ledger": ledger, "outcomes": outcomes, "statuses": statuses, "delta": delta}


def _named_human_reviewer(reviewer: str) -> str:
    reviewer = (reviewer or "").strip()
    tokens = re.findall(r"[a-z]+", reviewer.casefold())
    reserved = any(
        "".join(tokens[i:j]) in _RESERVED_AUTOMATION_REVIEWER_TOKENS
        for i in range(len(tokens))
        for j in range(i + 1, len(tokens) + 1)
    )
    if not reviewer or reserved:
        raise ValueError("NAMED_HUMAN_REVIEWER_REQUIRED")
    return reviewer


def release_draft(ledger: Ledger, record_id: str, reviewer: str) -> Dict[str, Any]:
    reviewer = _named_human_reviewer(reviewer)
    draft = ledger.drafts.get(record_id)
    if draft is None:
        raise KeyError("DRAFT_NOT_FOUND")
    updated = copy.deepcopy(draft)
    updated["status"] = RELEASED
    updated["reviewer"] = reviewer
    return updated


def assert_acceptance(records: List[Mapping[str, Any]], result: Mapping[str, Any]) -> Dict[str, Any]:
    ledger: Ledger = result["ledger"]
    statuses = result["statuses"]
    expected = {
        CLEAN: 150,
        METHOD_MISMATCH: 12,
        UNIT_ROUNDING_MISMATCH: 9,
        DUPLICATE_ACCESSION: 6,
        MISSING_SOURCE_FILE: 3,
    }
    if statuses != expected:
        raise AssertionError(f"status_counts {statuses!r} != {expected!r}")
    state_counts = {state: 0 for state in STATES}
    materials = {state: set() for state in STATES}
    clean_parity: Dict[tuple[str, str], set[tuple[str, str, str]]] = {}
    for record in records:
        state = record["state"]
        if state not in state_counts:
            raise AssertionError(f"unexpected state {state}")
        state_counts[state] += 1
        materials[state].add(record["material_id"])
        if record["state_output"]["material_id"] != record["material_id"]:
            raise AssertionError("cross-state sample swap")
        record_id = record["record_id"]
        if record_id in ledger.drafts:
            hashes = parity_hashes(record)
            key = (record["material_id"], record["canonical"]["analyte"])
            clean_parity.setdefault(key, set()).add(
                (hashes["analyte_hash"], hashes["unit_hash"], hashes["loq_hash"])
            )
            if ledger.drafts[record_id]["status"] != STAGED or ledger.drafts[record_id]["reviewer"] is not None:
                raise AssertionError("draft release state violated")
    if state_counts != {"CA": 60, "MI": 60, "NY": 60}:
        raise AssertionError(f"state counts {state_counts}")
    if any(len(items) != 20 for items in materials.values()):
        raise AssertionError("each state must carry the same 20 blinded materials")
    if any(len(hashes) != 1 for hashes in clean_parity.values()):
        raise AssertionError("canonical analyte/unit/LOQ parity drift")
    if ledger.counts() != {"processed": 180, "accepted": 150, "holds": 30, "drafts": 150, "events": 180}:
        raise AssertionError(f"ledger counts {ledger.counts()}")
    return {
        "status_counts": statuses,
        "state_counts": state_counts,
        "ledger_counts": ledger.counts(),
        "clean_parity_keys": len(clean_parity),
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=Path(__file__).with_name("fixtures") / "infinitecal_180_records.json")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("fixtures") / "manifest.json")
    args = parser.parse_args(argv)
    records = load_fixture(args.fixture, args.manifest)
    first = run_records(records)
    acceptance = assert_acceptance(records, first)
    before = first["ledger"].counts()
    replay = run_records(records, first["ledger"])
    after = first["ledger"].counts()
    if replay["delta"] != {"processed": 0, "accepted": 0, "holds": 0, "drafts": 0, "events": 0} or before != after:
        raise AssertionError("replay was not side-effect free")
    print(
        json.dumps(
            {
                "task_id": TASK_ID,
                "acceptance": acceptance,
                "replay_delta": replay["delta"],
                "release_policy": STAGED,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())