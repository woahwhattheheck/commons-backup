"""Reproduce the retained UIOWA-049 joint-assumption decision experiment.

Runs the existing calculator on its existing fictional register. This analysis
does not change that calculator, estimate effort, or assign probabilities.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
from itertools import combinations, product
import json
from pathlib import Path
import sys

from revenue.uiowa_rfq_18649_debt.model import analyze, canonical, load_register

OPERATION = "uiowa-049-joint-scenarios-heliotrope-20260919"
SOURCE_BLOBS = {
    "model.py": "a36e01416f7f6eebad420e5b7d9705fb22fdd368",
    "examples/synthetic-register.json": "856618996c6f5b51a6ee8dc37e518d22074b4439",
}
DIMENSIONS = tuple((item, field) for item in ("AUTOMATE", "RETRY", "SYNC")
                   for field in ("weekly_support_hours", "reduction_pct"))
CAPACITIES = (32, 40, 50, 52)
OBJECTIVES = ("conservative", "optimistic")
HORIZON = 12


def digest(value):
    return hashlib.sha256(canonical(value) + b"\n").hexdigest()


def source_register():
    folder = Path(__file__).resolve().parents[1] / "uiowa_rfq_18649_debt"
    for name, wanted in SOURCE_BLOBS.items():
        data = (folder / name).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != wanted:
            raise ValueError(f"refresh the analysis for changed source {name}: {actual}")
    return load_register((folder / "examples/synthetic-register.json").read_bytes())


def refinement(original, bits):
    changed = deepcopy(original)
    original_rows = {row["id"]: row for row in original["items"]}
    rows = {row["id"]: row for row in changed["items"]}
    for (item, field), bit in zip(DIMENSIONS, bits):
        value = original_rows[item][field]["high" if bit else "low"]
        rows[item][field] = {"low": value, "high": value}
    # RETRY and REPLACE describe the same workload, so change that rate together.
    rows["REPLACE"]["weekly_support_hours"] = dict(rows["RETRY"]["weekly_support_hours"])
    allowed = set(DIMENSIONS) | {("REPLACE", "weekly_support_hours")}
    if changed.keys() != original.keys() or changed["schema"] != original["schema"] or changed["evidence_class"] != original["evidence_class"]:
        raise ValueError("register identity changed during refinement")
    for item, row in rows.items():
        before = original_rows[item]
        for field, value in row.items():
            if (item, field) in allowed:
                bounds = before[field]
                if not bounds["low"] <= value["low"] <= value["high"] <= bounds["high"]:
                    raise ValueError(f"refinement outside original bounds: {item}.{field}")
            elif value != before[field]:
                raise ValueError(f"non-assumption field changed: {item}.{field}")
    return changed


def feasible_sets(register, capacity):
    """Expose the decision cohort's admissible sets, without scoring them."""
    rows = {row["id"]: row for row in register["items"]}
    known = sorted(key for key, row in rows.items() if all(row[field] is not None
                   for field in ("effort_hours", "weekly_support_hours", "reduction_pct")))
    result = []
    for size in range(len(known) + 1):
        for ids in combinations(known, size):
            selected = set(ids)
            if any(not set(rows[key]["dependencies"]) <= selected for key in ids):
                continue
            if sum(rows[key]["effort_hours"]["high"] for key in ids) > capacity:
                continue
            groups = [[rows[key][field] for key in ids if rows[key][field] is not None]
                      for field in ("benefit_pool", "alternative_group")]
            if any(len(values) != len(set(values)) for values in groups):
                continue
            result.append(list(ids))
    return sorted(result)


def projected_report(report):
    return {field: report[field] for field in
            ("parameters", "register_sha256", "report_sha256", "search", "portfolios")}


def hundredths(value):
    sign = -1 if value.startswith("-") else 1
    whole, fraction = value.lstrip("-").split(".")
    return sign * (100 * int(whole) + int(fraction))


def hours(value):
    return f"{'-' if value < 0 else ''}{abs(value) // 100}.{abs(value) % 100:02d}"


