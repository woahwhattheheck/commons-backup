#!/usr/bin/env python3
"""Reproduce UIOWA-120 synthetic examples and the real authority-v2 adapter run."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("uiowa120_source_impact_rehearsal", HERE / "source_impact.py")
impact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impact)
PIN = "1d58638c067b35dbdc210365ac3f30d6e72c9548"
PIN_COMMIT = "809ff46d4a828b2fdb0ea72dd135b1dd5301b926"
AUTHORITY = HERE.parent / "uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json"


def artifact(name, kind, refs):
    return {"id": name, "kind": kind, "locator": "synthetic://review/" + name,
            "depends_on": refs, "notes": "Fictional dependency; not an assertion about a University artifact."}


def synthetic_case():
    """Dated controlled fixtures. Every changed fact is fictional."""
    def source(sid, text, **metadata):
        return {"id": sid, "revision": "r1", "text": text,
                "metadata": {"synthetic": True, **metadata}, "interpretation": {}}
    before = {"schema": impact.MANIFEST, "snapshot_id": "SYNTHETIC-20260918",
              "captured_at": "2026-09-18T13:00:00Z", "namespace": "synthetic-preparation/v1",
              "scope": {"synthetic": True, "purpose": "source-impact demonstration"}, "coverage": "complete",
              "sources": [source("POLICY", "Synthetic normal changes require two reviewers.\n", locator="policy.md#normal"),
                          source("CATALOG", "Synthetic service catalog unchanged.\n", locator="catalog.md#owners"),
                          source("INTERVIEW", None, locator="interview.md#3"),
                          source("STABLE", "Synthetic glossary – no change.\n"),
                          source("RETIRED", "Synthetic superseded worksheet.\n"),
                          source("RATING", "Synthetic supporting record stays unchanged.\n"),
                          {"id": "DIGEST", "revision": "r1", "metadata": {"synthetic": True}, "interpretation": {},
                           "content": {"representation": "opaque-source/v1", "sha256": "a" * 64}}]}
    before["sources"][2]["unavailable_reason"] = "Original interview text not supplied."
    after = copy.deepcopy(before)
    after.update(snapshot_id="SYNTHETIC-20260919", captured_at="2026-09-19T13:00:00Z")
    rows = {s["id"]: s for s in after["sources"]}
    rows["POLICY"].update(text="Synthetic normal changes require two reviewers; urgent exceptions are recorded.\n", revision="r2")
    rows["CATALOG"]["metadata"]["locator"] = "catalog.md#service-owners"
    rows["INTERVIEW"]["metadata"]["review_note"] = "Transcript requested; still unavailable."
    rows["RATING"]["interpretation"]["claim"] = "Synthetic analyst narrowed the claim; source did not change."
    rows["DIGEST"]["content"]["sha256"] = "b" * 64
    after["sources"] = [s for s in after["sources"] if s["id"] != "RETIRED"] + [source("NEW", "Synthetic newly inventoried source.\n")]
    graph = {"schema": impact.GRAPH, "namespace": before["namespace"], "coverage": "complete", "scope": copy.deepcopy(before["scope"]),
             "provenance": {"synthetic": True, "notice": "Complete only for this explicitly fictional dependency set."},
             "artifacts": [artifact("worksheet", "worksheet", [{"source_id": "POLICY"}, {"source_id": "INTERVIEW"}]),
                           artifact("mapping", "mapping", [{"artifact_id": "worksheet"}, {"source_id": "CATALOG"}]),
                           artifact("narrative", "narrative", [{"artifact_id": "mapping"}, {"source_id": "RATING"}, {"source_id": "DIGEST"}]),
                           artifact("inventory", "worksheet", [{"source_id": "RETIRED"}, {"source_id": "NEW"}]),
                           artifact("locator-index", "mapping", [{"source_id": "CATALOG"}]),
                           artifact("glossary", "narrative", [{"source_id": "STABLE"}])]}
    return before, after, graph


def authority_case(path=AUTHORITY):
    """Run the adapter on an actual checked-in fixture; mutate a COPY only."""
    raw = Path(path).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != PIN:
        raise impact.InputError("Pinned authority fixture changed; reconcile source version before replay: " + blob)
    bundle = impact.load_json(path)
    before = impact.adapt_authority(bundle, "AUTHORITY-SYNTHETIC-20260918", "2026-09-18T13:00:00Z",
                                   coverage="complete", provenance={"git_blob": PIN, "git_commit": PIN_COMMIT})
    after = copy.deepcopy(before)
    after.update(snapshot_id="AUTHORITY-SYNTHETIC-MUTATION-20260919", captured_at="2026-09-19T13:00:00Z")
    after["provenance"]["synthetic_mutation"] = "Controlled test edits; no upstream file was changed."
    rows = {s["id"]: s for s in after["sources"]}
    rows["ESS-SW-01"]["content"]["sha256"] = hashlib.sha256(b"fictional replacement bytes").hexdigest()
    rows["RIS-SEC-01"]["metadata"]["source_ref"] += "#corrected-locator"
    rows["IAM-DEP-01"]["interpretation"]["claim"] += " Synthetic analyst clarification."
    graph = {"schema": impact.GRAPH, "namespace": before["namespace"], "coverage": "partial", "scope": copy.deepcopy(before["scope"]),
             "provenance": {"synthetic": True, "notice": "Illustrative review links, not a survey of all existing artifact dependencies."},
             "artifacts": [artifact("authority-worksheet", "worksheet", [{"source_id": "ESS-SW-01"}, {"source_id": "RIS-SEC-01"}]),
                           artifact("authority-mapping", "mapping", [{"artifact_id": "authority-worksheet"}, {"source_id": "IAM-DEP-01"}]),
                           artifact("authority-narrative", "narrative", [{"artifact_id": "authority-mapping"}])]}
    return before, after, graph


def run(out, authority=AUTHORITY):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    receipts = {}
    for name, inputs in (("synthetic", synthetic_case()), ("authority-adapter", authority_case(authority))):
        destination = out / name
        report = impact.analyze(*inputs)
        impact.write_report(report, destination)
        for filename, data in zip(("before.json", "after.json", "dependencies.json"), inputs):
            (destination / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipts[name] = {"status": report["status"], "counts": report["counts"],
                          "artifact_count": len(report["artifacts"]), "report_sha256": impact.digest(report),
                          "input_sha256": report["input_sha256"]}
    receipts["authority_input"] = {"git_blob": PIN, "git_commit": PIN_COMMIT, "sources": 12,
                                  "notice": "Actual existing synthetic authority fixture; no compiler execution or authority verification claimed."}
    (out / "receipt.json").write_text(json.dumps(receipts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--authority", type=Path, default=AUTHORITY)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.out_dir, args.authority), indent=2, sort_keys=True))
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
