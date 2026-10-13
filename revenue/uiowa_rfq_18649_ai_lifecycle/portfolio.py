#!/usr/bin/env python3
"""Batch offline lifecycle histories into an investigation queue and report bundle."""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

if __package__:
    from . import lifecycle
else:
    import lifecycle

INPUT_ERRORS = (OSError, ValueError, TypeError, RecursionError, OverflowError)
TASK_FIELDS = ("source", "workflow_id", "group", "provenance", "kind", "reference",
               "owner", "detail", "next_action")
COMPARISON_FIELDS = ("source", "workflow_id", "group", "provenance", "comparison_id",
                     "baseline_run", "candidate_run", "status", "metric", "paired",
                     "expected", "baseline_mean", "candidate_mean", "delta", "coverage",
                     "better_direction", "excluded_case_ids", "reason")
LIMITS = [
    "Coverage describes only the selected input files, not an organization's complete inventory.",
    "Leaf versions are all recorded branches with no child; none is inferred to be deployed.",
    "Workflow metrics are never pooled, ranked, or converted into an overall readiness score.",
    "Historical comparisons remain in the register; the queue uses leaf-version comparisons and unresolved incidents.",
    "Synthetic and caller-supplied observations retain their separate provenance on every workflow.",
    "No model, network, deployment, payment, or approval action is performed.",
]


def discover(inputs: Iterable[str], recursive: bool = False) -> tuple[list[Path], list[dict]]:
    """Expand requested directories only; overlapping path arguments count once."""
    paths, errors = {}, []
    for name in inputs:
        root = Path(name)
        try:
            if root.is_dir():
                found = sorted(root.rglob("*.json") if recursive else root.glob("*.json"))
                found = [p for p in found if p.is_file()]
                if not found:
                    raise ValueError("directory contains no matching JSON files")
            else:
                if not root.is_file():
                    raise ValueError("not a readable regular file or directory")
                found = [root]
            for path in found:
                key = str(path.resolve())
                if key not in paths or str(path) < str(paths[key]):
                    paths[key] = path
        except INPUT_ERRORS as exc:
            errors.append({"source": name, "status": "discovery_error", "error": str(exc)})
    return sorted(paths.values(), key=str), sorted(errors, key=lambda row: row["source"])


def workflow_entry(source: str, data: dict, report: dict) -> tuple[dict, list[dict]]:
    """Keep the analyzer's complete report; derive operational tasks, not new scores."""
    context = {"source": source, **{k: report[k] for k in ("workflow_id", "group", "provenance")}}
    tasks = []

    def task(kind: str, reference: str, owner: str | None, detail: str, action: str) -> None:
        tasks.append({**context, "kind": kind, "reference": reference, "owner": owner,
                      "detail": detail, "next_action": action})

    parent_ids = {v["parent_id"] for v in report["timeline"] if v["parent_id"] is not None}
    leaves = [v for v in report["timeline"] if v["version_id"] not in parent_ids]
    leaf_ids = {v["version_id"] for v in leaves}
    versions = {v["version_id"]: v for v in report["timeline"]}
    runs = {r["id"]: r for r in data["runs"]}
    unresolved = [e for e in report["events"] if e["incident_state"] in
                  {"open", "resolution_claim_without_evidence"}]
    for event in unresolved:
        task(event["incident_state"], "event:" + event["id"], event["owner"], event["summary"],
             "Record the investigation and its supporting evidence." if event["incident_state"] == "open"
             else "Attach supporting evidence to the recorded resolution; the incident remains unresolved.")
    for version in leaves:
        if version["reproduction_gaps"]:
            task("leaf_evidence_gaps", "version:" + version["version_id"], version["support_owner"],
                 "; ".join(version["reproduction_gaps"]),
                 "Collect the missing version metadata or record why it is unavailable.")
        if not version["run_ids"]:
            task("leaf_without_runs", "version:" + version["version_id"], version["support_owner"],
                 "No evaluation run is recorded for this branch.",
                 "Identify the intended branch and record any available evaluation results.")
    # An earlier failed run may have been repaired. Only the latest finished run(s)
    # on each leaf enter the queue; retain all ties rather than guessing a winner.
    recent_run_ids = set()
    for version in leaves:
        candidates = [runs[ident] for ident in version["run_ids"]]
        if candidates:
            latest = max(lifecycle.timestamp(r["finished_at"]) for r in candidates)
            recent_run_ids.update(r["id"] for r in candidates
                                  if lifecycle.timestamp(r["finished_at"]) == latest)
    for run in report["runs"]:
        if run["run_id"] not in recent_run_ids:
            continue
        problems = []
        if run["error_case_ids"]:
            problems.append("execution errors: " + ", ".join(run["error_case_ids"]))
        if run["missing_case_ids"]:
            problems.append("cases not observed: " + ", ".join(run["missing_case_ids"]))
        unknown = [f"{name} {m['known']}/{m['expected']} known"
                   for name, m in run["metrics"].items() if m["missing"]]
        problems.extend(unknown)
        if problems:
            task("latest_run_incomplete", "run:" + run["run_id"],
                 versions[run["version_id"]]["support_owner"], "; ".join(problems),
                 "Inspect the recorded error or missing observation; unknown values are not zero.")
    for comparison in report["comparisons"]:
        candidate = runs[comparison["candidate_run"]]
        if candidate["version_id"] not in leaf_ids:
            continue
        owner = versions[candidate["version_id"]]["support_owner"]
        reference = "comparison:" + comparison["id"]
        if comparison["status"] == "incomparable":
            task("incomparable_leaf_comparison", reference, owner, "; ".join(comparison["reasons"]),
                 "Reconcile evaluation definitions and retained inputs before interpreting a delta.")
            continue
        incomplete, worse = [], []
        for name, metric in comparison["metrics"].items():
            scope = f"{name}: {metric['paired']}/{metric['expected']} paired"
            if metric["coverage"] != "complete":
                incomplete.append(scope)
            delta = metric["delta"]
            if delta is not None and (delta > 0 if metric["better_direction"] == "lower" else delta < 0):
                worse.append(f"{scope}, delta {delta} ({metric['better_direction']} is better)")
        if incomplete:
            task("partial_leaf_comparison", reference, owner, "; ".join(incomplete),
                 "Keep the stated paired subset; investigate excluded cases before generalizing.")
        if worse:
            task("observed_leaf_regression", reference, owner, "; ".join(worse),
                 "Investigate the recorded association; this is not a causal or production claim.")
    for replay in report["replays"]:
        if replay["version_id"] in leaf_ids and replay["status"] != "exact_on_recorded_cases":
            task("leaf_replay_" + replay["status"], "replay:" + replay["id"],
                 versions[replay["version_id"]]["support_owner"],
                 f"{replay['content_verified']}/{replay['expected']} cases have retained comparison bytes; "
                 f"mismatches: {', '.join(replay['mismatch_case_ids']) or 'none recorded'}",
                 "Inspect the recorded outputs and missing bytes; no future replay guarantee is inferred.")
    entry = {**context, "leaf_versions": [{k: v[k] for k in
             ("version_id", "changed_at", "support_owner", "reproduction_gaps")} for v in leaves],
             "latest_leaf_run_ids": sorted(recent_run_ids), "unresolved_incidents": len(unresolved),
             "run_count": len(report["runs"]), "comparison_count": len(report["comparisons"]),
             "incomparable_count": sum(c["status"] == "incomparable" for c in report["comparisons"]),
             "task_count": len(tasks), "report": report}
    return entry, tasks


