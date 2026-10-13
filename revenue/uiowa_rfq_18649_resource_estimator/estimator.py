"""Offline recommendation-linked effort scenarios. No external services or scheduling."""
from __future__ import annotations

import argparse
import copy
import csv
from decimal import Decimal, InvalidOperation, localcontext
import html
import hashlib
import io
import json
from pathlib import Path
import sys

SCHEMA = "uiowa.resource-plan/v1"
KINDS = ("implementation", "process_change", "training", "maintenance")
POINTS = ("low", "central", "high")
ZERO = (Decimal(0),) * 3


class PlanError(ValueError):
    """An input is structurally invalid; missing estimates instead use null."""


def _object(value, fields, path):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise PlanError(f"{path}: expected exactly {fields}")


def _text(value, path):
    if type(value) is not str or not value.strip():
        raise PlanError(f"{path}: expected nonempty text")
    return value


def _list(value, path, nonempty=False):
    if type(value) is not list or (nonempty and not value):
        raise PlanError(f"{path}: expected {'nonempty ' if nonempty else ''}list")
    return value


def _refs(value, allowed, path, nonempty=False):
    _list(value, path, nonempty)
    for item in value:
        _text(item, path)
    if len(set(value)) != len(value) or not set(value) <= set(allowed):
        raise PlanError(f"{path}: duplicate or unknown reference")


def _number(value, path):
    if type(value) not in (str, int, float, Decimal):
        raise PlanError(f"{path}: expected a nonnegative decimal, not a boolean")
    if len(str(value)) > 80:
        raise PlanError(f"{path}: decimal representation is too long")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise PlanError(f"{path}: invalid decimal") from None
    if not number.is_finite() or not 0 <= number <= Decimal("1000000000"):
        raise PlanError(f"{path}: expected finite value from 0 to 1000000000")
    if not -6 <= number.as_tuple().exponent <= 9:
        raise PlanError(f"{path}: decimal exponent must be between -6 and 9")
    return Decimal(0) if number == 0 else number


def _range(value, path):
    if value is None:
        return None
    _object(value, "low central high", path)
    result = tuple(_number(value[p], f"{path}.{p}") for p in POINTS)
    if not result[0] <= result[1] <= result[2]:
        raise PlanError(f"{path}: require low <= central <= high")
    return result


def _index(rows, fields, path):
    result = {}
    for row in _list(rows, path):
        _object(row, fields, path)
        key = _text(row["id"], f"{path}.id")
        if key in result:
            raise PlanError(f"{path}: duplicate id {key}")
        result[key] = row
    return result


def _encode(values):
    if values is None:
        return None
    return {p: format(n, "f") for p, n in zip(POINTS, values)}


def _sum(values):
    return tuple(sum((v[i] for v in values), Decimal(0)) for i in range(3))


def _scale(values, count):
    return None if values is None else tuple(n * count for n in values)


def _capacity(demand, capacity):
    if demand is None:
        return "UNKNOWN_DEMAND"
    if demand[2] == 0:
        return "NO_DEMAND"
    if capacity is None:
        return "UNKNOWN_CAPACITY"
    if capacity[2] == 0:
        return "UNRESOURCED"
    if demand[0] > capacity[2]:
        return "EXCEEDS_EVEN_OPTIMISTIC_CAPACITY"
    if demand[2] <= capacity[0]:
        return "FITS_ALL_STATED_SCENARIOS"
    return "SCENARIO_DEPENDENT"


def load_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PlanError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise PlanError(f"nonfinite JSON value: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_float=Decimal,
                          parse_constant=constant)
    except (ValueError, RecursionError) as exc:
        raise PlanError(str(exc)) from None


def estimate(plan):
    """Return decimal-string ranges; null totals mean incomplete, never zero."""
    # Local arithmetic precision is independent of the embedding application's context.
    with localcontext() as context:
        context.prec = 80
        return _estimate(plan)