def run():
    original = source_register()
    baseline = {capacity: analyze(original, capacity, HORIZON) for capacity in CAPACITIES}
    feasible = {capacity: feasible_sets(original, capacity) for capacity in CAPACITIES}
    results, full_reports = [], []
    frequencies = {capacity: {objective: Counter() for objective in OBJECTIVES} for capacity in CAPACITIES}
    witness_report = None
    for bits in product((0, 1), repeat=len(DIMENSIONS)):
        register = refinement(original, bits)
        corner = "".join(str(bit) for bit in bits)
        row = {"corner": corner, "reports": []}
        for capacity in CAPACITIES:
            actual_feasible = feasible_sets(register, capacity)
            if actual_feasible != feasible[capacity]:
                raise ValueError(f"feasible-set membership changed at {corner}/{capacity}")
            report = analyze(register, capacity, HORIZON)
            if report["search"]["feasible_portfolios"] != len(actual_feasible):
                raise ValueError(f"calculator feasible count differs at {corner}/{capacity}")
            full_reports.append(report)
            row["reports"].append(projected_report(report))
            for objective in OBJECTIVES:
                selected = report["portfolios"][objective]
                frequencies[capacity][objective][tuple(selected["ids"])] += 1
            if corner == "110000" and capacity == 32:
                witness_report = report
        results.append(row)
    if witness_report is None:
        raise RuntimeError("mixed-assumption witness was not produced")
    old_ids = baseline[32]["portfolios"]["conservative"]["ids"]
    modeled = {row["id"]: row["modeled"] for row in witness_report["items"]}
    old_range = {bound: hours(sum(hundredths(modeled[key][f"net_hours_{bound}"]) for key in old_ids))
                 for bound in ("low", "high")}
    data = {
        "schema": "tjlabs.technical-debt-joint-assumptions/v1",
        "operation": OPERATION,
        "evidence_class": "SYNTHETIC",
        "source_blobs": SOURCE_BLOBS,
        "horizon_weeks": HORIZON,
        "capacities": list(CAPACITIES),
        "dimensions": [{"item": item, "field": field,
                        **next(row[field] for row in original["items"] if row["id"] == item)}
                       for item, field in DIMENSIONS],
        "shared_workload": "REPLACE.weekly_support_hours always equals RETRY.weekly_support_hours",
        "corner_count": len(results),
        "calculator_runs": len(full_reports),
        "full_reports_sha256": digest(full_reports),
        "serialization": "canonical sorted-key compact ASCII JSON followed by one LF",
        "baseline": [projected_report(baseline[capacity]) for capacity in CAPACITIES],
        "feasible_sets": [{"capacity": capacity, "count": len(feasible[capacity]),
                           "ids": feasible[capacity], "sha256": digest(feasible[capacity])}
                          for capacity in CAPACITIES],
        "witness": {"corner": "110000", "capacity": 32,
                    "report": projected_report(witness_report),
                    "former_portfolio": {"ids": old_ids, "net_hours_low": old_range["low"],
                                         "net_hours_high": old_range["high"]}},
        "selection_counts": [{"capacity": capacity, "objective": objective,
                              "portfolios": [{"ids": list(ids), "corners": count}
                                             for ids, count in sorted(frequencies[capacity][objective].items())]}
                             for capacity in CAPACITIES for objective in OBJECTIVES],
        "corners": results,
        "limits": ["All assumptions are fictional; no University findings or measured savings.",
                   "Corner counts are not probabilities.",
                   "Six benefit dimensions are narrowed; effort and all other assumptions remain unchanged.",
                   "The finite corner experiment is not an exhaustive robustness proof over continuous intervals.",
                   "Projected reports retain actual selected outputs and full-report digests; the replay regenerates full reports."],
    }
    data["artifact_sha256"] = digest(data)
    return data


def label(ids):
    return " + ".join(ids) if ids else "none"


