#!/usr/bin/env python3
"""UIOWA-095 -- deterministic synthetic collection generator.

Produces an evidence-and-report collection of a requested size, in the shape
the delivered lanes use: evidence -> findings -> recommendations -> trace-map,
plus the report surfaces the trace-map points at, plus the evidence documents
the label scan walks.

EVERYTHING THIS WRITES IS FICTION. Every generated document carries a
SYNTHETIC label in its first line, every row carries ``synthetic=true``, and no
string in here is drawn from any real University of Iowa system, person,
incident or record. The generator exists so the benchmark has a workload of a
known size -- not so anyone can mistake its output for findings.

Determinism: seeded ``random.Random``. Same profile + same seed = byte-identical
collection, which is what makes the benchmark re-runnable by a second operator.

Each profile seeds a fixed, small set of deliberate defects so the workflow has
something real to find at every size:

  * two findings that cite an evidence id that does not exist
  * two trace statements that were never written into the report text
  * one document listed in the manifest that is not on disk
  * one (service x assessment area) cell left with no evidence at all, so the
    coverage rollup has to emit UNKNOWN rather than zero

The defect count is held constant across sizes on purpose: it keeps the
measured curve a measurement of workload size, not of defect density.

Python 3 standard library only. No network.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

SYNTHETIC_BANNER = "<!-- SYNTHETIC: fictional content generated for UIOWA-095 capacity benchmarking. Not University data. -->"

SERVICES = ["ESS", "RIS", "IAM"]
AREAS = ["software_development", "security", "deployment_operations", "ai_readiness"]
SOURCE_TYPES = ["requirement", "test_result", "runbook", "change_record", "interview_note", "log_export"]
EVIDENCE_STATES = ["strength", "gap", "unknown"]

# Fictional subject fragments. Deliberately generic -- no real system names.
SUBJECTS = [
    "the fictional enrollment path", "the fictional records exchange",
    "the fictional identity broker", "the fictional batch reconciliation job",
    "the fictional notification fan-out", "the fictional archive restore path",
    "the fictional scheduled export", "the fictional access review cycle",
]
VERBS = [
    "retains an auditable trail for", "has no retained artifact covering",
    "was exercised once during", "is described but not demonstrated for",
    "carries a reviewed configuration for", "has an owner recorded for",
]


@dataclass(frozen=True)
class Profile:
    """A workload size. Counts are inputs to the benchmark, not estimates."""

    name: str
    evidence: int
    findings: int
    recommendations: int
    statements: int
    documents: int
    doc_body_lines: int          # ordinary document length
    big_doc_every: int           # every Nth document is a large log export
    big_doc_body_lines: int      # large log export length


PROFILES = {
    # Sized so the whole three-point sweep completes in single-digit minutes on
    # a 4-core container while still separating the quadratic stage from noise.
    "small": Profile("small", evidence=200, findings=60, recommendations=24,
                     statements=60, documents=40, doc_body_lines=60,
                     big_doc_every=20, big_doc_body_lines=2000),
    "medium": Profile("medium", evidence=2000, findings=600, recommendations=240,
                      statements=600, documents=200, doc_body_lines=120,
                      big_doc_every=20, big_doc_body_lines=6000),
    "large": Profile("large", evidence=10000, findings=3000, recommendations=1200,
                     statements=3000, documents=600, doc_body_lines=200,
                     big_doc_every=20, big_doc_body_lines=12000),
}


def _width(n: int) -> int:
    """Zero-pad ids to a fixed width per collection.

    Fixed width matters: it keeps ``E-7`` from being a prefix of ``E-70``, which
    is exactly the ambiguity the baseline statement check is blind to. The
    hostile test builds the ambiguous case on purpose.
    """
    return max(3, len(str(n)))


def _sentence(rng: random.Random) -> str:
    return f"{rng.choice(SUBJECTS).capitalize()} {rng.choice(VERBS)} the covered scenario"


INCOMPLETE_DIRECTORY = ".uiowa095-incomplete"


def _validate_generation(profile: Profile, seed: int) -> None:
    """Reject malformed workloads before reserving any filesystem path."""
    if not isinstance(profile, Profile):
        raise TypeError("profile must be a Profile instance")
    if not isinstance(profile.name, str) or not profile.name.strip():
        raise ValueError("profile.name must be a nonempty string")
    positive = ("evidence", "findings", "recommendations", "statements",
                "documents", "big_doc_every")
    nonnegative = ("doc_body_lines", "big_doc_body_lines")
    for field in positive + nonnegative:
        value = getattr(profile, field)
        minimum = 1 if field in positive else 0
        if type(value) is not int or value < minimum:
            raise ValueError(f"profile.{field} must be an integer >= {minimum}")
    if type(seed) is not int:
        raise TypeError("seed must be an integer (not bool)")


def generate(root: Path, profile: Profile, seed: int = 20260919) -> dict:
    """Write into a NEW destination, never replacing any existing object.

    An exclusive mkdir reserves the leaf. Existing empty directories, files,
    directory symlinks and dangling symlinks are all refused. A failed or
    interrupted run leaves its reserved directory and incomplete marker for
    inspection; use a different destination for another attempt. No cleanup
    recursively removes caller data. Success removes the empty marker and
    preserves the historical collection bytes and summary format.

    This is not an atomic publication or protection against an adversary
    replacing ancestor directories while the process is running.
    """
    _validate_generation(profile, seed)
    root = Path(root)
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise FileExistsError(
            f"refusing existing output: {root}; choose a new destination"
        ) from None
    marker = root / INCOMPLETE_DIRECTORY
    marker.mkdir()
    summary = _write_collection(root, profile, seed)
    marker.rmdir()
    return summary


def _write_collection(root: Path, profile: Profile, seed: int) -> dict:
    """Internal writer: caller has exclusively reserved a new directory."""
    rng = random.Random(seed)
    (root / "documents").mkdir()

    ew, fw, rw, sw, dw = (_width(profile.evidence), _width(profile.findings),
                          _width(profile.recommendations), _width(profile.statements),
                          _width(profile.documents))

    # One cell is deliberately starved so the rollup must emit UNKNOWN.
    starved_cell = (SERVICES[-1], AREAS[-1])
    cells = [(s, a) for s in SERVICES for a in AREAS if (s, a) != starved_cell]

    # ---- evidence -------------------------------------------------------
    evidence_rows = []
    for i in range(1, profile.evidence + 1):
        eid = f"E-{i:0{ew}d}"
        service, area = cells[i % len(cells)]
        evidence_rows.append({
            "evidence_id": eid,
            "service": service,
            "assessment_area": area,
            "source_type": rng.choice(SOURCE_TYPES),
            "source_name": f"Fictional {area.replace('_', ' ')} artifact {i}",
            "locator": f"section {1 + i % 9} / synthetic run {2026}-{1 + i % 12:02d}-{1 + i % 28:02d}",
            "observation": _sentence(rng),
            "evidence_state": EVIDENCE_STATES[i % len(EVIDENCE_STATES)],
            "synthetic": "true",
        })
    evidence_ids = [r["evidence_id"] for r in evidence_rows]

    # ---- findings -------------------------------------------------------
    finding_rows = []
    per = max(1, profile.evidence // max(1, profile.findings))
    for i in range(1, profile.findings + 1):
        fid = f"F-{i:0{fw}d}"
        start = ((i - 1) * per) % max(1, profile.evidence)
        cited = evidence_ids[start:start + 3] or evidence_ids[:3]
        finding_rows.append({
            "finding_id": fid,
            "service": SERVICES[i % len(SERVICES)],
            "assessment_area": AREAS[i % len(AREAS)],
            "statement": _sentence(rng),
            "evidence_ids": ";".join(cited),
            "confidence": ["supported", "partial", "UNKNOWN"][i % 3],
            "synthetic": "true",
        })
    finding_ids = [r["finding_id"] for r in finding_rows]

    # DEFECT 1+2: two findings cite evidence that was never collected. A broken
    # citation must surface as an error, never be quietly dropped.
    broken_link_ids = []
    for idx in (1, min(len(finding_rows), profile.findings // 2) - 1):
        if 0 <= idx < len(finding_rows):
            ghost = f"E-{profile.evidence + 900 + idx:0{ew}d}"
            finding_rows[idx]["evidence_ids"] += ";" + ghost
            broken_link_ids.append(finding_rows[idx]["finding_id"])

    # ---- recommendations ------------------------------------------------
    rec_rows = []
    for i in range(1, profile.recommendations + 1):
        rid = f"R-{i:0{rw}d}"
        start = ((i - 1) * 2) % max(1, profile.findings)
        rec_rows.append({
            "recommendation_id": rid,
            "linked_findings": ";".join(finding_ids[start:start + 2] or finding_ids[:2]),
            "horizon": ["0-90", "90-180", "180+"][i % 3],
            "effort_estimate": "UNKNOWN" if i % 7 == 0 else ["S", "M", "L"][i % 3],
            "synthetic": "true",
        })
    rec_ids = [r["recommendation_id"] for r in rec_rows]

    # ---- trace map + report text ---------------------------------------
    trace_rows = []
    for i in range(1, profile.statements + 1):
        sid = f"S-{i:0{sw}d}"
        fstart = ((i - 1) * 2) % max(1, profile.findings)
        rstart = (i - 1) % max(1, profile.recommendations)
        estart = ((i - 1) * 3) % max(1, profile.evidence)
        trace_rows.append({
            "statement_id": sid,
            "report_location": "final-report.md#findings" if i % 2 else "executive-summary.md#summary",
            "statement_summary": _sentence(rng),
            "recommendation_ids": rec_ids[rstart] if i % 3 else "",
            "finding_ids": ";".join(finding_ids[fstart:fstart + 2] or finding_ids[:1]),
            "evidence_ids": ";".join(evidence_ids[estart:estart + 3] or evidence_ids[:1]),
            "synthetic": "true",
        })

    # DEFECT 3+4: two statements are in the trace map but were never written
    # into the report. These are what the statement-presence stage exists to
    # catch, and they also force the optimized path through its fallback scan.
    absent_statements = {trace_rows[2]["statement_id"], trace_rows[-2]["statement_id"]} \
        if len(trace_rows) >= 4 else set()

    summary_lines = [
        "# Executive summary (SYNTHETIC)", "",
        SYNTHETIC_BANNER, "",
        "Fictional content for capacity benchmarking. Not University findings.", "",
    ]
    report_lines = [
        "# Final report (SYNTHETIC)", "",
        SYNTHETIC_BANNER, "",
        "Fictional content for capacity benchmarking. Not University findings.", "",
        "## Findings", "",
    ]
    for row in trace_rows:
        sid = row["statement_id"]
        if sid in absent_statements:
            continue
        para = (f"[{sid}] {row['statement_summary']}. This statement rests on "
                f"{row['finding_ids'] or 'UNKNOWN'} and on evidence "
                f"{row['evidence_ids'] or 'UNKNOWN'}. Recommendation linkage: "
                f"{row['recommendation_ids'] or 'none recorded'}.")
        (summary_lines if row["report_location"].startswith("executive") else report_lines).append(para)
        (summary_lines if row["report_location"].startswith("executive") else report_lines).append("")

    (root / "executive-summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    (root / "final-report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    # ---- evidence documents --------------------------------------------
    documents = []
    missing_doc_index = max(1, profile.documents // 3)
    for i in range(1, profile.documents + 1):
        did = f"D-{i:0{dw}d}"
        rel = f"documents/{did}.md"
        big = (i % profile.big_doc_every == 0)
        n_lines = profile.big_doc_body_lines if big else profile.doc_body_lines
        service, area = cells[i % len(cells)]
        documents.append({
            "source_id": did,
            "path": rel,
            "service": service,
            "assessment_area": area,
            "source_type": "log_export" if big else rng.choice(SOURCE_TYPES),
            "synthetic": True,
        })
        # DEFECT 5: this one is listed in the manifest and never written. A
        # manifest entry with no file behind it is an error, not a pass.
        if i == missing_doc_index:
            continue
        body = [
            SYNTHETIC_BANNER,
            f"# {did} -- fictional {('log export' if big else 'evidence document')} (SYNTHETIC)",
            "",
            f"service: {service}",
            f"assessment_area: {area}",
            "",
        ]
        for n in range(n_lines):
            body.append(f"{2026}-{1 + n % 12:02d}-{1 + n % 28:02d}T{n % 24:02d}:{n % 60:02d}:00Z "
                        f"seq={n:06d} {_sentence(rng)}.")
        (root / rel).write_text("\n".join(body) + "\n", encoding="utf-8")

    # ---- write tables ---------------------------------------------------
    def write_csv(name, rows, fields):
        with (root / name).open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    write_csv("evidence.csv", evidence_rows,
              ["evidence_id", "service", "assessment_area", "source_type",
               "source_name", "locator", "observation", "evidence_state", "synthetic"])
    write_csv("findings.csv", finding_rows,
              ["finding_id", "service", "assessment_area", "statement",
               "evidence_ids", "confidence", "synthetic"])
    write_csv("recommendations.csv", rec_rows,
              ["recommendation_id", "linked_findings", "horizon", "effort_estimate", "synthetic"])
    write_csv("trace-map.csv", trace_rows,
              ["statement_id", "report_location", "statement_summary",
               "recommendation_ids", "finding_ids", "evidence_ids", "synthetic"])

    manifest = {
        "schema": "uiowa-095-collection-v1",
        "synthetic": True,
        "disclaimer": "Fictional collection generated for capacity benchmarking. Not University data.",
        "profile": profile.name,
        "seed": seed,
        "services": SERVICES,
        "assessment_areas": AREAS,
        "report_files": ["executive-summary.md", "final-report.md"],
        "documents": documents,
        "seeded_defects": {
            "findings_with_unresolvable_evidence": sorted(broken_link_ids),
            "statements_absent_from_report": sorted(absent_statements),
            "documents_listed_but_absent": [f"D-{missing_doc_index:0{dw}d}"],
            "starved_coverage_cell": list(starved_cell),
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    total_bytes = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    doc_bytes = sum(p.stat().st_size for p in (root / "documents").iterdir() if p.is_file())
    largest_doc = max((p.stat().st_size for p in (root / "documents").iterdir() if p.is_file()), default=0)
    return {
        "profile": profile.name,
        "seed": seed,
        "evidence_rows": len(evidence_rows),
        "finding_rows": len(finding_rows),
        "recommendation_rows": len(rec_rows),
        "trace_rows": len(trace_rows),
        "documents_listed": len(documents),
        "documents_on_disk": sum(1 for p in (root / "documents").iterdir() if p.is_file()),
        "report_chars": len((root / "executive-summary.md").read_text(encoding="utf-8"))
                        + len((root / "final-report.md").read_text(encoding="utf-8")) + 1,
        "collection_bytes": total_bytes,
        "document_bytes": doc_bytes,
        "largest_document_bytes": largest_doc,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Generate a synthetic UIOWA-095 benchmark collection.")
    p.add_argument("--profile", choices=sorted(PROFILES), default="small")
    p.add_argument("--out", type=Path, required=True,
                   help="New destination; existing files, directories and symlinks are refused.")
    p.add_argument("--seed", type=int, default=20260919)
    a = p.parse_args(argv)
    try:
        summary = generate(a.out, PROFILES[a.profile], a.seed)
    except (OSError, ValueError, TypeError) as exc:
        p.error(f"{exc}; no successful collection reported. Any partial output is "
                "retained for inspection; retry at a new destination.")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