def build_portfolio(inputs: Iterable[str], recursive: bool = False) -> dict[str, Any]:
    paths, diagnostics = discover(inputs, recursive)
    input_rows, candidates = [], defaultdict(list)
    for path in paths:
        row = {"source": str(path), "status": "included"}
        input_rows.append(row)
        try:
            data = lifecycle.load(path.read_text(encoding="utf-8"))
            report = lifecycle.analyze(data)
            row.update({k: report[k] for k in ("workflow_id", "group", "provenance")})
            candidates[report["workflow_id"]].append((row, data, report))
        except INPUT_ERRORS as exc:
            row.update(status="invalid_input", error=str(exc))
    workflows, queue = [], []
    for workflow_id, entries in sorted(candidates.items()):
        if len(entries) > 1:
            sources = sorted(entry[0]["source"] for entry in entries)
            for row, _, _ in entries:
                row.update(status="duplicate_workflow", conflicting_sources=sources,
                           error=f"Workflow {workflow_id} occurs in multiple files; no snapshot was selected.")
            continue
        row, data, report = entries[0]
        entry, tasks = workflow_entry(row["source"], data, report)
        workflows.append(entry)
        queue.extend(tasks)
    input_rows = sorted(input_rows + diagnostics, key=lambda row: row["source"])
    for row in input_rows:
        if row["status"] != "included":
            queue.append({"source": row["source"], "workflow_id": row.get("workflow_id"),
                          "group": row.get("group"), "provenance": row.get("provenance"),
                          "kind": row["status"], "reference": "input", "owner": None,
                          "detail": row["error"], "next_action":
                          "Select one intended snapshot for this workflow and rerun." if row["status"] == "duplicate_workflow"
                          else "Correct the input path or metadata and rerun; other valid workflows are retained."})
    priority = {"discovery_error": 0, "invalid_input": 0, "duplicate_workflow": 0,
                "open": 1, "resolution_claim_without_evidence": 1}
    queue.sort(key=lambda row: (priority.get(row["kind"], 2), row["workflow_id"] or "",
                               row["kind"], row["reference"], row["source"]))
    excluded = sum(row["status"] != "included" for row in input_rows)
    return {"schema": "commons-ai-lifecycle-portfolio/v1", "authority": "DRAFT_ANALYSIS_ONLY",
            "complete": excluded == 0, "inputs": input_rows,
            "summary": {"discovered_files": len(paths), "input_errors": excluded,
                        "workflows_included": len(workflows), "investigation_tasks": len(queue),
                        "groups": dict(sorted(Counter(w["group"] for w in workflows).items())),
                        "provenance": dict(sorted(Counter(w["provenance"] for w in workflows).items()))},
            "workflows": workflows, "investigation_queue": queue, "limits": LIMITS}


