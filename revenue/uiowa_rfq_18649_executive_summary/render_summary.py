#!/usr/bin/env python3
"""Render a leadership briefing from the existing UIOWA-093 trace bundle.

Source statements remain verbatim. Structural trace checks do not authenticate
evidence or make the resulting draft an accepted institutional assessment.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from revenue.uiowa_rfq_18649_traceability_rehearsal import validate_trace

DEFAULT_BUNDLE = ROOT / "revenue/uiowa_rfq_18649_traceability_rehearsal"
SOURCES = ("evidence.csv", "findings.csv", "recommendations.csv", "trace-map.csv",
           "executive-summary.md", "final-report.md")
FIELDS = {
    "evidence.csv": ("evidence_id", "service", "source_type", "source_name", "locator", "observation", "evidence_state"),
    "findings.csv": ("finding_id", "service", "type", "title", "statement", "evidence_ids", "confidence", "limitation"),
    "recommendations.csv": ("recommendation_id", "title", "linked_findings", "action", "expected_outcome", "effort", "dependency"),
    "trace-map.csv": ("statement_id", "report_location", "statement_summary", "recommendation_ids", "finding_ids", "evidence_ids"),
}
NOTICE = ("DRAFT — supplied-record leadership briefing. Structural references were checked; "
          "source authenticity, professional conclusions and institutional acceptance are not established. "
          "The bundled public example is fictional.")
PLANNING_SCHEMA = "uiowa-executive-planning/v1"
PLANNING_LIMIT = 2 * 1024 * 1024
PLANNING_TEXT = ("owner", "priority", "sequence", "timing", "resource_assumptions")
MEASURE_TEXT = ("unit", "baseline", "target", "observed_value", "measurement_window", "notes")


def _planning_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"planning: duplicate JSON field {key!r}")
        result[key] = value
    return result


def _planning_shape(value, required, optional, where: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected an object")
    missing, extra = set(required) - value.keys(), value.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"{where}: missing fields {sorted(missing)}; unknown fields {sorted(extra)}")


def _planning_string(value, where: str, *, optional=False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise ValueError(f"{where}: expected {'text or null' if optional else 'nonempty text'}")


def _planning_id(value, where: str) -> None:
    if not isinstance(value, str) or not validate_trace.ID.fullmatch(value):
        raise ValueError(f"{where}: expected a stable ASCII identifier")


def _planning_refs(value, known: set[str], where: str, *, required=False) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{where}: expected a list of evidence identifiers")
    ids = set(value)
    if len(ids) != len(value) or ids - known or (required and not ids):
        raise ValueError(f"{where}: references must be unique{' and nonempty' if required else ''}; "
                         f"unknown identifiers {sorted(ids - known)}")
    return ids


def _supplied(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def planning_input(path: Path, report: dict) -> dict:
    """Read explicit planning statements once; never derive decisions or results."""
    with path.open("rb") as handle:
        raw = handle.read(PLANNING_LIMIT + 1)
    if len(raw) > PLANNING_LIMIT:
        raise ValueError("planning: input exceeds 2 MiB")
    def invalid_constant(value):
        raise ValueError(f"planning: non-finite JSON value {value}")
    try:
        plan = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_planning_object,
                          parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"planning: unreadable JSON ({type(exc).__name__})") from exc
    _planning_shape(plan, ("schema", "context", "plan_id", "version", "source_name",
                           "source_locator", "recommendations"), (), "planning")
    if plan["schema"] != PLANNING_SCHEMA:
        raise ValueError(f"planning.schema: expected {PLANNING_SCHEMA}")
    if plan["context"] not in ("SYNTHETIC_EXAMPLE", "SUPPLIED_RECORDS"):
        raise ValueError("planning.context: expected SYNTHETIC_EXAMPLE or SUPPLIED_RECORDS")
    _planning_id(plan["plan_id"], "planning.plan_id")
    for key in ("version", "source_name", "source_locator"):
        _planning_string(plan[key], "planning." + key)
    if not isinstance(plan["recommendations"], list):
        raise ValueError("planning.recommendations: expected a list")
    recommendations = {item["record"]["recommendation_id"]: item["record"]
                       for item in report["recommendations"]}
    findings = {item["record"]["finding_id"]: item["record"] for item in report["findings"]}
    evidence = {item["record"]["evidence_id"] for item in report["evidence"]}
    seen_recommendations, seen_plans, seen_measures, rows = set(), set(), set(), []
    for index, row in enumerate(plan["recommendations"]):
        where = f"planning.recommendations[{index}]"
        _planning_shape(row, ("planning_id", "recommendation_id", "evidence_ids"),
                        (*PLANNING_TEXT, "outcome_measures"), where)
        for key in ("planning_id", "recommendation_id"):
            _planning_id(row[key], where + "." + key)
        rid, pid = row["recommendation_id"], row["planning_id"]
        if rid not in recommendations or rid in seen_recommendations or pid in seen_plans:
            raise ValueError(f"{where}: unknown or repeated recommendation, or repeated planning ID")
        seen_recommendations.add(rid)
        seen_plans.add(pid)
        basis = set()
        for fid in validate_trace.split_ids(recommendations[rid]["linked_findings"]):
            basis.update(validate_trace.split_ids(findings[fid]["evidence_ids"]))
        _planning_refs(row["evidence_ids"], basis, where + ".evidence_ids", required=True)
        for key in PLANNING_TEXT:
            _planning_string(row.get(key), where + "." + key, optional=True)
        measures = row.get("outcome_measures", [])
        if not isinstance(measures, list):
            raise ValueError(f"{where}.outcome_measures: expected a list")
        for number, measure in enumerate(measures):
            mwhere = f"{where}.outcome_measures[{number}]"
            _planning_shape(measure, ("measure_id", "name"),
                            (*MEASURE_TEXT, "observation_evidence_ids"), mwhere)
            _planning_id(measure["measure_id"], mwhere + ".measure_id")
            if measure["measure_id"] in seen_measures:
                raise ValueError(f"{mwhere}: repeated measure ID {measure['measure_id']}")
            seen_measures.add(measure["measure_id"])
            _planning_string(measure["name"], mwhere + ".name")
            for key in MEASURE_TEXT:
                _planning_string(measure.get(key), mwhere + "." + key, optional=True)
            observations = _planning_refs(measure.get("observation_evidence_ids", []),
                                          evidence, mwhere + ".observation_evidence_ids")
            if _supplied(measure.get("observed_value")) and (
                    not observations or not _supplied(measure.get("measurement_window"))):
                raise ValueError(f"{mwhere}: an observed value requires a measurement window "
                                 "and registered observation evidence")
        rows.append({"record": row, "source": {"file": path.name,
                     "json_pointer": f"/recommendations/{index}"}})
    result = dict(plan)
    result["recommendations"] = sorted(rows, key=lambda item: item["record"]["recommendation_id"])
    result["source_file"] = {"file": path.name, "bytes": len(raw),
                             "sha256": hashlib.sha256(raw).hexdigest(),
                             "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
    return result


def source_inventory(root: Path) -> dict:
    result = {}
    for name in SOURCES:
        raw = (root / name).read_bytes()
        result[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                        "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
    return result


def records(root: Path, name: str) -> list[dict]:
    rows = []
    with (root / name).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, strict=True)
        missing = set(FIELDS[name]) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{name}: required briefing columns missing: {sorted(missing)}")
        previous_line = reader.line_num
        for row in reader:
            rows.append({"record": row, "source": {"file": name, "line_start": previous_line + 1,
                                                   "line_end": reader.line_num}})
            previous_line = reader.line_num
    return sorted(rows, key=lambda r: r["record"][FIELDS[name][0]])


def build(root: Path, *, planning: Path | None = None) -> dict:
    root = root.resolve(strict=True)
    before = source_inventory(root)
    validation = validate_trace.validate(root)
    if validation["status"] != "PASS":
        details = "; ".join(f"{i['file']}:{i['row']} {i['code']} {i['detail']}" for i in validation["issues"])
        raise ValueError(f"source trace bundle is {validation['status']}: {details}")
    tables = {name: records(root, name) for name in FIELDS}
    if source_inventory(root) != before:
        raise ValueError("source bundle changed while the briefing was being assembled")
    canonical = json.dumps(before, sort_keys=True, separators=(",", ":")).encode()
    report = {"schema": "uiowa-executive-summary/v1", "status": "DRAFT", "notice": NOTICE,
            "source_bundle_sha256": hashlib.sha256(canonical).hexdigest(),
            "source_files": before, "source_validation": validation,
            "findings": tables["findings.csv"], "recommendations": tables["recommendations.csv"],
            "evidence": tables["evidence.csv"], "statement_trace": tables["trace-map.csv"],
            "planning_state": {"priority_and_schedule": "NOT_SUPPLIED",
                               "accountable_owners": "NOT_SUPPLIED",
                               "cash_savings": "NOT_ESTIMATED",
                               "measured_outcome_results": "NOT_SUPPLIED"}}
    if planning is not None:
        plan = planning_input(Path(planning), report)
        report["schema"] = "uiowa-executive-summary/v2"
        report["planning"] = plan
        rows = [item["record"] for item in plan["recommendations"]]
        measures = [measure for row in rows for measure in row.get("outcome_measures", [])]
        state = report["planning_state"]
        state["priority_and_schedule"] = "SUPPLIED" if any(
            _supplied(row.get(key)) for row in rows for key in ("priority", "sequence", "timing")) else "NOT_SUPPLIED"
        state["accountable_owners"] = "SUPPLIED" if any(_supplied(row.get("owner")) for row in rows) else "NOT_SUPPLIED"
        state["resource_assumptions"] = "SUPPLIED" if any(
            _supplied(row.get("resource_assumptions")) for row in rows) else "NOT_SUPPLIED"
        state["outcome_measures"] = "SUPPLIED" if measures else "NOT_SUPPLIED"
        state["measured_outcome_results"] = "SUPPLIED" if any(
            _supplied(measure.get("observed_value")) for measure in measures) else "NOT_SUPPLIED"
        state["recommendations_without_planning"] = sorted(
            {item["record"]["recommendation_id"] for item in report["recommendations"]}
            - {row["recommendation_id"] for row in rows})
    return report


def text(value: str) -> str:
    value = html.escape(value or "NOT SUPPLIED", quote=True)
    for char, entity in (("\\", "&#92;"), ("|", "&#124;"), ("`", "&#96;"),
                         ("*", "&#42;"), ("_", "&#95;"), ("[", "&#91;"), ("]", "&#93;")):
        value = value.replace(char, entity)
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def refs(value: str, family: str) -> str:
    return ", ".join(f"[{text(ident)}](#{family}-{ident})" for ident in sorted(validate_trace.split_ids(value))) or "None supplied"


def planning_markdown(item: dict) -> list[str]:
    row, source = item["record"], item["source"]
    def shown(value):
        return text(value if _supplied(value) else "")
    lines = [f'<a id="planning-{row["planning_id"]}"></a>', "",
             f"**Planning record:** {text(row['planning_id'])}.", "",
             f"**Supplied accountable owner:** {shown(row.get('owner'))}", "",
             f"**Supplied priority:** {shown(row.get('priority'))}", "",
             f"**Supplied sequence:** {shown(row.get('sequence'))}", "",
             f"**Planned timing:** {shown(row.get('timing'))}", "",
             f"**Resource assumptions:** {shown(row.get('resource_assumptions'))}", "",
             "Rationale evidence: " + refs(";".join(row["evidence_ids"]), "evidence") + ". "
             "These references link the recommendation's rationale; the planning values are supplied separately.", ""]
    measures = row.get("outcome_measures", [])
    if not measures:
        lines += ["**Outcome measures and observed results:** NOT SUPPLIED.", ""]
    for number, measure in enumerate(measures):
        lines += [f'<a id="measure-{measure["measure_id"]}"></a>', "",
                  f"#### {text(measure['measure_id'])} — {text(measure['name'])}", "",
                  "| Supplied baseline | Proposed target | Supplied observed value | Unit |",
                  "|---|---|---|---|",
                  "| " + " | ".join(shown(measure.get(key)) for key in
                                      ("baseline", "target", "observed_value", "unit")) + " |", "",
                  f"**Measurement window:** {shown(measure.get('measurement_window'))}", "",
                  "**Observation evidence:** " + refs(";".join(measure.get("observation_evidence_ids", [])), "evidence") + ".", "",
                  f"**Measure notes:** {shown(measure.get('notes'))}", "",
                  f"Planning locator: {text(source['file'])}, "
                  f"{text(source['json_pointer'] + '/outcome_measures/' + str(number))}.", ""]
    lines += [f"Planning locator: {text(source['file'])}, {text(source['json_pointer'])}.", ""]
    return lines


def markdown(report: dict) -> str:
    lines = ["# Leadership review briefing", "", NOTICE, "",
             f"Source bundle: `{report['source_bundle_sha256']}`.", "",
             "## Strengths, gaps and uncertainty", "",
             "The following finding text, classifications and confidence labels come from the source register. "
             "Confidence is supplied metadata, not recalculated here. Each limitation travels with its statement.", ""]
    plan = report.get("planning")
    planning_rows = {item["record"]["recommendation_id"]: item
                     for item in plan["recommendations"]} if plan else {}
    if plan:
        context = ("FICTIONAL WORKED PLAN — no institutional decision or achieved result is asserted."
                   if plan["context"] == "SYNTHETIC_EXAMPLE" else
                   "SUPPLIED PLANNING — decisions and observation values are transcribed, not independently verified.")
        lines[6:6] = ["## Planning source", "", context, "",
                      f"Plan {text(plan['plan_id'])}, version {text(plan['version'])}.", "",
                      f"**Source:** {text(plan['source_name'])}. **Locator:** {text(plan['source_locator'])}.", "",
                      "Plan fields remain draft inputs. A target is never promoted to an observed result; "
                      "recording timing does not schedule an action or contact an owner.", ""]
    for item in report["findings"]:
        row = item["record"]
        ident = row["finding_id"]
        lines += [f'<a id="finding-{ident}"></a>', "", f"### {text(ident)} — {text(row['title'])}", "",
                  f"{text(row['service'])}; supplied classification: **{text(row['type'])}**; "
                  f"supplied confidence: {text(row['confidence'])}.", "",
                  text(row["statement"]), "", f"**Limitation:** {text(row['limitation'])}", "",
                  "Sources: " + refs(row["evidence_ids"], "evidence") + ".", ""]
    lines += ["## Decisions and practical sequencing", "",
              "These are proposed actions copied from the recommendation register. "
              "Display order follows identifiers, not priority or an approved schedule. "
              "Confirm dependencies, accountable owners and sequencing before adopting a plan.", ""]
    findings = {i["record"]["finding_id"]: i["record"] for i in report["findings"]}
    for item in report["recommendations"]:
        row = item["record"]
        ident = row["recommendation_id"]
        evidence = set()
        for fid in validate_trace.split_ids(row["linked_findings"]):
            evidence.update(validate_trace.split_ids(findings[fid]["evidence_ids"]))
        lines += [f'<a id="recommendation-{ident}"></a>', "", f"### {text(ident)} — {text(row['title'])}", "",
                  f"**Proposed action:** {text(row['action'])}", "",
                  f"**Dependency:** {text(row['dependency'])}", "",
                  f"**Expected outcome, not a measurement:** {text(row['expected_outcome'])}", "",
                  f"**Supplied implementation-effort label:** {text(row['effort'])}. "
                  "This is not a dollar estimate or cash savings.", "",
                  ]
        if ident in planning_rows:
            lines += planning_markdown(planning_rows[ident])
        else:
            lines += ["**Owner, priority, schedule and measured result:** NOT SUPPLIED.", ""]
        lines += ["Finding basis: " + refs(row["linked_findings"], "finding") + ". "
                  "Source chain: " + refs(";".join(sorted(evidence)), "evidence") + ".", ""]
    resource_note = ("Owner, sequence, timing, resources and outcome measures above are supplied draft inputs. "
                     "No staffing quantity, cash saving or realized benefit is calculated. Baselines, proposed targets "
                     "and supplied observed values are kept separate; missing fields remain NOT SUPPLIED. "
                     "Evidence links do not authenticate a measurement or establish that a target was achieved."
                     if plan else
                     "Effort labels and dependencies above are the supplied planning inputs. "
                     "No staffing quantity, budget, cash saving, baseline, target, measurement window or realized "
                     "benefit is inferred. Record those decisions separately with their source and version. "
                     "An expected benefit must not be reported as an observed result.")
    lines += ["## Resource assumptions and outcome follow-up", "", resource_note, "",
              "## Statement-to-source navigation", "",
              "Original statement identities and locations are retained below. "
              "Finding and recommendation links point into this portable briefing.", "",
              "| Statement | Original location | Registered statement | Findings | Recommendations | Evidence |",
              "|---|---|---|---|---|---|"]
    for item in report["statement_trace"]:
        row = item["record"]
        lines.append("| " + " | ".join([text(row["statement_id"]), text(row["report_location"]),
                     text(row["statement_summary"]), refs(row["finding_ids"], "finding"),
                     refs(row["recommendation_ids"], "recommendation"), refs(row["evidence_ids"], "evidence")]) + " |")
    lines += ["", "## Evidence locators and retained observations", ""]
    for item in report["evidence"]:
        row = item["record"]
        ident = row["evidence_id"]
        source = item["source"]
        lines += [f'<a id="evidence-{ident}"></a>', "", f"### {text(ident)} — {text(row['source_name'])}", "",
                  f"{text(row['service'])}; {text(row['source_type'])}; supplied state: {text(row['evidence_state'])}.", "",
                  f"**Original locator:** {text(row['locator'])}", "", text(row["observation"]), "",
                  f"Register locator: {text(source['file'])}, lines {source['line_start']}–{source['line_end']}.", ""]
    lines += ["## Exact source versions", "",
              "These hashes identify the input files used to render this draft, not the authenticity "
              "of underlying source documents. Structural PASS is not substantive approval.", "",
              "| Source file | Bytes | Git blob | SHA-256 |", "|---|---:|---|---|"]
    for name, identity in sorted(report["source_files"].items()):
        lines.append(f"| {text(name)} | {identity['bytes']} | {identity['git_blob_sha1']} | {identity['sha256']} |")
    if plan:
        identity = plan["source_file"]
        lines += ["", "### Exact planning version", "",
                  "The planning input is separate from the six-file evidence bundle above. "
                  "This identity binds the planning statements and their JSON locators to the bytes read.", "",
                  "| Planning file | Bytes | Git blob | SHA-256 |", "|---|---:|---|---|",
                  f"| {text(identity['file'])} | {identity['bytes']} | {identity['git_blob_sha1']} | {identity['sha256']} |"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", type=Path, default=DEFAULT_BUNDLE,
                        help="Existing UIOWA-093 trace bundle directory")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--planning", type=Path,
                        help="Optional explicit planning JSON; see planning-template.json")
    args = parser.parse_args(argv)
    try:
        report = build(args.bundle, planning=args.planning)
        rendered = markdown(report) if args.format == "markdown" else json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        print(rendered, end="")
        return 0
    except (OSError, ValueError, csv.Error, KeyError, TypeError, RecursionError) as exc:
        print(f"executive-summary error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
