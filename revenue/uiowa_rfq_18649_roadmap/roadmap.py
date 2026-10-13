#!/usr/bin/env python3
"""Offline, non-authoritative recommendation-to-roadmap planning (Python 3.10+)."""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import html
import importlib.util
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PHASES = {"0-90": (0, 90), "90-180": (90, 180), "180+": (180, None)}
GROUPS = {"ESS", "RIS", "IAM", "DEPARTMENT"}
FIELDS = ("id", "title", "group", "phase", "owner_role", "depends_on",
          "duration_days", "finding_refs", "evidence_refs", "practice_change",
          "observable_outcome", "assumptions")
LISTS = ("depends_on", "finding_refs", "evidence_refs", "assumptions")
META = ("document_title", "synthetic", "document_assumptions")
DERIVED = ("start_min", "start_max", "finish_min", "finish_max", "layer",
           "status", "phase_state", "issues")
STATE = "DRAFT_NON_AUTHORITATIVE"
NOTICE = ("Relative calendar-day planning only; not appointments or commitments. "
          "Duration bounds are assumptions, not probabilities. Parallel layers show "
          "dependency independence, not available staffing. Capacity and maturity "
          "progression must be validated by the assessment team.")


class PlanError(ValueError):
    """Invalid interchange or planning data; no plausible defaults are invented."""


def strict_loads(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PlanError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value):
        raise PlanError(f"non-finite JSON number: {value}")
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except json.JSONDecodeError as exc:
        raise PlanError(str(exc)) from exc