def _estimate(plan):
    _object(plan, "schema plan_id title evidence_class planning_months assumptions roles recommendations activities", "plan")
    if plan["schema"] != SCHEMA:
        raise PlanError(f"schema: expected {SCHEMA}")
    for key in ("plan_id", "title"):
        _text(plan[key], key)
    if plan["evidence_class"] not in ("SYNTHETIC", "USER_PROVIDED_UNVERIFIED"):
        raise PlanError("evidence_class: expected SYNTHETIC or USER_PROVIDED_UNVERIFIED")
    months = plan["planning_months"]
    if type(months) is not int or not 1 <= months <= 120:
        raise PlanError("planning_months: expected integer from 1 to 120")
    assumptions = _index(plan["assumptions"], "id text source", "assumptions")
    for a in assumptions.values():
        _text(a["text"], "assumption.text")
        _text(a["source"], "assumption.source")
    roles = _index(plan["roles"], "id name skills implementation_hours_per_month maintenance_hours_per_month assumption_ids", "roles")
    capacities = {}
    for rid, role in roles.items():
        _text(role["name"], "role.name")
        for skill in _list(role["skills"], "role.skills", True):
            _text(skill, "role.skill")
        _refs(role["assumption_ids"], assumptions, "role.assumption_ids", True)
        capacities[rid] = (_range(role["implementation_hours_per_month"], "implementation capacity"),
                           _range(role["maintenance_hours_per_month"], "maintenance capacity"))
    recs = _index(plan["recommendations"], "id title group_id area dependencies adoption_notes success_evidence", "recommendations")
    if not roles or not recs:
        raise PlanError("plan: at least one role and recommendation are required")
    for rid, rec in recs.items():
        for key in ("title", "group_id", "area", "adoption_notes", "success_evidence"):
            _text(rec[key], f"recommendation.{key}")
        _refs(rec["dependencies"], recs, f"{rid}.dependencies")
    # This orders prerequisites; it is deliberately not a calendar or critical-path model.
    order, remaining = [], set(recs)
    while remaining:
        ready = sorted(r for r in remaining if set(recs[r]["dependencies"]) <= set(order))
        if not ready:
            raise PlanError("recommendations.dependencies: cycle")
        order.extend(ready)
        remaining.difference_update(ready)
    activities = _index(plan["activities"], "id description recommendation_ids role_id kind unit_label units hours_per_unit assumption_ids", "activities")
    rows, values = [], {}
    for aid, activity in activities.items():
        for key in ("description", "unit_label", "role_id", "kind"):
            _text(activity[key], f"{aid}.{key}")
        if activity["role_id"] not in roles or activity["kind"] not in KINDS:
            raise PlanError(f"{aid}: unknown role or kind")
        _refs(activity["recommendation_ids"], recs, f"{aid}.recommendation_ids", True)
        _refs(activity["assumption_ids"], assumptions, f"{aid}.assumption_ids", True)
        units = _range(activity["units"], f"{aid}.units")
        hours = _range(activity["hours_per_unit"], f"{aid}.hours_per_unit")
        effort = None if units is None or hours is None else tuple(u * h for u, h in zip(units, hours))
        values[aid] = effort
        rows.append({"activity_id": aid, "description": activity["description"],
                     "recommendation_ids": list(activity["recommendation_ids"]),
                     "role_id": activity["role_id"], "kind": activity["kind"],
                     "unit_label": activity["unit_label"], "units": _encode(units),
                     "hours_per_unit": _encode(hours), "effort_hours": _encode(effort),
                     "period": "PER_MONTH" if activity["kind"] == "maintenance" else "ONE_TIME",
                     "assumption_ids": list(activity["assumption_ids"]),
                     "missing_inputs": [name for name in ("units", "hours_per_unit") if activity[name] is None]})

    unscoped = [rid for rid in order if not any(rid in r["recommendation_ids"] for r in rows)]

    def subtotal(selected):
        ids = [r["activity_id"] for r in selected]
        missing = [aid for aid in ids if values[aid] is None]
        known = _sum([values[aid] for aid in ids if values[aid] is not None])
        total = None if missing or unscoped else known
        return {"known_hours": _encode(known), "total_hours": _encode(total),
                "missing_activity_ids": missing, "unscoped_recommendation_ids": list(unscoped)}, total

    once, one_values = subtotal([r for r in rows if r["kind"] != "maintenance"])
    recurring, recurring_values = subtotal([r for r in rows if r["kind"] == "maintenance"])
    role_results = []
    for rid, role in roles.items():
        one, one_v = subtotal([r for r in rows if r["role_id"] == rid and r["kind"] != "maintenance"])
        maintenance, maintenance_v = subtotal([r for r in rows if r["role_id"] == rid and r["kind"] == "maintenance"])
        implementation_capacity = _scale(capacities[rid][0], months)
        role_results.append({"role_id": rid, "name": role["name"], "skills": list(role["skills"]),
                             "one_time": one, "monthly_maintenance": maintenance,
                             "implementation_capacity_over_horizon": _encode(implementation_capacity),
                             "monthly_maintenance_capacity": _encode(capacities[rid][1]),
                             "implementation_capacity_status": _capacity(one_v, implementation_capacity),
                             "maintenance_capacity_status": _capacity(maintenance_v, capacities[rid][1]),
                             "capacity_assumption_ids": list(role["assumption_ids"])})
    rec_results = []
    for rid in order:
        rec = recs[rid]
        linked = [r for r in rows if rid in r["recommendation_ids"]]
        rec_results.append({**rec, "dependencies": list(rec["dependencies"]),
                            "activity_ids": [r["activity_id"] for r in linked],
                            "shared_activity_ids": [r["activity_id"] for r in linked if len(r["recommendation_ids"]) > 1]})
    combined = None if one_values is None or recurring_values is None else _sum([one_values, _scale(recurring_values, months)])
    return {"schema": "uiowa.resource-estimate/v1", "plan_id": plan["plan_id"],
            "title": plan["title"], "evidence_class": plan["evidence_class"],
            "planning_months": months, "estimate_status": "INCOMPLETE" if unscoped or any(v is None for v in values.values()) else "COMPLETE_INPUTS",
            "interpretation": "Conditional low/central/high scenarios; not confidence intervals, actual staffing, maturity scores, spend approval, or delivery dates.",
            "recurrence_assumption": "Maintenance occurs in every planning month; capacity pools for implementation and maintenance must be disjoint net allocations.",
            "shared_activity_rule": "Each activity ID is counted once at plan/role level; recommendation links do not allocate or multiply its effort.",
            "one_time": once, "monthly_maintenance": recurring,
            "horizon_maintenance_hours": _encode(_scale(recurring_values, months)),
            "horizon_total_hours": _encode(combined),
            "by_kind": {kind: subtotal([r for r in rows if r["kind"] == kind])[0] for kind in KINDS},
            "roles": role_results, "recommendations": rec_results, "activities": rows,
            "recommendations_without_activities": [r["id"] for r in rec_results if not r["activity_ids"]],
            "assumptions": [dict(a) for a in assumptions.values()]}


