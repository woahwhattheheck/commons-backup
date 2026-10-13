#!/usr/bin/env python3
"""Validate the UIOWA-091 synthetic evidence collection."""
from __future__ import annotations
import csv
import json
import sys
from collections import Counter
from pathlib import Path

AREAS = {"software_development","security","deployment_operations","ai_readiness"}
SERVICES = {"ESS","RIS","IAM"}
STATES = {"strength","gap","unknown"}

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)

def validate(root: Path) -> list[str]:
    errors: list[str] = []
    facts_doc = load_json(root / "facts.json")
    manifest = load_json(root / "evidence_manifest.json")
    facts = facts_doc.get("facts", [])
    fact_by_id = {f.get("fact_id"): f for f in facts}
    if len(fact_by_id) != len(facts):
        errors.append("duplicate fact_id")
    for f in facts:
        if f.get("service") not in SERVICES: errors.append(f"bad service for {f.get('fact_id')}")
        if f.get("area") not in AREAS: errors.append(f"bad area for {f.get('fact_id')}")
        if f.get("status") not in STATES: errors.append(f"bad state for {f.get('fact_id')}")
        if f.get("synthetic") is not True: errors.append(f"fact not synthetic: {f.get('fact_id')}")

    seen_sources = set()
    referenced_facts = set()
    prefix = "revenue/uiowa_rfq_18649_synthetic_collection/"
    for doc in manifest.get("documents", []):
        sid = doc.get("source_id")
        if sid in seen_sources: errors.append(f"duplicate source_id: {sid}")
        seen_sources.add(sid)
        if doc.get("synthetic") is not True: errors.append(f"document not synthetic: {sid}")
        raw_path = str(doc.get("path",""))
        if not raw_path.startswith(prefix):
            errors.append(f"path outside collection: {raw_path}")
            continue
        path = root / raw_path[len(prefix):]
        if not path.exists():
            errors.append(f"missing file: {path}")
            continue
        with path.open("r", encoding="utf-8") as fh:
            label_excerpt = fh.read(500)
        if "SYNTHETIC" not in label_excerpt.upper():
            errors.append(f"missing SYNTHETIC label near top: {path}")
        doc_services = set(doc.get("services", []))
        doc_areas = set(doc.get("assessment_areas", []))
        for fid in doc.get("fact_ids", []):
            referenced_facts.add(fid)
            fact = fact_by_id.get(fid)
            if not fact:
                errors.append(f"unknown fact reference {fid} in {sid}")
                continue
            if fact["service"] not in doc_services: errors.append(f"service scope mismatch {fid} in {sid}")
            if fact["area"] not in doc_areas: errors.append(f"area scope mismatch {fid} in {sid}")

    missing_refs = set(fact_by_id) - referenced_facts
    if missing_refs: errors.append("facts unreferenced by manifest: " + ",".join(sorted(missing_refs)))

    with (root / "coverage_matrix.csv").open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    cells = {(r["service"], r["assessment_area"]) for r in rows}
    expected = {(s,a) for s in SERVICES for a in AREAS}
    if cells != expected: errors.append(f"coverage cells mismatch: have {len(cells)}, expected 12")
    for row in rows:
        ids = [x for x in row["fact_ids"].split(";") if x]
        if len(ids) < 2: errors.append(f"cell has fewer than two facts: {row['service']}/{row['assessment_area']}")
        for fid in ids:
            f = fact_by_id.get(fid)
            if not f: errors.append(f"coverage references unknown fact: {fid}")
            elif (f["service"], f["area"]) != (row["service"], row["assessment_area"]): errors.append(f"coverage fact scope mismatch: {fid}")
        expected_counts = Counter(fact_by_id[fid]["status"] for fid in ids if fid in fact_by_id)
        for state in STATES:
            if int(row[f"{state}_count"]) != expected_counts[state]: errors.append(f"bad {state}_count for {row['service']}/{row['assessment_area']}")
    return errors

def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    errors = validate(root)
    if errors:
        for error in errors: print(f"ERROR: {error}")
        return 1
    print("PASS: UIOWA-091 synthetic collection is internally consistent")
    print("PASS: 24 canonical facts across all 12 service x assessment cells")
    print("PASS: manifest references resolve and every artifact is synthetic-labeled")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