def markdown(data):
    witness = data["witness"]
    selected = witness["report"]["portfolios"]["conservative"]
    old = witness["former_portfolio"]
    lines = [
        "# UIOWA-049 — joint assumptions can overturn endpoint agreement", "",
        "**SYNTHETIC demonstration.** Actual runs of the existing calculator on fictional assumptions; no University findings, measured savings, investment approval or staffing commitment.", "",
        "Continuation of [issue #16302](https://github.com/woahwhattheheck/commons/issues/16302) and the [existing decision readout](README.md).", "",
        "## The retained counterexample", "",
        "At 32 implementation hours and 12 weeks, the original lower- and upper-endpoint objectives both select BASE + RETRY + SYNC, with net support-hour endpoints 42.00–120.00. Agreement at those two objectives does not establish that the same portfolio wins for every simultaneous realization inside the stated intervals.", "",
        "Narrow AUTOMATE to 10 weekly support hours and 80% reduction, RETRY to 8 hours and 50%, and SYNC to 6 hours and 50%. REPLACE shares RETRY's workload, so its weekly rate also becomes 8. Every change stays inside the original interval; effort, delays, dependencies, exclusions, evidence labels and capacity remain unchanged.", "",
        f"Under this refinement both objectives select **{label(selected['ids'])}**, using **{selected['effort_hours_high']} upper-effort hours**, with net support-hour endpoints **{selected['net_hours_low']}–{selected['net_hours_high']}**. The former {label(old['ids'])} portfolio becomes **{old['net_hours_low']}–{old['net_hours_high']}**. Its feasible status did not change; its benefit assumptions did.", "",
        "## The simultaneous-assumption experiment", "",
        "Each bit selects the original low (0) or high (1) endpoint and narrows that interval to the selected value. Bit order is AUTOMATE weekly rate, AUTOMATE reduction, RETRY weekly rate, RETRY reduction, SYNC weekly rate, SYNC reduction. REPLACE's weekly rate follows RETRY's in every corner. Other intervals remain unchanged.", "",
        "All 64 corners were run at capacities 32, 40, 50 and 52, each at 12 weeks: **256 new calculator runs**. Four original-register baseline runs provide comparison. The full feasible portfolio membership at each capacity is identical in all 64 refinements; membership, counts and digests are published in the JSON.", "",
        "### Selected portfolios across the 64 corners", "",
        "| Capacity | Objective | Selected portfolio | Corners |", "|---:|---|---|---:|",
    ]
    for group in data["selection_counts"]:
        for row in group["portfolios"]:
            lines.append(f"| {group['capacity']} | {group['objective']} | {label(row['ids'])} | {row['corners']} |")
    lines += ["", "Counts describe this chosen finite experiment. They are **not probabilities**, likelihoods, confidence levels or estimates of how frequently a portfolio will be best. The experiment does not cover every point in continuous intervals, every effort realization, or every other register assumption.", "",
              "### Read every corner", "",
              "The table gives conservative / optimistic selections. A single selection means both objectives agree. The JSON retains each selected portfolio's effort and support-hour bounds plus register and full-report digests.", "",
              "| Corner | Capacity 32 | Capacity 40 | Capacity 50 | Capacity 52 |", "|---|---|---|---|---|"]
    for row in data["corners"]:
        cells = []
        for report in row["reports"]:
            names = [label(report["portfolios"][objective]["ids"]) for objective in OBJECTIVES]
            cells.append(names[0] if names[0] == names[1] else " / ".join(names))
        lines.append("| " + " | ".join([row["corner"], *cells]) + " |")
    lines += ["", "## Replay and retained outputs", "",
              "Run from a checkout containing the unchanged calculator and register:", "", "```bash",
              "python -m revenue.uiowa_rfq_18649_debt_decision_readout.joint_assumptions",
              "python -m revenue.uiowa_rfq_18649_debt_decision_readout.joint_assumptions --json",
              "```", "",
              "The default command emits this readout. `--json` emits the published result structure; `--output-dir NEW_DIRECTORY` writes both files in a new directory. Failures exit nonzero with a diagnosis. This is the analysis itself, not a test suite or a replacement solver.", "",
              "The replay validates the exact input blobs, bounds of every narrowing, unchanged non-assumption fields, shared workload consistency, identical feasible-set membership, and the actual calculator's feasible count. It then retains all 256 raw reports in deterministic corner/capacity order for their complete digest. The checked-in JSON projects the named output fields to avoid duplicating the unchanged item prose 256 times.", "",
              "| Source | Git blob |", "|---|---|",
              *[f"| `{name}` | `{value}` |" for name, value in SOURCE_BLOBS.items()], "",
              f"Original 32-hour report: `{data['baseline'][0]['report_sha256']}`.", "",
              f"Mixed-refinement report: `{witness['report']['report_sha256']}`.", "",
              f"Complete ordered 256-report JSON plus LF SHA-256: `{data['full_reports_sha256']}`.", "",
              f"Projected artifact payload plus LF SHA-256, excluding its own `artifact_sha256` field: `{data['artifact_sha256']}`.", "",
              "[Published machine-readable outputs](joint_assumptions.json). Hashes use sorted-key compact ASCII JSON plus one final LF, except the calculator's original `report_sha256` fields, which retain its own serialization contract.", "",
              "The original calculator and original decision sweep remain the source of their earlier results. This continuation supplies the previously requested joint-assumption counterexample and finite experiment. It does not establish live institutional validation, universal stability, actual savings or payment."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--json", action="store_true", help="print the actual output projection")
    mode.add_argument("--output-dir", type=Path, help="write the readout and outputs in a new directory")
    args = parser.parse_args()
    try:
        data = run()
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=False)
            (args.output_dir / "JOINT_ASSUMPTIONS.md").write_text(markdown(data), encoding="utf-8")
            (args.output_dir / "joint_assumptions.json").write_bytes(canonical(data) + b"\n")
            print(f"{data['calculator_runs']} joint scenarios plus four baseline runs completed; outputs: {args.output_dir}")
            print(f"Full reports SHA-256: {data['full_reports_sha256']}")
        elif args.json:
            sys.stdout.buffer.write(canonical(data) + b"\n")
        else:
            print(markdown(data), end="")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Joint assumption analysis failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