def _cell(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", "<br>").replace("`", "&#96;")


def _display(value):
    return "UNKNOWN" if value is None else " / ".join(value[p] for p in POINTS)


def markdown(report):
    lines = ["# Resource and adoption estimate", "", f"**{_cell(report['title'])} — {_cell(report['evidence_class'])}**", "",
             report["interpretation"], "", "All ranges are **low / central / high person-hours**.", "",
             f"One-time total: **{_display(report['one_time']['total_hours'])}**; known subtotal: {_display(report['one_time']['known_hours'])}.",
             f"Monthly maintenance: **{_display(report['monthly_maintenance']['total_hours'])}**; known subtotal: {_display(report['monthly_maintenance']['known_hours'])}.",
             f"Over {report['planning_months']} planning months, total one-time plus recurring: **{_display(report['horizon_total_hours'])}**.", "",
             report["recurrence_assumption"], "", report["shared_activity_rule"], "",
             "## Skill and capacity view", "", "| Role | One-time hours | Monthly maintenance | Implementation capacity status | Maintenance capacity status |", "|---|---|---|---|---|"]
    for r in report["roles"]:
        lines.append("| " + " | ".join(_cell(x) for x in (r["name"], _display(r["one_time"]["total_hours"]), _display(r["monthly_maintenance"]["total_hours"]), r["implementation_capacity_status"], r["maintenance_capacity_status"])) + " |")
    for r in report["roles"]:
        lines += ["", f"**{_cell(r['name'])}**: skills: {_cell(', '.join(r['skills']))}.",
                  f"Implementation capacity across the horizon: {_display(r['implementation_capacity_over_horizon'])} person-hours; maintenance capacity: {_display(r['monthly_maintenance_capacity'])} person-hours/month.",
                  f"Capacity assumptions: {_cell(', '.join(r['capacity_assumption_ids']))}."]
    if report["recommendations_without_activities"]:
        lines += ["", "**Unscoped recommendations:** " + _cell(', '.join(report['recommendations_without_activities'])) + ". Complete totals are UNKNOWN until these are assessed."]
    lines += ["", "## Activities", "", "| Activity / recommendation IDs | Role / kind | Period | Effort hours | Assumptions / missing inputs |", "|---|---|---|---|---|"]
    for r in report["activities"]:
        lines.append("| " + " | ".join(_cell(x) for x in (r["activity_id"] + " / " + ", ".join(r["recommendation_ids"]), r["role_id"] + " / " + r["kind"], r["period"], _display(r["effort_hours"]), ", ".join(r["assumption_ids"]) + " / " + (", ".join(r["missing_inputs"]) or "none"))) + " |")
    lines += ["", "## Adoption and traceability", ""]
    for rec in report["recommendations"]:
        lines += [f"### {_cell(rec['id'])}: {_cell(rec['title'])}",
                  f"Group/area: {_cell(rec['group_id'])} / {_cell(rec['area'])}. Prerequisites: {_cell(', '.join(rec['dependencies']) or 'none')}.",
                  f"Adoption: {_cell(rec['adoption_notes'])}", f"Evidence to collect later: {_cell(rec['success_evidence'])}",
                  f"Activities: {_cell(', '.join(rec['activity_ids']) or 'NONE — effort not assessed')}. Shared: {_cell(', '.join(rec['shared_activity_ids']) or 'none')}.", ""]
    lines += ["## Assumption register", ""]
    for a in report["assumptions"]:
        lines.append(f"- **{_cell(a['id'])}**: {_cell(a['text'])} Source: {_cell(a['source'])}")
    return "\n".join(lines) + "\n"


def activity_csv(report):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["activity_id", "description", "recommendation_ids", "role_id", "kind", "period", "unit_label", "units_low", "units_central", "units_high", "hours_per_unit_low", "hours_per_unit_central", "hours_per_unit_high", "effort_low", "effort_central", "effort_high", "assumption_ids", "missing_inputs"])
    def safe(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
    for r in report["activities"]:
        fields = [r["activity_id"], r["description"], ";".join(r["recommendation_ids"]), r["role_id"], r["kind"], r["period"], r["unit_label"]]
        for name in ("units", "hours_per_unit", "effort_hours"):
            fields += ["" if r[name] is None else r[name][p] for p in POINTS]
        fields += [";".join(r["assumption_ids"]), ";".join(r["missing_inputs"])]
        writer.writerow([safe(v) for v in fields])
    return output.getvalue()


def apply_activity_csv(plan, text):
    """Overlay only quantity/unit-effort cells; keep all source-plan metadata.

    The exported CSV is still not a complete plan representation. Noneditable
    display cells must match its supplied base; derived effort is recomputed.
    """
    base = list(csv.reader(io.StringIO(activity_csv(estimate(plan)), newline=""), strict=True))
    incoming = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    header = base[0]
    if not incoming or incoming[0] != header:
        raise PlanError("activities CSV: expected the exact exported header and column order")
    # Spreadsheet formula protection can make two distinct native IDs display
    # identically. Do not guess which activity a row was intended to update.
    original = {}
    for activity, row in zip(plan["activities"], base[1:]):
        if row[0] in original:
            raise PlanError("activities CSV: ambiguous spreadsheet activity ID; edit the JSON plan instead")
        original[row[0]] = (activity, row)
    edited = copy.deepcopy(plan)
    activities = {r["id"]: r for r in edited["activities"]}
    editable = {header.index(f"{field}_{point}") for field in ("units", "hours_per_unit") for point in POINTS}
    seen, changes = set(), []
    for line, row in enumerate(incoming[1:], 2):
        if len(row) != len(header):
            raise PlanError(f"activities CSV row {line}: wrong column count")
        key = row[0]
        if key not in original or key in seen:
            raise PlanError(f"activities CSV row {line}: unknown or duplicate activity ID {key!r}")
        seen.add(key)
        activity, old = original[key]
        for index, name in enumerate(header):
            if index not in editable and row[index] != old[index]:
                raise PlanError(f"{activity['id']}.{name}: read-only CSV column changed; edit the source JSON for metadata")
        for field in ("units", "hours_per_unit"):
            cells = [row[header.index(f"{field}_{point}")].strip() for point in POINTS]
            if any(not value for value in cells) and not all(not value for value in cells):
                raise PlanError(f"{activity['id']}.{field}: all three points must be supplied or all blank for UNKNOWN")
            value = None if not any(cells) else dict(zip(POINTS, cells))
            normalized = _encode(_range(value, f"{activity['id']}.{field}"))
            previous = _encode(_range(activity[field], f"{activity['id']}.{field}"))
            if normalized != previous:
                activities[activity["id"]][field] = normalized
                changes.append({"activity_id": activity["id"], "field": field,
                                "before": previous, "after": normalized})
    if seen != set(original):
        raise PlanError("activities CSV: missing activity rows: " + ", ".join(sorted(set(original) - seen)))
    estimate(edited)  # Reuse the complete original contract before publication.
    return edited, sorted(changes, key=lambda x: (x["activity_id"], x["field"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Human-edited plan JSON")
    source.add_argument("--demo", choices=("release", "security", "reliability"))
    parser.add_argument("--activities-csv", type=Path,
                        help="Edited exported activity CSV; overlays only units/hour-per-unit ranges on --input")
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory; existing paths are never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.activities_csv and not args.input:
            raise PlanError("--activities-csv requires the original --input JSON plan")
        if args.demo:
            from example_plans import make_plan
            plan = make_plan(args.demo)
        else:
            source_bytes = args.input.read_bytes()
            plan = load_json(source_bytes.decode("utf-8"))
        if args.activities_csv:
            with args.activities_csv.open("rb") as handle:
                csv_bytes = handle.read(2 * 1024 * 1024 + 1)
            if len(csv_bytes) > 2 * 1024 * 1024:
                raise PlanError("activities CSV exceeds 2 MiB")
            plan, changes = apply_activity_csv(plan, csv_bytes.decode("utf-8-sig"))
        report = estimate(plan)
        # Render everything before creating output; invalid plans leave no directory.
        files = {"input.json": json.dumps(plan, ensure_ascii=False, indent=2, default=str) + "\n",
                 "estimate.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                 "activities.csv": activity_csv(report), "estimate.md": markdown(report)}
        if args.activities_csv:
            receipt = {"schema": "uiowa.resource-activity-edit/v1", "plan_id": plan["plan_id"],
                       "source_input_sha256": hashlib.sha256(source_bytes).hexdigest(),
                       "edited_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
                       "updated_input_sha256": hashlib.sha256(files["input.json"].encode("utf-8")).hexdigest(),
                       "changes": changes, "note": "Numeric overlay on supplied source plan; not evidence or approval."}
            files["activity-edits.json"] = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for name, content in files.items():
            (args.output_dir / name).write_text(content, encoding="utf-8", newline="")
        if args.activities_csv:
            (args.output_dir / "source-input.json").write_bytes(source_bytes)
        print(f"{report['plan_id']}: {report['estimate_status']}; output={args.output_dir}")
        return 0
    except (PlanError, OSError, UnicodeError, csv.Error) as exc:
        print(f"Resource estimate failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
