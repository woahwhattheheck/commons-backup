#!/usr/bin/env python3
"""Connect verified fictional fixture specifications to the existing 047 assessor.

No application run, refresh, cleanup, or actual historical creation is inferred.
The required created-at value is a synthetic scenario time, not a clock receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType

from fixture_lab import (CatalogError, _date, _timestamp, build_bundle, canonical,
                         digest, load_json, validate_catalog, verify_bundle,
                         write_bundle)

SCHEMA = "tjlabs.testdata.canonical-bridge.v1"
NOTICE = ("FICTIONAL SPECIFICATION PREVIEW. Scenario creation time is not a historical "
          "execution receipt. Generated expectations are not observed application "
          "results. Canonical unknowns are not failed application tests.")


def canonical_path() -> Path:
    return Path(__file__).resolve().parent.parent / "uiowa_rfq_18649_test_data" / "assess.py"


def load_assessor(path: Path | None = None) -> tuple[ModuleType, dict]:
    # Only the caller's local repository code is loaded, never a path from data.
    source = (path or canonical_path()).resolve()
    raw = source.read_bytes()
    sha256 = digest(raw)
    module = ModuleType("osprey_canonical_assessor_" + sha256)
    module.__file__ = str(source)
    exec(compile(raw, str(source), "exec"), module.__dict__)
    for name in ("assess", "validate", "markdown"):
        if not callable(getattr(module, name, None)):
            raise CatalogError(f"canonical assessor lacks {name}")
    return module, {"repository_path": "revenue/uiowa_rfq_18649_test_data/assess.py",
                    "sha256": sha256,
                    "git_blob_sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}


def _key(kind: str, *parts: str) -> str:
    return "OSPREY-" + kind + "-" + digest(canonical(list(parts)))


def prepare(root: Path, created_at: str, as_of: str) -> dict:
    created = _timestamp(created_at, "created_at")
    cutoff = _timestamp(as_of, "as_of")
    receipt = verify_bundle(root)
    manifest = load_json(root / "manifest.json")
    source = validate_catalog(load_json(root / "catalog.json"))
    frozen = build_bundle(source, _date(manifest["as_of"], "manifest.as_of"))
    if digest(frozen["manifest.json"]) != receipt["manifest_sha256"]:
        raise CatalogError("bundle changed during capture; no mapping was produced")
    converted = {"schema_version": 1, "context": "synthetic-demo", "contracts": [], "fixtures": []}
    lineage = []
    mapped_cases = 0
    unmapped_cases = 0
    for item in sorted(source["fixtures"], key=lambda row: row["id"]):
        member = "fixtures/" + item["id"] + ".json"
        cases = json.loads(frozen[member])["cases"]
        record = {"source_id": item["id"], "source_definition": item,
                  "source_pointer": member, "source_member_sha256": digest(frozen[member]),
                  "cases": cases, "mapping_notes": [], "canonical_fixture_id": None,
                  "canonical_contract_id": None}
        lineage.append(record)
        if item["target_interface_version"] is None:
            unmapped_cases += len(cases)
            record["status"] = "UNMAPPED_TARGET_VERSION_UNKNOWN"
            record["mapping_notes"].append("No current contract version was invented; all case specifications remain in this record.")
            continue
        fixture_id = _key("FIXTURE", source["catalog_id"], item["id"], item["version"])
        contract_id = _key("CONTRACT", source["catalog_id"], item["id"], item["target_interface_version"])
        record.update(status="SPECIFICATIONS_MAPPED", canonical_fixture_id=fixture_id,
                      canonical_contract_id=contract_id)
        record["mapping_notes"] += [
            "SOURCE_HISTORY_RETAINED_ONLY: date-only refresh/retirement and opaque pointers are not converted into events.",
            "REVIEW_CADENCE_NOT_REFRESH_CADENCE: refresh_interval_days stays null; the source review interval remains in source_definition.",
            "SCENARIO_CREATION: created_at is the declared fictional preview creation time, not the source fixture's historical creation.",
            "NO_APPLICATION_RUNS: reference expectations become specifications; runs, refreshes and cleanups remain empty."]
        effort = item["maintenance_hours"]
        point_effort = effort["low"] if effort is not None and effort["low"] == effort["high"] else None
        if effort is not None and point_effort is None:
            record["mapping_notes"].append("EFFORT_RANGE_NOT_POINT: the complete interval remains in source_definition; no midpoint was invented.")
        retired = _date(item["retired_on"], "retired_on", nullable=True)
        current_state = "retired" if retired and retired <= cutoff.date() else "active"
        converted["contracts"].append({"id": contract_id, "group": item["group"],
            "version": item["target_interface_version"], "required_cases": [case["case_id"] for case in cases]})
        converted["fixtures"].append({"id": fixture_id, "contract_id": contract_id,
            "contract_version": item["source_interface_version"], "fixture_version": item["version"],
            "origin": "synthetic", "state": current_state, "owner": item["owner_role"],
            "maintenance_hours": point_effort, "refresh_interval_days": None,
            "recipe_ref": "sha256:" + digest(frozen[member]) + "#" + member,
            "created_at": created.isoformat(), "cleanup_due_at": None,
            "refreshes": [], "cleanups": [],
            "cases": [{"id": c["case_id"], "input_class": c["boundary"],
                       "expected_behavior": c["contract_assumption"] + " Reference only: " +
                           canonical(c["reference_expectation"]).decode().strip(), "runs": []} for c in cases]})
        mapped_cases += len(cases)
    return {"schema": SCHEMA, "notice": NOTICE, "source_bundle": receipt,
            "created_at": created.isoformat(), "as_of": cutoff.isoformat(),
            "summary": {"source_fixtures": len(lineage), "mapped_fixtures": len(converted["fixtures"]),
                        "unmapped_fixtures": len(lineage) - len(converted["fixtures"]),
                        "planned_cases": mapped_cases + unmapped_cases,
                        "mapped_cases": mapped_cases, "unmapped_cases": unmapped_cases,
                        "recorded_application_runs": 0},
            "canonical_catalog": converted if converted["contracts"] else None, "lineage": lineage}


def run_bridge(root: Path, created_at: str, as_of: str) -> dict[str, bytes]:
    mapping = prepare(root, created_at, as_of)
    report = None
    binding = None
    if mapping["canonical_catalog"] is not None:
        assessor, binding = load_assessor()
        assessor.validate(mapping["canonical_catalog"])
        report = assessor.assess(mapping["canonical_catalog"], mapping["as_of"])
        if (report["summary"]["cases_with_supported_evidence"] != 0 or
                report["summary"]["cases_with_recorded_failure"] != 0 or
                any(c["status"] != "unknown" for f in report["fixtures"] for c in f["cases"])):
            raise CatalogError("canonical output promoted a generated specification into an application result")
        if report["summary"]["required_cases"] != mapping["summary"]["mapped_cases"]:
            raise CatalogError("canonical output lost or duplicated mapped cases")
    mapping["canonical_source"] = binding
    mapping["state"] = "CANONICAL_ASSESSOR_EXECUTED" if report is not None else "NO_MAPPED_CONTRACTS"
    summary = mapping["summary"]
    explanation = ("# Fictional fixture-to-assessor rehearsal\n\n" + NOTICE + "\n\n" +
        f"{summary['source_fixtures']} definitions / {summary['planned_cases']} planned cases. " +
        f"{summary['mapped_cases']} mapped; {summary['unmapped_cases']} retained but unmapped. " +
        "Recorded application runs: 0.\n\n" +
        "The existing assessor, not a new scoring engine, evaluates mapped specifications. " +
        "No refresh cadence is inferred from review cadence, and no effort midpoint is substituted. " +
        "Full original definitions and generated cases remain in mapping.json. " +
        "A missing target version prevents contract mapping rather than inventing a version.\n\n" +
        (assessor.markdown(report) if report is not None else
         "NO_MAPPED_CONTRACTS: canonical assessor not executed; no empty-input pass was claimed.\n"))
    files = {"mapping.json": canonical(mapping), "REHEARSAL.md": explanation.encode("utf-8")}
    if report is not None:
        files["canonical_catalog.json"] = canonical(mapping["canonical_catalog"])
        files["canonical_report.json"] = canonical(report)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--created-at", required=True, help="Declared fictional preview creation timestamp with timezone")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.out.resolve().is_relative_to(args.bundle.resolve()):
            raise CatalogError("output must not change the input bundle")
        files = run_bridge(args.bundle, args.created_at, args.as_of)
        write_bundle(files, args.out)
        print(canonical({"output_files": len(files), "mapping_sha256": digest(files["mapping.json"]),
                         "notice": NOTICE}).decode(), end="")
        return 0
    except (CatalogError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"canonical-bridge: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