def text_ok(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(document: Any) -> dict:
    required = {"schema_version", "title", "synthetic", "assumptions", "recommendations"}
    if not isinstance(document, dict) or set(document) != required:
        raise PlanError("document keys must be " + ", ".join(sorted(required)))
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise PlanError("schema_version must be integer 1")
    if not text_ok(document["title"]) or type(document["synthetic"]) is not bool:
        raise PlanError("title must be nonempty; synthetic must be a boolean")
    if not isinstance(document["assumptions"], list) or not all(map(text_ok, document["assumptions"])):
        raise PlanError("document assumptions must be a list of nonempty strings")
    rows = document["recommendations"]
    if not isinstance(rows, list) or not rows:
        raise PlanError("recommendations must be a nonempty list")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            raise PlanError("recommendation keys must be " + ", ".join(FIELDS))
        key = row["id"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", key):
            raise PlanError("id must be an alphanumeric identifier with . _ or -")
        if key in seen:
            raise PlanError(f"duplicate recommendation id: {key}")
        seen.add(key)
        for field in ("title", "practice_change", "observable_outcome"):
            if not text_ok(row[field]):
                raise PlanError(f"{key}: {field} must be nonempty text")
        if not isinstance(row["group"], str) or row["group"] not in GROUPS:
            raise PlanError(f"{key}: unknown group")
        if not isinstance(row["phase"], str) or row["phase"] not in PHASES:
            raise PlanError(f"{key}: unknown phase")
        if row["owner_role"] is not None and not text_ok(row["owner_role"]):
            raise PlanError(f"{key}: owner_role must be text or null")
        for field in LISTS:
            values = row[field]
            if not isinstance(values, list) or not all(map(text_ok, values)):
                raise PlanError(f"{key}: {field} must be a list of nonempty strings")
            if len(set(values)) != len(values):
                raise PlanError(f"{key}: duplicate values in {field}")
        duration = row["duration_days"]
        if duration is not None and (not isinstance(duration, list) or len(duration) != 2
                or any(type(x) is not int or x < 0 for x in duration)
                or duration[0] > duration[1]):
            raise PlanError(f"{key}: duration_days must be null or [nonnegative min, max] calendar days")
    return document


def canonical(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def plan(document: dict) -> dict:
    """Propagate both duration bounds over a DAG; preserve unresolved work."""
    validate(document)
    rows = {row["id"]: row for row in document["recommendations"]}
    children, indegree = defaultdict(list), {}
    for key, row in rows.items():
        known = [dep for dep in row["depends_on"] if dep in rows]
        indegree[key] = len(known)
        for dep in known:
            children[dep].append(key)
    ready = [key for key, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    results = {}
    while ready:
        key = heapq.heappop(ready)
        row = rows[key]
        missing = sorted(set(row["depends_on"]) - rows.keys())
        predecessors = [results[dep] for dep in row["depends_on"] if dep in results]
        issues = [f"missing_prerequisite:{dep}" for dep in missing]
        if row["owner_role"] is None:
            issues.append("owner_role_unknown")
        for field in ("finding_refs", "evidence_refs", "assumptions"):
            if not row[field]:
                issues.append(f"{field}_missing")
        layer = max((p["layer"] for p in predecessors), default=-1) + 1
        out = dict(row, start_min=None, start_max=None, finish_min=None,
                   finish_max=None, layer=layer, status="PLANNED", phase_state="UNKNOWN")
        blocked = [p["id"] for p in predecessors if p["finish_max"] is None]
        if row["duration_days"] is None:
            issues.append("duration_unknown")
        if missing:
            out["status"] = "MISSING_PREREQUISITE"
        elif blocked:
            out["status"] = "BLOCKED_BY_UNSCHEDULED_PREREQUISITE"
            issues.extend(f"unscheduled_prerequisite:{dep}" for dep in sorted(blocked))
        elif row["duration_days"] is None:
            out["status"] = "MISSING_DURATION"
        else:
            lower, upper = PHASES[row["phase"]]
            start_min = max([lower] + [p["finish_min"] for p in predecessors])
            start_max = max([lower] + [p["finish_max"] for p in predecessors])
            out.update(start_min=start_min, start_max=start_max,
                       finish_min=start_min + row["duration_days"][0],
                       finish_max=start_max + row["duration_days"][1])
            out["phase_state"] = ("OUTSIDE_PHASE" if upper is not None and start_min >= upper
                                  else "AT_RISK" if upper is not None and start_max >= upper
                                  else "ON_PHASE")
            if out["phase_state"] != "ON_PHASE":
                issues.append("requested_start_phase_" + out["phase_state"].lower())
            if upper is not None and out["finish_max"] > upper:
                issues.append("work_may_span_phase_boundary")
        out["issues"] = issues
        results[key] = out
        for child in children[key]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    # Kahn's remainder includes cycle members AND downstream dependents; do not
    # falsely assert that every remaining node itself belongs to a cycle.
    for key in sorted(rows.keys() - results.keys()):
        results[key] = dict(rows[key], start_min=None, start_max=None, finish_min=None,
                            finish_max=None, layer=None, status="CYCLE_OR_BLOCKED_BY_CYCLE",
                            phase_state="UNKNOWN", issues=["resolve_dependency_cycle"])
    ordered = [results[key] for key in sorted(results)]
    layers = defaultdict(list)
    for item in ordered:
        if item["status"] == "PLANNED":
            layers[item["layer"]].append(item["id"])
    return {"schema_version": 1, "planning_state": STATE, "synthetic": document["synthetic"],
            "title": document["title"], "notice": NOTICE, "capacity_validation": "NOT_PERFORMED",
            "input_sha256": hashlib.sha256(canonical(document)).hexdigest(),
            "assumptions": document["assumptions"], "recommendations": ordered,
            "dependency_layers": [layers[n] for n in sorted(layers)],
            "summary": {"total": len(ordered),
                        "planned": sum(r["status"] == "PLANNED" for r in ordered),
                        "unscheduled": sum(r["status"] != "PLANNED" for r in ordered),
                        "phase_at_risk": sum(r["phase_state"] == "AT_RISK" for r in ordered),
                        "phase_conflicts": sum(r["phase_state"] == "OUTSIDE_PHASE" for r in ordered)}}


def csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("'", "\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@")) else text


def csv_restore(text: str) -> str:
    if text.startswith("'") and (text[1:].startswith(("'", "\t", "\r", "\n"))
                                     or text[1:].lstrip().startswith(("=", "+", "-", "@"))):
        return text[1:]
    return text


def table_csv(report: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=(*META, *FIELDS, "planning_state", *DERIVED), lineterminator="\n")
    writer.writeheader()
    for row in report["recommendations"]:
        cells = dict(row, document_title=report["title"], synthetic=json.dumps(report["synthetic"]),
                     document_assumptions=json.dumps(report["assumptions"], ensure_ascii=False), planning_state=STATE)
        for field in (*LISTS, "duration_days", "issues"):
            cells[field] = "" if row[field] is None else json.dumps(row[field], ensure_ascii=False)
        writer.writerow({key: csv_safe(value) for key, value in cells.items()})
    return stream.getvalue()


def from_csv(text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    names = reader.fieldnames or []
    allowed = set((*META, *FIELDS, "planning_state", *DERIVED))
    if len(names) != len(set(names)) or not set((*META, *FIELDS)) <= set(names) or set(names) - allowed:
        raise PlanError("CSV needs unique input columns; only documented derived columns may be added")
    rows, metadata = [], None
    for number, cells in enumerate(reader, 2):
        if None in cells or any(value is None for value in cells.values()):
            raise PlanError(f"CSV row {number}: wrong number of cells")
        cells = {key: csv_restore(value) for key, value in cells.items()}
        meta = (cells["document_title"], strict_loads(cells["synthetic"]),
                strict_loads(cells["document_assumptions"]))
        if metadata is not None and canonical({"meta": meta}) != canonical({"meta": metadata}):
            raise PlanError("CSV document metadata differs between rows")
        metadata = meta
        row = {key: cells[key] for key in FIELDS}
        for field in (*LISTS, "duration_days"):
            row[field] = None if field == "duration_days" and not row[field].strip() else strict_loads(row[field])
        row["owner_role"] = row["owner_role"] or None
        rows.append(row)
    if metadata is None:
        raise PlanError("CSV contains no recommendations")
    return validate({"schema_version": 1, "title": metadata[0], "synthetic": metadata[1],
                     "assumptions": metadata[2], "recommendations": rows})


def interval(row: dict, prefix: str) -> str:
    if row[prefix + "_min"] is None:
        return "UNKNOWN"
    return f"D{row[prefix + '_min']}–D{row[prefix + '_max']}"


def markdown(report: dict) -> str:
    def safe(value):
        return html.escape(str(value)).replace("|", "\\|").replace("\n", "<br>").replace("\r", "")
    lines = [f"# {safe(report['title'])}", "", f"**{STATE} · SYNTHETIC={report['synthetic']}**", "",
             NOTICE, "", f"Input SHA-256: `{report['input_sha256']}`", "", "## Roadmap", "",
             "|Recommendation|Group / owner role|Requested start phase|Start range|Finish range|Status / phase|Prerequisites|",
             "|---|---|---|---|---|---|---|"]
    for row in report["recommendations"]:
        values = [row["id"] + " — " + row["title"], row["group"] + " / " + (row["owner_role"] or "UNKNOWN"),
                  row["phase"], interval(row, "start"), interval(row, "finish"),
                  row["status"] + " / " + row["phase_state"], ", ".join(row["depends_on"]) or "None"]
        lines.append("|" + "|".join(map(safe, values)) + "|")
    lines += ["", "## Dependency-independent layers", "",
              "Same-layer items have no prerequisite path between them. Phases, staffing and budgets may still prevent simultaneous work.", ""]
    lines.extend(f"Layer {i}: " + ", ".join(group) for i, group in enumerate(report["dependency_layers"]))
    lines += ["", "## Outcomes and traceability", ""]
    for row in report["recommendations"]:
        lines += [f"### {safe(row['id'])}", f"Practice change: {safe(row['practice_change'])}",
                  f"Observable outcome: {safe(row['observable_outcome'])}",
                  "Finding refs: " + safe(", ".join(row["finding_refs"]) or "MISSING"),
                  "Evidence refs: " + safe(", ".join(row["evidence_refs"]) or "MISSING"),
                  "Assumptions: " + safe("; ".join(row["assumptions"]) or "MISSING"),
                  "Planning issues: " + safe("; ".join(row["issues"]) or "None identified by this model"), ""]
    lines += ["## Document assumptions", "", *[safe(x) for x in report["assumptions"]], ""]
    return "\n".join(lines)


def render_html(report: dict, dependency_report: dict | None = None) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    dependency_links = ""
    if dependency_report is not None:
        dependency_links = ("<section aria-label='Dependency structure'><h2>Dependency structure: "
                            + esc(dependency_report["dependency_check_status"])
                            + "</h2><p>This structural result is separate from the duration and phase outcomes above.</p>"
                            "<p><a href='dependencies.md'>Dependency findings</a> · "
                            "<a href='dependencies.json'>Dependency JSON</a> · "
                            "<a href='dependencies.dot'>Dependency graph source</a></p></section>")
    rows = []
    for row in report["recommendations"]:
        cells = []
        for phase, (lower, upper) in PHASES.items():
            if row["start_min"] is None:
                label = row["status"] if phase == row["phase"] else "—"
            else:
                end = row["finish_max"]
                intersects = row["start_min"] < (upper if upper is not None else float("inf")) and end > lower
                milestone = end == row["start_min"] and lower <= end and (upper is None or end < upper)
                label = f"Possible work · {interval(row, 'start')} start / {interval(row, 'finish')} finish" if intersects or milestone else "—"
            if phase == row["phase"]:
                label = "REQUESTED START PHASE · " + label
            cells.append("<td>" + esc(label) + "</td>")
        detail = (f"{row['id']} — {row['title']} | {row['group']} / {row['owner_role'] or 'UNKNOWN OWNER'} | "
                  f"{row['status']} / {row['phase_state']}")
        support = (
            ("Prerequisites", ", ".join(row["depends_on"]) or "None"),
            ("Practice change", row["practice_change"]),
            ("Observable outcome", row["observable_outcome"]),
            ("Finding references", "; ".join(row["finding_refs"]) or "MISSING"),
            ("Evidence references", "; ".join(row["evidence_refs"]) or "MISSING"),
            ("Assumptions", "; ".join(row["assumptions"]) or "MISSING"),
            ("Planning issues", "; ".join(row["issues"]) or "None identified by this model"),
        )
        details = "".join("<dt>" + esc(label) + "</dt><dd>" + esc(value) + "</dd>"
                          for label, value in support)
        rows.append("<tr><th scope='row'>" + esc(detail) + "<details><summary>Outcome, sources and assumptions</summary><dl>" + details + "</dl></details></th>" + "".join(cells) + "</tr>")
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Draft relative-day roadmap</title><style>body{font:16px/1.5 system-ui;margin:2rem;max-width:100rem}"
            ".table-scroll{overflow-x:auto}.table-scroll:focus{outline:3px solid #2363ad;outline-offset:3px}"
            "table{border-collapse:collapse;width:100%;min-width:48rem}th,td{border:1px solid;padding:.75rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}"
            "th:first-child{min-width:16rem}dt{font-weight:700}dd{margin:0 0 .5rem}"
            "caption{text-align:left;padding:1rem 0}details{font-weight:normal}summary{cursor:pointer}"
            "@media(max-width:48rem){body{margin:1rem}}"
            "@media print{body{font-size:10pt;margin:0}table{min-width:0}.table-scroll{overflow:visible}tr{break-inside:avoid}}"
            "</style><main><h1>" + esc(report["title"]) + "</h1><p><strong>" + STATE + " · SYNTHETIC=" + str(report["synthetic"])
            + "</strong></p><p>" + NOTICE + "</p><p>" + esc(report["summary"]) + "</p>"
            "<nav aria-label='Alternate formats'><a href='planning_table.csv'>Editable planning table</a> · "
            "<a href='roadmap.md'>Markdown roadmap</a> · <a href='roadmap.json'>JSON roadmap</a></nav>"
            "<div class='table-scroll' role='region' aria-label='Relative-day roadmap table' tabindex='0'><table><caption>"
            "Possible work envelopes, not booked work. Edit the accompanying CSV inputs and rerun to update this view. "
            "Half-open horizons: day 90 belongs to the second phase; day 180 belongs to the third.</caption>"
            "<thead><tr><th scope='col'>Recommendation / accountable role / status</th><th scope='col'>0–90 days</th>"
            "<th scope='col'>90–180 days</th><th scope='col'>180+ days</th></tr></thead><tbody>" + "".join(rows)
            + "</tbody></table></div><h2>Document assumptions</h2><ul>"
            + "".join("<li>" + esc(value) + "</li>" for value in report["assumptions"])
            + "</ul>" + dependency_links
            + "<p>All details and assumptions are also available in roadmap.md and roadmap.json.</p>"
            "<p>Input SHA-256: " + esc(report["input_sha256"]) + "</p></main></html>\n")


def analyze_dependencies(document: dict) -> dict:
    """Compose the installed dependency oracle with this exact parsed source."""
    source = Path(__file__).resolve().parent.parent / "uiowa_rfq_18649_roadmap_dependency_oracle" / "checker.py"
    if not source.is_file():
        raise PlanError("--include-dependencies requires the sibling roadmap_dependency_oracle/checker.py")
    spec = importlib.util.spec_from_file_location("uiowa_roadmap_dependency_oracle", source)
    if spec is None or spec.loader is None:
        raise PlanError("could not load the installed dependency oracle")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    try:
        result = checker.analyze_roadmap085(document)
    except checker.InputError as exc:
        raise PlanError(f"dependency input: {exc}") from exc
    return {
        "report": result,
        "payloads": {
            "dependencies.json": json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            "dependencies.md": checker.markdown(result),
            "dependencies.dot": checker.dot(result),
        },
        "component": {
            "path": "revenue/uiowa_rfq_18649_roadmap_dependency_oracle/checker.py",
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "report_schema": result["schema"],
            "graph_input_sha256": result["input_sha256"],
            "full_input_sha256": result["source_projection"]["full_input_sha256"],
        },
    }


def write_bundle(report: dict, destination: Path, dependency: dict | None = None) -> dict:
    payloads = {"roadmap.json": json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                "planning_table.csv": table_csv(report), "roadmap.md": markdown(report),
                "roadmap.html": render_html(report, dependency["report"] if dependency else None)}
    if dependency is not None:
        payloads.update(dependency["payloads"])
    destination.mkdir(parents=True, exist_ok=False)
    digests = {}
    for name, text in payloads.items():
        data = text.encode("utf-8")
        with (destination / name).open("xb") as handle:
            handle.write(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    receipt = {"planning_state": STATE, "input_sha256": report["input_sha256"], "outputs": digests}
    if dependency is not None:
        receipt["components"] = {
            "roadmap": {
                "path": "revenue/uiowa_rfq_18649_roadmap/roadmap.py",
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "schema_version": report["schema_version"],
                "input_sha256": report["input_sha256"],
            },
            "dependencies": dependency["component"],
        }
    with (destination / "manifest.json").open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON document or exported editable CSV")
    parser.add_argument("output", type=Path, help="new output directory (never overwritten)")
    parser.add_argument("--require-plannable", action="store_true", help="exit 3 for unscheduled work or phase conflicts/risks")
    parser.add_argument("--include-dependencies", action="store_true",
                        help="include the installed dependency oracle's JSON, Markdown and DOT from the same source")
    args = parser.parse_args(argv)
    try:
        text = args.input.read_text(encoding="utf-8-sig")
        document = from_csv(text) if args.input.suffix.lower() == ".csv" else strict_loads(text)
        report = plan(document)
        dependency = analyze_dependencies(document) if args.include_dependencies else None
        write_bundle(report, args.output, dependency)
        summary = dict(report["summary"])
        dependency_incomplete = False
        if dependency is not None:
            graph = dependency["report"]
            summary.update(dependency_check_status=graph["dependency_check_status"],
                           dependency_errors=graph["counts"]["errors"],
                           dependency_warnings=graph["counts"]["warnings"])
            dependency_incomplete = graph["dependency_check_status"] != "CONSISTENT"
        print(json.dumps(summary, sort_keys=True))
        incomplete = any(report["summary"][k] for k in ("unscheduled", "phase_conflicts", "phase_at_risk"))
        return 3 if args.require_plannable and (incomplete or dependency_incomplete) else 0
    except (PlanError, OSError, UnicodeError, csv.Error) as exc:
        print(f"roadmap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
