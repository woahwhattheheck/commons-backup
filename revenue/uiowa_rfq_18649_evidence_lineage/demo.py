"""Materialize a fictional before/after evidence collection in a NEW directory."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import lineage


OLD_TEXT = {
    "ESS-P1": "FICTIONAL ESS delivery notes v1\n1. Review a change.\n2. Record acceptance.\n",
    "RIS-R1": "FICTIONAL RIS service notes\nSupport owner: example role R.\n",
    "IAM-A1": "FICTIONAL IAM review v1\nOwner handoff is documented in sample ticket.\n",
    "ESS-C1": "FICTIONAL test catalog v1\nBoundary behavior A is covered.\n",
    "RIS-X1": "FICTIONAL retired interview note\nFollow-up required on example workflow.\n",
}
NEW_TEXT = {
    "ESS-P2": "FICTIONAL ESS delivery notes v2\n1. Review a change.\n2. Record acceptance.\n3. Record support handoff.\n",
    "RIS-R1": OLD_TEXT["RIS-R1"],
    "RIS-RCOPY": OLD_TEXT["RIS-R1"],
    "IAM-A1": "FICTIONAL IAM review v1\nOwner handoff evidence is not supplied.\n",
    "ESS-C2": "FICTIONAL test catalog v2\nBoundary behavior A and B are covered.\n",
    "RIS-S1": "FICTIONAL research delivery notes\nSeparate service and independent document.\n",
    "ESS-NEW": "FICTIONAL new design decision\nDecision owner: example role D.\n",
}


def row(rid: str, document: str, version: str, title: str, location: str) -> dict:
    return {"record_id": rid, "document_id": document, "version": version,
            "title": title, "location": location,
            "metadata": {"owner_role": "fictional assessment custodian",
                         "classification": "synthetic", "locator_example": "lines 1-3"}}


def build(destination: Path) -> dict:
    """Write invented fixtures only. Refuse to reuse an existing destination."""
    destination.mkdir(parents=True, exist_ok=False)
    old = [row("ESS-P1", "ESS-DELIVERY", "v1", "Delivery notes", "ess.txt"),
           row("RIS-R1", "RIS-SUPPORT", "v1", "Service notes", "ris.txt"),
           row("IAM-A1", "IAM-REVIEW", "v1", "Access review", "iam.txt"),
           row("ESS-C1", "ESS-CATALOG", "v1", "Test catalog", "catalog.txt"),
           row("RIS-X1", "RIS-INTERVIEW", "v1", "Retired note", "interview.txt")]
    new = [row("ESS-P2", "ESS-DELIVERY", "v2", "Delivery notes", "ess-v2.txt"),
           row("RIS-R1", "RIS-SUPPORT", "v1", "Service notes", "renamed-ris.txt"),
           row("RIS-RCOPY", "RIS-SUPPORT", "v1", "Service notes", "copied-ris.txt"),
           row("IAM-A1", "IAM-REVIEW", "v1", "Access review", "iam.txt"),
           row("ESS-C2", "ESS-CATALOG", "v2", "Test catalog", "catalog-v2.txt"),
           row("RIS-S1", "RIS-DELIVERY", "v1", "Delivery notes", "ris-delivery.txt"),
           row("ESS-NEW", "ESS-DESIGN", "v1", "New design", "design.txt")]
    new[0]["supersedes"] = [{"record_id": "ESS-P1", "sha256": hashlib.sha256(OLD_TEXT["ESS-P1"].encode()).hexdigest()}]
    manifests = []
    for label, records, texts in (("before", old, OLD_TEXT), ("after", new, NEW_TEXT)):
        root = destination / label
        root.mkdir()
        for record in records:
            (root / record["location"]).write_bytes(texts[record["record_id"]].encode("utf-8"))
        catalog = {"schema": lineage.SCHEMA, "collection_id": "synthetic-" + label,
                   "synthetic": True, "records": records,
                   "metadata": {"purpose": "rehearsal only; no University observations"}}
        (destination / (label + "-catalog.json")).write_text(lineage.encoded(catalog), encoding="utf-8")
        manifest = lineage.snapshot(catalog, root)
        manifests.append(manifest)
        (destination / (label + ".json")).write_text(lineage.encoded(manifest), encoding="utf-8")
    findings = {"findings": []}
    for record in manifests[0]["records"]:
        citation = lineage.reference(record)
        citation["locator"] = "lines 1-3 (fictional locator, not automatically revalidated)"
        findings["findings"].append({"finding_id": "F-" + record["record_id"], "citations": [citation],
                                     "metadata": {"claim_status": "synthetic rehearsal, not assessed"}})
    findings["findings"].append({"finding_id": "F-NO-EVIDENCE", "citations": []})
    (destination / "findings.json").write_text(lineage.encoded(findings), encoding="utf-8")
    report = lineage.compare(*manifests, findings)
    (destination / "review.json").write_text(lineage.encoded(report), encoding="utf-8")
    (destination / "review.md").write_text(lineage.markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new directory for fictional files and review outputs")
    args = parser.parse_args()
    try:
        report = build(args.destination)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Demo could not create a new collection: {exc}\n")
    print(lineage.encoded(report["summary"]), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
