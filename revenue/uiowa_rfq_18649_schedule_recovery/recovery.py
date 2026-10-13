#!/usr/bin/env python3
"""UIOWA-134: offline workday scenarios over UIOWA-002 staffing exports."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from engine import EPS, ROLES, Edge, Task, load_profile, number, role_values, schedule

HERE = Path(__file__).resolve().parent
EXPECTED_IDS = {f"A{i:02d}" for i in range(1, 17)}
PAYMENTS = (
    ("authorization_kickoff", 9600, "Written authorization and kickoff", "A02"),
    ("qualifying_draft", 9600, "Qualifying draft delivered under the proposed criteria", "DRAFT"),
    ("written_final_acceptance", 4800, "Written final acceptance", "FINAL"),
)


def validate_plan(plan: object) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("staffing plan must be an object")
    if type(plan.get("target_weeks")) is not int or plan["target_weeks"] not in (6, 8):
        raise ValueError("target_weeks must be integer 6 or 8")
    if plan.get("status") != "PROPOSED_PLANNING_ONLY" or plan.get("scheduling_authority") is not False:
        raise ValueError("source must be a proposed planning-only staffing export")
    assumptions = plan.get("assumptions")
    if not isinstance(assumptions, dict):
        raise ValueError("source assumptions required")
    for field in ("evidence_delay_weeks", "review_delay_weeks"):
        if type(assumptions.get(field)) is not int or assumptions[field] != 0:
            raise ValueError("use an undelayed staffing export; apply delays once in this adapter")
    rows = plan.get("tasks")
    if not isinstance(rows, list) or len(rows) != 16 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("the A01-A16 source task set is required")
    if {row.get("id") for row in rows} != EXPECTED_IDS:
        raise ValueError("the source task IDs must be exactly A01-A16")
    for row in rows:
        for key in ("start_week", "end_week"):
            if type(row.get(key)) is not int:
                raise ValueError(f"{row['id']}.{key}: integer required")
        if not 1 <= row["start_week"] <= row["end_week"] <= plan["target_weeks"]:
            raise ValueError("source task window must fit the baseline")
        role_values(row.get("hours"), f"{row['id']}.hours")
        if not isinstance(row.get("activity"), str) or not isinstance(row.get("package"), str):
            raise ValueError("source activity and package required")
    coord = next(row for row in rows if row["id"] == "A16")
    if coord["start_week"] != 1 or coord["end_week"] != plan["target_weeks"]:
        raise ValueError("A16 coordination must span the entire source baseline")
    totals = role_values(plan.get("totals"), "source totals")
    for r in ROLES:
        if abs(totals[r]-sum(row["hours"][r] for row in rows)) > EPS:
            raise ValueError(f"source hours do not reconcile for {r}")
        number(assumptions.get(f"{r.lower()}_capacity"), f"{r}.capacity", positive=True)
    return plan


def validate_case(case: object) -> dict:
    required = {"id", "label", "interview_delay_days", "evidence_delay_days", "comment_delay_days", "extra_hours"}
    optional = {"recovery", "requires", "compared_to", "post_delivery_days", "recovery_window_days"}
    if not isinstance(case, dict) or required-set(case) or set(case)-required-optional:
        raise ValueError("invalid scenario fields")
    if not all(isinstance(case[k], str) and case[k] for k in ("id", "label")):
        raise ValueError("scenario id and label required")
    for key in ("interview_delay_days", "evidence_delay_days", "comment_delay_days"):
        if case[key] is not None:
            number(case[key], key)
    if not isinstance(case["extra_hours"], dict) or set(case["extra_hours"])- (EXPECTED_IDS-{"A16"}):
        raise ValueError("extra hours must reference A01-A15")
    for key, values in case["extra_hours"].items():
        role_values(values, f"extra_hours.{key}")
    mode = case.get("recovery")
    if mode not in (None, "rolling_synthesis", "rolling_evidence", "review_surge"):
        raise ValueError("unknown recovery option")
    if mode and (not isinstance(case.get("requires"), list) or not case["requires"] or
                 any(not isinstance(s, str) or not s.strip() for s in case["requires"])):
        raise ValueError("a recovery option requires explicit confirmation conditions")
    if "compared_to" in case and (not isinstance(case["compared_to"], str) or not case["compared_to"]):
        raise ValueError("comparison scenario ID must be a nonempty string")
    if mode == "rolling_evidence":
        number(case.get("post_delivery_days"), "post_delivery_days", positive=True)
    elif "post_delivery_days" in case:
        raise ValueError("post_delivery_days applies only to rolling_evidence")
    if mode == "review_surge":
        number(case.get("recovery_window_days"), "recovery_window_days", positive=True)
    elif "recovery_window_days" in case:
        raise ValueError("recovery_window_days applies only to review_surge")
    return case


def analyze(plan: dict, case: dict, rates: dict) -> dict:
    validate_plan(plan)
    validate_case(case)
    rates = role_values(rates, "hourly cost assumptions", nullable=True)
    source = {row["id"]: row for row in plan["tasks"]}
    target = plan["target_weeks"]*5
    starts = {key: (r["start_week"]-1)*5 for key, r in source.items()}
    durations = {key: (r["end_week"]-r["start_week"]+1)*5 for key, r in source.items()}
    mode = case.get("recovery")
    if mode == "review_surge":
        durations["A14"] = durations["A15"] = case["recovery_window_days"]
    tasks = [Task(key, durations[key], starts[key], source[key]["activity"])
             for key in sorted(source) if key != "A16"]
    for gate, field, activity in (("INTERVIEWS", "interview_delay_days", "A06"),
                                  ("EVIDENCE", "evidence_delay_days", "A08")):
        delay = case[field]
        tasks.append(Task(gate, 0, None if delay is None else starts[activity]+delay,
                          f"Assumed {gate.lower()} input availability"))
    tasks.extend([Task("DRAFT", 0, 0, "Potential qualifying draft ready"),
                  Task("COMMENTS", 0, None if case["comment_delay_days"] is None else 0,
                       "Assumed consolidated comments available"),
                  Task("FINAL", 0, 0, "Final artifacts ready; written acceptance unverified")])
    edges = []

    def add(a, b, relation="FS", lag=0, reason=""):
        edges.append(Edge(a, b, relation, lag, reason))

    def rolling(a, b):
        lag = max(0, starts[b]-starts[a])
        add(a, b, "SS", lag, "Rolling work offset from the source planning windows")
        add(a, b, "FF", 0, "Successor cannot complete before its evidence source")

    add("INTERVIEWS", "A06", reason="Interview work waits for the assumed availability window")
    rolling("A06", "A07")
    rolling("A07", "A08")
    add("A03", "A08", "FF", reason="Matrix completion waits for intake completion")
    add("EVIDENCE", "A08", "FF" if mode == "rolling_evidence" else "FS",
        lag=case["post_delivery_days"] if mode == "rolling_evidence" else 0,
        reason="Explicit reconciliation time follows complete input delivery before matrix closure" if mode == "rolling_evidence"
        else "Conservative baseline waits for the complete input tranche before matrix work")
    if mode == "rolling_synthesis":
        add("A08", "A09", "FF", reason="Provisional synthesis may start early but cannot close before the matrix")
    else:
        rolling("A08", "A09")
    rolling("A09", "A11")
    for key in ("A09", "A10", "A11"):
        add(key, "DRAFT", reason="All proposed draft components must be ready")
    for key in ("A12", "A13"):
        add("DRAFT", key, reason="Consolidated review follows the proposed draft")
        add(key, "COMMENTS", lag=case["comment_delay_days"] or 0,
            reason="Assumed comment wait begins after review, not at a fixed calendar date")
    add("COMMENTS", "A14", reason="Corrections wait for consolidated comments")
    rolling("A14", "A15")
    for key in sorted(source):
        if key != "A16":
            add(key, "FINAL", reason="Final readiness requires every production work package")
    result = schedule(tasks, edges)
    hours = {key: {r: row["hours"][r]+case["extra_hours"].get(key, {}).get(r, 0) for r in ROLES}
             for key, row in source.items() if key != "A16"}
    coord_rate = {r: source["A16"]["hours"][r]/target for r in ROLES}
    finish = result["finish"]
    result["tasks"]["A16"] = {"id": "A16", "label": source["A16"]["activity"], "start": 0 if finish is not None else None,
                                "finish": finish, "duration": finish, "unknown_inputs": [] if finish is not None else ["FINAL"],
                                "drivers": [{"predecessor": "FINAL", "reason": "Coordination continues through final readiness"}],
                                "float_days": None}
    noncoord = {r: sum(h[r] for h in hours.values()) for r in ROLES}
    if finish is not None:
        hours["A16"] = {r: coord_rate[r]*finish for r in ROLES}
        totals = {r: noncoord[r]+hours["A16"][r] for r in ROLES}
        costs = {r: None if rates[r] is None else totals[r]*rates[r] for r in ROLES}
    else:
        totals = {r: None for r in ROLES}
        costs = {r: None for r in ROLES}
    capacities = {r: plan["assumptions"][f"{r.lower()}_capacity"] for r in ROLES}
    profile = load_profile(result["tasks"], hours, capacities)
    if finish is None:
        profile["unscheduled_tasks"].append("A16")
    milestones = [{"id": key, "proposed_amount_usd": amount, "trigger": trigger,
                   "artifact_readiness_day": result["tasks"][task]["finish"],
                   "trigger_status": "NOT_VERIFIED", "actual_trigger_day": None,
                   "invoice_earned": False, "paid": False}
                  for key, amount, trigger, task in PAYMENTS]
    return {"schema_version": 1, "id": case["id"], "label": case["label"], "target_weeks": plan["target_weeks"],
            "status": "HYPOTHETICAL_PLANNING_ONLY", "scheduling_authority": False,
            "requires_confirmation": case.get("requires", []), "compared_to": case.get("compared_to", "baseline"),
            "case_assumptions": case, "schedule": result, "hours": hours,
            "known_noncoordination_hours": noncoord, "total_hours": totals,
            "cost_rates_usd_per_hour": rates, "labor_cost_usd_by_role": costs,
            "unpriced_roles": [r for r in ROLES if rates[r] is None],
            "capacity": profile, "milestones": milestones,
            "dependencies": [{"from": e.predecessor, "to": e.successor, "relation": e.relation,
                              "lag": e.lag, "reason": e.reason} for e in edges]}


def compare(result: dict, baseline: dict) -> dict:
    rows, base = result["schedule"]["tasks"], baseline["schedule"]["tasks"]
    unchanged, shifted, unknown = [], [], []
    for key in sorted(EXPECTED_IDS):
        if rows[key]["finish"] is None or base[key]["finish"] is None:
            unknown.append(key)
        elif all(abs(rows[key][x]-base[key][x]) < EPS for x in ("start", "finish")):
            unchanged.append(key)
        else:
            shifted.append({"task": key, "start_shift": rows[key]["start"]-base[key]["start"],
                            "finish_shift": rows[key]["finish"]-base[key]["finish"], "drivers": rows[key]["drivers"]})
    f, b = result["schedule"]["finish"], baseline["schedule"]["finish"]
    delta_hours = {r: None if result["total_hours"][r] is None else result["total_hours"][r]-baseline["total_hours"][r] for r in ROLES}
    costs, bc = result["labor_cost_usd_by_role"], baseline["labor_cost_usd_by_role"]
    delta_costs = {r: None if costs[r] is None or bc[r] is None else costs[r]-bc[r] for r in ROLES}
    rc, cb = result["schedule"]["critical_tasks"], baseline["schedule"]["critical_tasks"]
    return {"finish_shift_days": None if f is None or b is None else f-b,
            "unchanged_tasks": unchanged, "shifted_tasks": shifted, "unknown_tasks": unknown,
            "extra_hours_by_role": delta_hours, "extra_labor_cost_usd_by_role": delta_costs,
            "critical_tasks_added": None if rc is None or cb is None else sorted(set(rc)-set(cb)),
            "critical_tasks_removed": None if rc is None or cb is None else sorted(set(cb)-set(rc))}


def build_suite(source: object, config: object) -> list[dict]:
    plans = source.get("plans") if isinstance(source, dict) else source
    if not isinstance(plans, list) or {p.get("target_weeks") for p in plans if isinstance(p, dict)} != {6, 8} or len(plans) != 2:
        raise ValueError("one six-week and one eight-week staffing plan required")
    if not isinstance(config, dict) or set(config) != {"rates_usd_per_hour", "scenarios", "assumption_note"}:
        raise ValueError("invalid scenario configuration")
    if not isinstance(config["assumption_note"], str) or not config["assumption_note"].strip():
        raise ValueError("a nonempty assumption note is required")
    cases = config["scenarios"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("scenarios required")
    for c in cases:
        validate_case(c)
    if len({c["id"] for c in cases}) != len(cases) or cases[0]["id"] != "baseline":
        raise ValueError("unique scenarios with baseline first required")
    base = cases[0]
    if any(base[k] != 0 for k in ("interview_delay_days", "evidence_delay_days", "comment_delay_days")) or base["extra_hours"] or base.get("recovery"):
        raise ValueError("baseline must have zero delays, no extra hours and no recovery")
    results = []
    for plan in sorted(plans, key=lambda p: p["target_weeks"]):
        group = [analyze(plan, c, config["rates_usd_per_hour"]) for c in cases]
        # Refuse incompatible new source windows rather than silently rewriting them.
        for task in plan["tasks"]:
            row = group[0]["schedule"]["tasks"][task["id"]]
            if row["start"] != (task["start_week"]-1)*5 or row["finish"] != task["end_week"]*5:
                raise ValueError(f"baseline dependency model is incompatible with source window {task['id']}")
        for role in ROLES:
            if abs(group[0]["total_hours"][role]-plan["totals"][role]) > EPS:
                raise ValueError(f"baseline effort drift for {role}")
        by_id = {r["id"]: r for r in group}
        for r in group:
            r["assumption_note"] = config["assumption_note"]
            r["vs_baseline"] = compare(r, group[0])
            other = r["compared_to"]
            if other not in by_id:
                raise ValueError(f"unknown comparison scenario {other}")
            parent = by_id[other]
            rf, pf = r["schedule"]["finish"], parent["schedule"]["finish"]
            r["recovery_days_vs_parent"] = None if rf is None or pf is None else pf-rf
            results.append(r)
    return results


def fmt(value):
    return "UNKNOWN" if value is None else f"{value:.2f}".rstrip("0").rstrip(".")


def md(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render(results: list[dict], weeks: int) -> str:
    parts = [f"# UIOWA-134: {weeks}-week scenario calendars", "",
             "HYPOTHETICAL PLANNING ONLY. Relative working days from kickoff; day 0 is the planning origin.",
             "Five working days per relative week. No date, holiday calendar, appointment or actual availability is asserted.",
             "Intervals are [start, finish); readiness is not written acceptance, earned invoicing or payment.",
             "Uniform effort allocation is a demand view, not resource leveling. All recovery conditions need confirmation.", ""]
    for r in (x for x in results if x["target_weeks"] == weeks):
        s, d = r["schedule"], r["vs_baseline"]
        parts += [f"## {md(r['id'])}: {md(r['label'])}", "",
                  f"Final readiness: **day {fmt(s['finish'])}**; baseline shift: **{fmt(d['finish_shift_days'])} working days**.",
                  f"Known-task finish lower bound: day {fmt(s['finish_lower_bound'])}; missing inputs can extend this indefinitely.",
                  "Representative driving chain: " + (" → ".join(s["driving_chain"]) if s["driving_chain"] else "UNKNOWN") + ".",
                  "Critical tasks: " + (", ".join(s["critical_tasks"]) if s["critical_tasks"] else "UNKNOWN") + ".",
                  "Critical tasks added vs baseline: " + (", ".join(d["critical_tasks_added"]) or "none" if d["critical_tasks_added"] is not None else "UNKNOWN") + ".",
                  "Unchanged work windows: " + (", ".join(d["unchanged_tasks"]) or "none") + ".", ""]
        if r["requires_confirmation"]:
            parts += ["**Conditional recovery, not a commitment:** " + "; ".join(map(md, r["requires_confirmation"])),
                      f"Recovery vs {md(r['compared_to'])}: {fmt(r['recovery_days_vs_parent'])} working days.", ""]
        parts += ["| Task | Start | Finish | Shift in finish | Driving dependency / unknown input |",
                  "|---|---:|---:|---:|---|"]
        shifts = {x["task"]: x["finish_shift"] for x in d["shifted_tasks"]}
        for key in sorted(EXPECTED_IDS):
            row = s["tasks"][key]
            drivers = "; ".join(f"{x['predecessor'] or 'release'}: {x['reason']}" for x in row["drivers"])
            if row["unknown_inputs"]:
                drivers = "UNKNOWN: " + ", ".join(row["unknown_inputs"])
            shift = None if key in d["unknown_tasks"] else shifts.get(key, 0)
            parts.append(f"| {key} {md(row['label'])} | {fmt(row['start'])} | {fmt(row['finish'])} | {fmt(shift)} | {md(drivers)} |")
        parts += ["", "| Role | Total hours | Incremental hours | Assumed USD/hour | Incremental labor cost USD |",
                  "|---|---:|---:|---:|---:|"]
        for role in ROLES:
            parts.append(f"| {role} | {fmt(r['total_hours'][role])} | {fmt(d['extra_hours_by_role'][role])} | {fmt(r['cost_rates_usd_per_hour'][role])} | {fmt(d['extra_labor_cost_usd_by_role'][role])} |")
        parts += ["", "Costs are labor-only scenario assumptions, not quoted rates, fees, travel or tooling estimates. Unpriced roles: " + ", ".join(r["unpriced_roles"]) + ".",
                  "Capacity-overload intervals: " + str(len(r["capacity"]["overloads"])) + ". Availability remains unconfirmed."]
        for x in r["capacity"]["overloads"]:
            parts.append(f"- {x['role']} days {fmt(x['start'])}–{fmt(x['finish'])}: {fmt(x['hours_per_day'])} h/day demand versus {fmt(x['assumed_capacity_per_day'])} assumed h/day capacity.")
        parts += ["", "| Proposed trigger | Amount USD | Related artifact readiness day | Trigger verified / earned / paid |",
                  "|---|---:|---:|---|"]
        for m in r["milestones"]:
            parts.append(f"| {md(m['trigger'])} | {m['proposed_amount_usd']} | {fmt(m['artifact_readiness_day'])} | No / No / No |")
        parts += ["", "The kickoff row uses completion of the source's week-one workshop window as a readiness proxy, not an invoice date. Final readiness never supplies written acceptance.", ""]
    return "\n".join(parts)


def render_overview(results: list[dict]) -> str:
    """Compact side-by-side calendars; the detailed exports retain every driver."""
    parts = ["# Worked schedule-recovery calendars", "",
             "Synthetic planning cases, not University findings or confirmed availability.",
             "All windows are [start, finish) in relative working days from kickoff, with five workdays per week.",
             "The native staffing effort is preserved. No appointments, invoices or payment events are created.", ""]
    names = ("baseline", "late_interviews", "partial_evidence", "delayed_comments")
    for weeks in (6, 8):
        group = {r["id"]: r for r in results if r["target_weeks"] == weeks}
        parts += [f"## {weeks}-week baseline and three alternative calendars", "",
                  "| Task | Baseline | Late interviews | Partial evidence | Delayed comments |",
                  "|---|---:|---:|---:|---:|"]
        for key in sorted(EXPECTED_IDS):
            windows = []
            for name in names:
                row = group[name]["schedule"]["tasks"][key]
                windows.append(f"{fmt(row['start'])}–{fmt(row['finish'])}")
            label = group["baseline"]["schedule"]["tasks"][key]["label"]
            parts.append(f"| {key} {md(label)} | " + " | ".join(windows) + " |")
        parts += ["", "### Why these dates moved", ""]
        for name in names:
            r = group[name]; d = r["vs_baseline"]
            chain = " → ".join(r["schedule"]["driving_chain"] or [])
            unchanged = ", ".join(d["unchanged_tasks"]) or "none"
            parts.append(f"**{name}:** final readiness day {fmt(r['schedule']['finish'])}; "
                         f"driving chain {chain}. Unchanged work: {unchanged}.")
            if name != "baseline":
                added = ", ".join(d["critical_tasks_added"] or []) or "none"
                removed = ", ".join(d["critical_tasks_removed"] or []) or "none"
                parts.append(f"Critical tasks added: {added}; removed: {removed}.")
            parts.append("")
        parts += ["### Conditional recovery and effort exposure", "",
                  "| Scenario | Final day | Days recovered vs delayed parent | TJLabs hours | Added TJLabs labor USD vs baseline | Overload intervals |",
                  "|---|---:|---:|---:|---:|---:|"]
        for name, r in group.items():
            parts.append(f"| {name} | {fmt(r['schedule']['finish'])} | {fmt(r['recovery_days_vs_parent'])} | "
                         f"{fmt(r['total_hours']['TJLabs'])} | {fmt(r['vs_baseline']['extra_labor_cost_usd_by_role']['TJLabs'])} | "
                         f"{len(r['capacity']['overloads'])} |")
        parts += ["", "Recovery rows compare against their named delayed parent; ordinary delayed rows compare against baseline (negative means later).", ""]
        for name in ("recover_interviews", "recover_evidence", "recover_comments"):
            r = group[name]
            parts.append(f"**{name} requires:** " + "; ".join(map(md, r["requires_confirmation"])) + ".")
        parts += ["", "### Proposed payment triggers stay unchanged", "",
                  "| Scenario | Kickoff readiness proxy | Qualifying-draft readiness | Final-artifact readiness |",
                  "|---|---:|---:|---:|"]
        for name in names:
            parts.append(f"| {name} | " + " | ".join(fmt(m["artifact_readiness_day"]) for m in group[name]["milestones"]) + " |")
        parts += ["", "Amounts remain $9,600 at written authorization/kickoff, $9,600 for the qualifying draft, and $4,800 at written final acceptance.",
                  "All trigger verification, earned-invoice and payment fields remain unverified/false. The kickoff proxy is the source week-one workshop window's end, not an invoice date.", ""]
    parts += ["## Interpretation limits", "",
              "The illustrative cost rates are Clark $100/hour and TJLabs $80/hour; University labor is unpriced, not free. Costs exclude travel, tooling and other expenses.",
              "Overloads use exact interval demand against editable aggregate capacity. A zero-overload result does not establish real availability or a feasible resource-leveled appointment plan.",
              "An unknown complete-evidence date leaves final readiness, total coordination effort and full labor exposure UNKNOWN, while unaffected work remains visible.",
              "See the CLI-generated detailed calendars and scenarios.json for every binding dependency, critical edge, cost-by-role and overload interval.", ""]
    return "\n".join(parts)


def export(results: list[dict], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory/"WORKED_CALENDARS.md").write_text(render_overview(results), encoding="utf-8")
    (directory/"scenarios.json").write_text(json.dumps(results, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    for weeks in (6, 8):
        (directory/f"calendar-{weeks}-week.md").write_text(render(results, weeks), encoding="utf-8")
    with (directory/"summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["weeks", "scenario", "final_ready_workday", "shift_workdays", "TJLabs_hours", "TJLabs_extra_labor_usd", "overload_intervals", "actual_availability_confirmed"])
        for r in results:
            writer.writerow([r["target_weeks"], r["id"], fmt(r["schedule"]["finish"]), fmt(r["vs_baseline"]["finish_shift_days"]),
                             fmt(r["total_hours"]["TJLabs"]), fmt(r["vs_baseline"]["extra_labor_cost_usd_by_role"]["TJLabs"]),
                             len(r["capacity"]["overloads"]), False])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staffing-plans", type=Path, default=HERE/"staffing-source.json")
    parser.add_argument("--scenarios", type=Path, default=HERE/"scenario-inputs.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        source = json.loads(args.staffing_plans.read_text(encoding="utf-8"))
        config = json.loads(args.scenarios.read_text(encoding="utf-8"))
        result = build_suite(source, config)
        export(result, args.out)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"Invalid planning input: {exc}\n")
    print(f"Exported {len(result)} hypothetical cases; no appointments or payment events created.")


if __name__ == "__main__":
    main()
