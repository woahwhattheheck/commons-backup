#!/usr/bin/env python3
"""UIOWA-095 -- the evidence-and-report preparation workflow, under measurement.

This module is the *subject* of the benchmark, not the harness. It runs the
same five stages an analyst runs when turning a collected evidence set into a
report bundle:

    import -> link check -> statement presence -> document label scan
           -> coverage rollup -> export

Two of those stages ship in two implementations, selected by ``mode``:

    mode="baseline"   the algorithm as it appears in the delivered lane tools
    mode="optimized"  the repaired algorithm

Both modes MUST return an identical ``WorkflowResult.canonical()``. That is
asserted in ``test_capacity_benchmark.py`` at every workload size, because a
faster wrong answer is not an improvement.

Where the baseline came from (these are real shipped files, not strawmen):

  B1  revenue/uiowa_rfq_18649_traceability_rehearsal/validate_trace.py
      builds one concatenated report string, then runs
      ``for sid in sids: if sid not in report``. Each test is a full substring
      scan of the whole report. The report grows *with* the statement count,
      so characters scanned grow as O(statements x report_length) -- quadratic
      in the size of the engagement.

  B2  revenue/uiowa_rfq_18649_synthetic_collection/validate_collection.py
      checks for a SYNTHETIC label near the top of each evidence document with
      ``path.read_text(encoding="utf-8")[:500]``. That pulls every byte of
      every document into memory to look at 500 characters of it. Cost and
      peak memory are driven by total collection bytes and by the single
      largest document, neither of which the check actually needs.

Neither of those lanes is edited by this lane. This lane ships the repaired
implementation plus the measurement; the fix is reported, not reached across
lane boundaries and applied.

Python 3 standard library only. No network. No writes outside the output dir
passed to ``export_bundle``.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

MODES = ("baseline", "optimized")

# Characters an identifier may contain. Used by the optimized statement scan;
# the equivalence argument below depends on this being a superset of every
# character appearing in an id.
_ID_CHARS = re.compile(r"[A-Za-z0-9_-]+")

# How much of a document the SYNTHETIC label check is allowed to look at. This
# is the window the delivered check already uses -- `read_text()[:500]` -- kept
# identical so the optimized read returns the same decision.
LABEL_WINDOW_CHARS = 500


class WorkflowError(RuntimeError):
    """Raised when the collection cannot be read at all."""


# --------------------------------------------------------------------------
# stage 1: import
# --------------------------------------------------------------------------

@dataclass
class Collection:
    """Everything read off disk, before any checking happens."""

    evidence: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    report_text: str = ""
    services: list = field(default_factory=list)
    areas: list = field(default_factory=list)

    def row_count(self) -> int:
        return (
            len(self.evidence)
            + len(self.findings)
            + len(self.recommendations)
            + len(self.trace)
        )


def _read_csv(path: Path) -> list:
    if not path.exists():
        raise WorkflowError(f"required input is missing: {path.name}")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def split_ids(value) -> set:
    """Split a ';' or ',' separated id cell. Empty cell -> empty set.

    An empty cell means 'no links declared', which is a different thing from a
    broken link, and it is NOT an error here. Callers decide.
    """
    return {x.strip() for x in (value or "").replace(",", ";").split(";") if x.strip()}


def import_collection(root: Path) -> Collection:
    """Stage 1. Read the collection off disk.

    Identical in both modes -- this stage is measured to show what import
    actually costs relative to the stages that were repaired, so the report can
    say which stages are hot and which merely felt hot.
    """
    root = Path(root)
    incomplete = root / ".uiowa095-incomplete"
    if incomplete.exists() or incomplete.is_symlink():
        raise WorkflowError(
            "collection generation is incomplete: .uiowa095-incomplete is present; "
            "generate a new collection and observe a successful exit before consumption"
        )
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise WorkflowError("required input is missing: manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    col = Collection(
        evidence=_read_csv(root / "evidence.csv"),
        findings=_read_csv(root / "findings.csv"),
        recommendations=_read_csv(root / "recommendations.csv"),
        trace=_read_csv(root / "trace-map.csv"),
        documents=manifest.get("documents", []),
        services=list(manifest.get("services", [])),
        areas=list(manifest.get("assessment_areas", [])),
    )

    # The delivered tool concatenates every report surface into one string and
    # searches that. Kept, because it is the input the statement check is
    # measured against.
    parts = []
    for name in manifest.get("report_files", []):
        p = root / name
        if not p.exists():
            raise WorkflowError(f"report surface listed in manifest is missing: {name}")
        parts.append(p.read_text(encoding="utf-8"))
    col.report_text = "\n".join(parts)
    return col


# --------------------------------------------------------------------------
# stage 2: referential integrity
# --------------------------------------------------------------------------

def check_links(col: Collection) -> list:
    """Stage 2. Every declared link resolves to a row that exists.

    Set containment, same in both modes. Included in the measurement so the
    report can state -- from data, not from intuition -- that this stage is not
    where the time goes.
    """
    eids = {r["evidence_id"] for r in col.evidence}
    fids = {r["finding_id"] for r in col.findings}
    rids = {r["recommendation_id"] for r in col.recommendations}
    errors = []

    for row in col.findings:
        missing = split_ids(row.get("evidence_ids")) - eids
        for m in sorted(missing):
            errors.append(f"{row['finding_id']}: evidence link does not resolve: {m}")
    for row in col.recommendations:
        missing = split_ids(row.get("linked_findings")) - fids
        for m in sorted(missing):
            errors.append(f"{row['recommendation_id']}: finding link does not resolve: {m}")
    for row in col.trace:
        sid = row["statement_id"]
        for m in sorted(split_ids(row.get("finding_ids")) - fids):
            errors.append(f"{sid}: finding link does not resolve: {m}")
        for m in sorted(split_ids(row.get("recommendation_ids")) - rids):
            errors.append(f"{sid}: recommendation link does not resolve: {m}")
        for m in sorted(split_ids(row.get("evidence_ids")) - eids):
            errors.append(f"{sid}: evidence link does not resolve: {m}")
    return errors


# --------------------------------------------------------------------------
# stage 3: statement presence  -- BOTTLENECK B1
# --------------------------------------------------------------------------

def statements_absent_baseline(statement_ids, report_text: str) -> list:
    """The delivered algorithm. One full substring scan of the report per id.

    Characters scanned = len(statement_ids) * len(report_text). Because the
    report is written *from* the statements, len(report_text) grows with
    len(statement_ids) -- so this is quadratic in engagement size.
    """
    absent = []
    for sid in sorted(statement_ids):
        if sid not in report_text:
            absent.append(sid)
    return absent


def statements_absent_optimized(statement_ids, report_text: str) -> list:
    """Same answer, one pass.

    Split the report once into its maximal runs of id-legal characters and keep
    the distinct runs in a set. An id that equals one of those runs is
    unambiguously present, so it is resolved by a hash lookup instead of a scan.

    Equivalence to the baseline is exact, by construction, not by assumption:
    a run-equal id is a literal substring of the report, so no false 'present'
    is possible; and any id NOT resolved that way is still put through the
    original ``sid in report_text`` scan, so no false 'absent' is possible
    either. That fallback is what makes the optimized path safe when an id is
    embedded inside a longer token (``S-001`` inside ``S-0012``) -- a case the
    hostile test exercises directly.

    Cost is O(len(report_text)) plus O(absent_count * len(report_text)). On a
    healthy bundle absent_count is ~0 and the stage is linear. On a bundle
    where every statement is missing it degrades to the baseline cost, which is
    the correct behaviour and is stated rather than hidden.

    ``finditer`` plus the length filter, rather than the more obvious
    ``set(_ID_CHARS.findall(report_text))``. The first version of this function
    used findall, and the benchmark caught it handing the time win straight back
    as a memory regression: findall materialises every run in the report as a
    list before the set is built, so peak allocation tracked report size, and
    whole-workflow peak at the large size went ABOVE the baseline. A
    timing-only benchmark would have shipped it.

    Both shapes are still measured on every run -- see "Why the shipped repair
    is not the obvious one" in results/BENCHMARK_REPORT.md, rendered from
    benchmark.measure_statement_variants(). Numbers are deliberately not
    repeated here: a figure pasted into a docstring goes stale the next time
    anyone touches the machine, and the generated table cannot.

    Filtering on the lengths the ids actually have is what keeps the retained
    set small. Those lengths are read off the input rather than hardcoded, and
    the fallback scan below means a filtered-out run can never produce a wrong
    answer -- the filter can only cost time, never correctness.
    """
    id_lengths = {len(s) for s in statement_ids}
    present_runs = set()
    for match in _ID_CHARS.finditer(report_text):
        run = match.group()
        if len(run) in id_lengths:
            present_runs.add(run)

    absent = []
    for sid in sorted(statement_ids):
        if sid in present_runs:
            continue
        if sid not in report_text:
            absent.append(sid)
    return absent


def check_statement_presence(col: Collection, mode: str) -> list:
    """Stage 3. Every trace statement id is actually findable in the report."""
    ids = {r["statement_id"] for r in col.trace}
    fn = statements_absent_baseline if mode == "baseline" else statements_absent_optimized
    return [f"{sid}: statement id is absent from the report text" for sid in fn(ids, col.report_text)]


# --------------------------------------------------------------------------
# stage 4: document label scan  -- BOTTLENECK B2
# --------------------------------------------------------------------------

def _label_ok(head: str) -> bool:
    return "SYNTHETIC" in head.upper()


def read_label_window_baseline(path: Path) -> str:
    """The delivered algorithm: whole file into memory, then slice 500 chars."""
    return path.read_text(encoding="utf-8")[:LABEL_WINDOW_CHARS]


def read_label_window_optimized(path: Path) -> str:
    """Retain the same 500 characters and validate UTF-8 through end of file.

    Both modes must reject malformed text even beyond the label window. Read
    fixed-size character chunks, not lines or the whole remainder, so a large
    document (including a single long line) does not become a large allocation.
    TextIOWrapper preserves the baseline's character and newline semantics.
    Full-stream validation costs O(file size) I/O; historical prefix-only
    timings do not measure this implementation.
    """
    with path.open("r", encoding="utf-8") as fh:
        head = fh.read(LABEL_WINDOW_CHARS)
        while fh.read(64 * 1024):
            pass
        return head


def check_document_labels(root: Path, col: Collection, mode: str) -> list:
    """Stage 4. Every evidence document carries its SYNTHETIC label up top.

    A document listed in the manifest but absent on disk is an error, never a
    silent pass -- missing evidence stays missing.
    """
    root = Path(root)
    read = read_label_window_baseline if mode == "baseline" else read_label_window_optimized
    errors = []
    for doc in col.documents:
        rel = str(doc.get("path", ""))
        path = root / rel
        if not path.exists():
            errors.append(f"{doc.get('source_id')}: document listed in manifest is missing on disk: {rel}")
            continue
        try:
            head = read(path)
        except UnicodeError as exc:
            raise WorkflowError(f"document is not valid UTF-8: {rel}: {exc}") from exc
        if not _label_ok(head):
            errors.append(f"{doc.get('source_id')}: no SYNTHETIC label in the first {LABEL_WINDOW_CHARS} characters")
    return errors


# --------------------------------------------------------------------------
# stage 5: coverage rollup
# --------------------------------------------------------------------------

def rollup_coverage(col: Collection) -> list:
    """Stage 5. Evidence counts per (service x assessment area) cell.

    A cell with no evidence is reported as state ``UNKNOWN``. It is not a zero
    and it is not a pass. An unexamined cell and an examined-and-empty cell are
    not the same claim, and this workflow never collapses the first into the
    second.
    """
    counts = defaultdict(lambda: {"strength": 0, "gap": 0, "unknown": 0, "total": 0})
    for row in col.evidence:
        key = (row.get("service"), row.get("assessment_area"))
        state = row.get("evidence_state")
        bucket = counts[key]
        bucket["total"] += 1
        if state in bucket:
            bucket[state] += 1
        else:
            bucket["unknown"] += 1

    rows = []
    for service in col.services:
        for area in col.areas:
            c = counts.get((service, area))
            if c is None:
                rows.append({
                    "service": service, "assessment_area": area,
                    "evidence_count": "UNKNOWN", "strength_count": "UNKNOWN",
                    "gap_count": "UNKNOWN", "unknown_count": "UNKNOWN",
                    "cell_state": "UNKNOWN",
                })
                continue
            rows.append({
                "service": service, "assessment_area": area,
                "evidence_count": c["total"], "strength_count": c["strength"],
                "gap_count": c["gap"], "unknown_count": c["unknown"],
                "cell_state": "covered",
            })
    return rows


# --------------------------------------------------------------------------
# driver + export
# --------------------------------------------------------------------------

@dataclass
class WorkflowResult:
    mode: str
    rows_in: int
    documents_in: int
    report_chars: int
    link_errors: list
    statement_errors: list
    document_errors: list
    coverage: list

    def all_errors(self) -> list:
        return self.link_errors + self.statement_errors + self.document_errors

    def unknown_cells(self) -> int:
        return sum(1 for r in self.coverage if r["cell_state"] == "UNKNOWN")

    def analyst_followups(self) -> int:
        """Items this run hands back to a human.

        This is a count of what the run produced -- validation errors plus
        UNKNOWN coverage cells -- not an estimate of how long a human takes.
        Effort per item is UNKNOWN and is not modelled here.
        """
        return len(self.all_errors()) + self.unknown_cells()

    def canonical(self) -> dict:
        """Mode-independent view, for asserting baseline == optimized."""
        return {
            "rows_in": self.rows_in,
            "documents_in": self.documents_in,
            "report_chars": self.report_chars,
            "link_errors": self.link_errors,
            "statement_errors": self.statement_errors,
            "document_errors": self.document_errors,
            "coverage": self.coverage,
            "analyst_followups": self.analyst_followups(),
        }


def run_workflow(root, mode: str = "optimized") -> WorkflowResult:
    """Run every stage end to end."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
    root = Path(root)
    col = import_collection(root)
    return WorkflowResult(
        mode=mode,
        rows_in=col.row_count(),
        documents_in=len(col.documents),
        report_chars=len(col.report_text),
        link_errors=check_links(col),
        statement_errors=check_statement_presence(col, mode),
        document_errors=check_document_labels(root, col, mode),
        coverage=rollup_coverage(col),
    )