def csv_text(fields: tuple[str, ...], rows: Iterable[dict]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(fields)
    for row in rows:
        cells = [row.get(field) for field in fields]
        writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@"))
                         else v for v in cells])
    return output.getvalue()


def comparison_rows(portfolio: dict) -> Iterable[dict]:
    for workflow in portfolio["workflows"]:
        for c in workflow["report"]["comparisons"]:
            context = {k: workflow[k] for k in ("source", "workflow_id", "group", "provenance")}
            context.update(comparison_id=c["id"], baseline_run=c["baseline_run"],
                           candidate_run=c["candidate_run"], status=c["status"], reason="; ".join(c["reasons"]))
            for name, metric in (c["metrics"].items() or [("", {})]):
                yield {**context, **metric, "metric": name,
                       "excluded_case_ids": "; ".join(metric.get("excluded_case_ids", []))}


def markdown(portfolio: dict) -> str:
    def esc(value: Any) -> str:
        text = "UNKNOWN" if value is None else str(value)
        text = html.escape(text).replace("\r", " ").replace("\n", " ")
        for char in ("\\", "`", "[", "]", "*", "_", "|"):
            text = text.replace(char, "\\" + char)
        return text

    summary = portfolio["summary"]
    lines = ["# AI lifecycle portfolio", "", "**DRAFT ANALYSIS ONLY**", "",
             f"Included workflows: {summary['workflows_included']}; input errors: {summary['input_errors']}; "
             f"investigation tasks: {summary['investigation_tasks']}.",
             "Input coverage: " + ("complete for selected inputs." if portfolio["complete"] else "PARTIAL; excluded inputs are listed below."),
             "", "## Workflow inventory", "",
             "| Workflow | Group | Provenance | Recorded leaf branches | Runs | Unresolved incidents | Tasks |",
             "|---|---|---|---|---:|---:|---:|"]
    for w in portfolio["workflows"]:
        cells = [w["workflow_id"], w["group"], w["provenance"],
                 ", ".join(v["version_id"] for v in w["leaf_versions"]),
                 w["run_count"], w["unresolved_incidents"], w["task_count"]]
        lines.append("| " + " | ".join(esc(v) for v in cells) + " |")
    lines += ["", "## Investigation queue", "",
              "| Workflow / source | Kind / reference | Recorded owner | Detail | Next action |",
              "|---|---|---|---|---|"]
    for task in portfolio["investigation_queue"]:
        cells = [f"{task['workflow_id'] or 'UNKNOWN'} / {task['source']}",
                 f"{task['kind']} / {task['reference']}", task["owner"], task["detail"], task["next_action"]]
        lines.append("| " + " | ".join(esc(v) for v in cells) + " |")
    lines += ["", "Full per-workflow reports are retained in JSON. Use the comparisons-csv format for "
              "the complete historical register with each metric's own paired denominator.", "", "## Input diagnostics", "",
              "| Source | State | Explanation |", "|---|---|---|"]
    for row in portfolio["inputs"]:
        lines.append("| " + " | ".join(esc(row.get(k, "")) for k in ("source", "status", "error")) + " |")
    lines += ["", "## Limits", ""] + ["- " + text for text in portfolio["limits"]]
    return "\n".join(lines) + "\n"


def render(portfolio: dict, format_name: str) -> str:
    if format_name == "markdown":
        return markdown(portfolio)
    if format_name == "csv":
        return csv_text(TASK_FIELDS, portfolio["investigation_queue"])
    if format_name == "comparisons-csv":
        return csv_text(COMPARISON_FIELDS, comparison_rows(portfolio))
    return json.dumps(portfolio, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="history JSON files or directories of history JSON files")
    parser.add_argument("--recursive", action="store_true", help="include nested JSON files in selected directories")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--format", choices=("json", "markdown", "csv", "comparisons-csv"), default="json")
    output.add_argument("--output-dir", type=Path, help="create a new directory containing all four reports")
    args = parser.parse_args(argv)
    try:
        portfolio = build_portfolio(args.inputs, args.recursive)
        if args.output_dir:
            # Render before creating outputs. Existing directories are never overwritten.
            bundle = {"portfolio.json": render(portfolio, "json"), "overview.md": render(portfolio, "markdown"),
                      "investigation_queue.csv": render(portfolio, "csv"),
                      "comparisons.csv": render(portfolio, "comparisons-csv")}
            args.output_dir.mkdir(parents=True, exist_ok=False)
            for name, text in bundle.items():
                with (args.output_dir / name).open("x", encoding="utf-8", newline="") as stream:
                    stream.write(text)
            print(json.dumps({"output_dir": str(args.output_dir), "complete": portfolio["complete"], **portfolio["summary"]}))
        else:
            sys.stdout.write(render(portfolio, args.format))
        for row in portfolio["inputs"]:
            if row["status"] != "included":
                print(f"INPUT_ERROR [{row['source']}]: {row['error']}", file=sys.stderr)
        return 0 if portfolio["complete"] else 2
    except INPUT_ERRORS as exc:
        print(f"PORTFOLIO_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
