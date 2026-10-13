"""Rehearse evidence arrivals with the real lineage engine and fictional records.

The same declared history is deliberately exported in several incomplete forms.
No source is declared deleted, approved, authentic, or current by this program.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path

import lineage


def record(identifier: str, version: str, predecessors: list[dict] | None = None) -> dict:
    payload = f"FICTIONAL release-review notes {version}\nRecord: {identifier}\n"
    result = {"record_id": identifier, "document_id": "SYNTHETIC-DELIVERY-NOTES",
              "version": version, "title": "Fictional release-review notes",
              "location": f"source-{identifier}.txt",
              "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
              "metadata": {"example_text": payload, "owner_role": "fictional custodian"}}
    if predecessors:
        result["supersedes"] = [lineage.reference(p) for p in predecessors]
    return result


def collection(identifier: str, records: list[dict]) -> dict:
    return {"schema": lineage.SCHEMA, "collection_id": identifier,
            "synthetic": True, "hash_basis": "FICTIONAL_FIXTURE_TEXT",
            "records": deepcopy(records)}


def scenarios() -> list[dict]:
    """Editable inputs, expected queue labels, and explicit follow-up questions."""
    a = record("A", "v1")
    b = record("B", "v2", [a])
    c = record("C", "v3", [b])
    d = record("D", "parallel-draft", [a])
    e = record("E", "reconciled-draft", [c, d])
    definitions = [
        ("01-original-retained", [a, b, c], [a], "DECLARED_SUCCESSOR_MISSING_REVIEW",
         "A is still supplied, but the declared terminal C is omitted. Request C or explain the export boundary; do not silently treat A as the selected revision."),
        ("02-intermediate-retained", [a, b, c], [b], "DECLARED_SUCCESSOR_MISSING_REVIEW",
         "B remains an intermediate declaration, not the terminal. Preserve the request for C without inferring its deletion."),
        ("03-no-records-supplied", [a, b, c], [], "DECLARED_SUCCESSOR_MISSING_REVIEW",
         "No after records were supplied. The known declaration ending at C remains relevant; reconcile the collection before selecting a citation."),
        ("04-terminal-arrives", [a, b, c], [c], "DECLARED_SUPERSEDED_REVIEW",
         "C is now present by exact record ID and digest. Read its passage and decide whether the original finding concerns the old or new period. Presence is not approval."),
        ("05-one-branch-omitted", [a, b, c, d], [c], "BRANCHED_SUCCESSION_REVIEW",
         "C and D are both known terminal declarations. Only C was supplied; omission of D does not choose a winner."),
        ("06-both-branches-arrive", [a, b, c, d], [c, d], "BRANCHED_SUCCESSION_REVIEW",
         "Both drafts are present. Determine whether they are competing revisions or legitimately parallel scopes; retain the disagreement."),
        ("07-declared-convergence", [a, b, c, d], [e], "DECLARED_SUPERSEDED_REVIEW",
         "E explicitly references both prior branches. This resolves the graph to one supplied terminal, not the substantive review or approval decision."),
    ]
    result = []
    for name, before, after, expected, question in definitions:
        result.append({"name": name, "before": collection(name + "-before", before),
                       "after": collection(name + "-after", after),
                       "findings": {"findings": [{"finding_id": "F-SYNTHETIC-HANDOFF",
                           "citations": [{**lineage.reference(a), "locator": "line 1 (fictional)"}],
                           "note": "Historical sample statement, not a University finding."}]},
                       "expected_status": expected, "follow_up": question})
    return result


def build(destination: Path) -> dict:
    """Create a fresh editable packet; never replace a previous rehearsal."""
    cases = scenarios()
    evaluated = []
    for case in cases:
        report = lineage.compare(case["before"], case["after"], case["findings"])
        impact = report["finding_impacts"][0]
        lineage.require(impact["status"] == case["expected_status"],
                        f"rehearsal expectation failed: {case['name']}")
        evaluated.append((case, report))
    # Complete semantic evaluation before creating any destination.
    destination.mkdir(parents=True, exist_ok=False)
    rows = []
    for case, report in evaluated:
        folder = destination / case["name"]
        folder.mkdir()
        for kind in ("before", "after", "findings"):
            (folder / (kind + ".json")).write_text(lineage.encoded(case[kind]), encoding="utf-8")
        for label in ("before", "after"):
            sources = folder / label
            sources.mkdir()
            for source in case[label]["records"]:
                payload = source["metadata"]["example_text"].encode("utf-8")
                lineage.require(hashlib.sha256(payload).hexdigest() == source["sha256"],
                                "fictional source digest mismatch")
                (sources / source["location"]).write_bytes(payload)
        (folder / "review.json").write_text(lineage.encoded(report), encoding="utf-8")
        (folder / "review.md").write_text(lineage.markdown(report), encoding="utf-8")
        impact = report["finding_impacts"][0]
        rows.append({"case": case["name"], "status": impact["status"],
                     "present_terminal_records": [r["record_id"] for r in impact["declared_successors"]],
                     "absent_terminal_records": [r["record_id"] for r in impact.get("missing_declared_successors", [])],
                     "follow_up": case["follow_up"],
                     "report_sha256": hashlib.sha256(lineage.encoded(report).encode()).hexdigest()})
    summary = {"synthetic": True, "status": "DRAFT_NON_AUTHORITATIVE", "cases": rows}
    (destination / "walkthrough.json").write_text(lineage.encoded(summary), encoding="utf-8")
    lines = ["# Seven evidence-arrival decisions", "", "**Fictional records; not an assessment or approval.**", "",
             "| Case | Actual queue status | Supplied terminal IDs | Omitted terminal IDs |", "| --- | --- | --- | --- |"]
    for row in rows:
        present = ", ".join(row["present_terminal_records"]) or "None"
        missing = ", ".join(row["absent_terminal_records"]) or "None"
        lines.append(f"| {row['case']} | {row['status']} | {present} | {missing} |")
    for row in rows:
        lines += ["", "## " + row["case"], "", row["follow_up"]]
    lines += ["", "Every case contains editable before/after/findings JSON, the fictional source files, and real engine reports.",
              "An omitted record is not proof of deletion. A declared terminal is not an approved or current source.",
              "If an I/O failure interrupts creation, treat the directory as incomplete and choose a new destination; it is not an atomic bundle install.", ""]
    (destination / "walkthrough.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new directory for seven editable synthetic cases")
    args = parser.parse_args(argv)
    try:
        summary = build(args.destination)
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"Rehearsal not completed: {exc}", file=__import__("sys").stderr)
        return 2
    print(lineage.encoded(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