def export_bundle(result: WorkflowResult, out) -> dict:
    """Write the analyst-facing outputs. Deterministic: same input, same bytes.

    Returns the byte size of each written file so the benchmark can report
    export volume rather than guess at it.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = {}

    buf = io.StringIO()
    fields = ["service", "assessment_area", "evidence_count", "strength_count",
              "gap_count", "unknown_count", "cell_state"]
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(result.coverage)
    coverage_csv = buf.getvalue()
    (out / "coverage-matrix.csv").write_text(coverage_csv, encoding="utf-8")
    written["coverage-matrix.csv"] = len(coverage_csv.encode("utf-8"))

    bundle = {
        "schema": "uiowa-095-workflow-result-v1",
        "synthetic": True,
        "rows_in": result.rows_in,
        "documents_in": result.documents_in,
        "report_chars": result.report_chars,
        "link_errors": result.link_errors,
        "statement_errors": result.statement_errors,
        "document_errors": result.document_errors,
        "unknown_coverage_cells": result.unknown_cells(),
        "analyst_followups": result.analyst_followups(),
        "coverage": result.coverage,
    }
    payload = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
    (out / "workflow-result.json").write_text(payload, encoding="utf-8")
    written["workflow-result.json"] = len(payload.encode("utf-8"))

    lines = [
        "# UIOWA-095 workflow result (SYNTHETIC)",
        "",
        "Generated from a synthetic collection. No University data.",
        "",
        f"- Rows imported: {result.rows_in}",
        f"- Documents scanned: {result.documents_in}",
        f"- Report characters searched: {result.report_chars}",
        f"- Link errors: {len(result.link_errors)}",
        f"- Statement-presence errors: {len(result.statement_errors)}",
        f"- Document-label errors: {len(result.document_errors)}",
        f"- Coverage cells with no evidence (UNKNOWN, not zero): {result.unknown_cells()}",
        f"- Items returned to an analyst: {result.analyst_followups()}",
        "",
    ]
    md = "\n".join(lines)
    (out / "workflow-report.md").write_text(md, encoding="utf-8")
    written["workflow-report.md"] = len(md.encode("utf-8"))
    return written


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Run the UIOWA-095 preparation workflow once.")
    p.add_argument("collection", type=Path)
    p.add_argument("--mode", choices=MODES, default="optimized")
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args(argv)

    try:
        result = run_workflow(a.collection, mode=a.mode)
        if a.out:
            export_bundle(result, a.out)
    except (WorkflowError, OSError, UnicodeError, ValueError, csv.Error) as exc:
        print(f"workflow: {exc}", file=sys.stderr)
        return 2
    print(f"mode={result.mode} rows={result.rows_in} documents={result.documents_in} "
          f"report_chars={result.report_chars}")
    print(f"errors: link={len(result.link_errors)} statement={len(result.statement_errors)} "
          f"document={len(result.document_errors)}")
    print(f"UNKNOWN coverage cells={result.unknown_cells()} analyst_followups={result.analyst_followups()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
