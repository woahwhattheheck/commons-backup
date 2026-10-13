#!/usr/bin/env python3
"""Offline AI-workflow economics. Decimal ranges are assumptions, not probabilities.

No network, model calls, procurement, scoring, or institution findings. See README.md
for equations, units, independent-range interpretation and cash/capacity distinctions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
from pathlib import Path
from typing import Any

VERSION = "1.0"
ZERO = Decimal(0)
ONE = Decimal(1)
SIXTY = Decimal(60)
# key: (unit, real measurement that replaces the planning assumption)
FIELDS = {
    "monthly_tasks": ("tasks/month", "Count comparable eligible tasks, including unsuccessful attempts; record period and exclusions."),
    "adoption_fraction": ("fraction", "Measure the fraction of eligible tasks actually attempted with the assisted workflow."),
    "baseline_minutes": ("minutes/task", "Time the current workflow through accepted output, not first draft, for a comparable task mix."),
    "author_minutes": ("minutes/assisted task", "Record prompting, context preparation and editing; exclude checking and rework counted below."),
    "checking_minutes": ("minutes/assisted task", "Time verification of every assisted output, including discarded outputs and source checks."),
    "rework_fraction": ("fraction", "Count tasks requiring additional repair after ordinary checking; retain failed and abandoned tasks."),
    "rework_minutes": ("minutes/reworked task", "Measure extra repair or manual fallback time conditional on rework, without double counting author/checking time."),
    "attempts_per_task": ("generation attempts/task", "Count all billable attempts including retries and discarded generations."),
    "generation_cash_per_attempt": ("currency/attempt", "Use dated metered cost or a documented cost assumption covering each attempt's actual usage."),
    "loaded_hourly_rate": ("currency/hour", "Obtain an agreed aggregate loaded-labor valuation; document role mix and valuation basis."),
    "integration_hours": ("hours one-time", "Estimate and then record integration, rollout, initial evaluation and training effort."),
    "setup_cash": ("currency one-time", "Record incremental setup cash not already represented by integration labor."),
    "support_hours": ("hours/month", "Record recurring operational support and troubleshooting, excluding per-task rework."),
    "maintenance_hours": ("hours/month", "Record recurring updates, evaluation refresh and knowledge maintenance, excluding support."),
    "platform_cash": ("currency/month", "Record incremental fixed recurring cash not already included in generation costs."),
    "cash_conversion_fraction": ("fraction", "Document what fraction of the signed capacity value would actually change payroll or contractor cash; zero is not an automatic fact."),
}
ECONOMIC_FIELDS = tuple(k for k in FIELDS if k != "cash_conversion_fraction")
FRACTIONS = {"adoption_fraction", "rework_fraction", "cash_conversion_fraction"}
# These coordinates may reverse sign, so evaluate endpoints rather than assigning
# high volume/rate/conversion to the favorable corner. All other costs are monotone.
FREE_FIELDS = ("monthly_tasks", "adoption_fraction", "loaded_hourly_rate", "cash_conversion_fraction")
METRICS = (
    "assisted_tasks_per_month", "baseline_hours_per_month", "assisted_hours_per_month",
    "net_capacity_hours_per_month", "net_capacity_hours_horizon",
    "external_cash_per_month", "external_cash_horizon", "setup_economic_value",
    "operating_economic_net_per_month", "economic_horizon_net",
    "cash_conversion_horizon_net", "unit_economic_margin",
)


class InputError(ValueError):
    """An input cannot be interpreted without silently changing its meaning."""


def decimal_value(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise InputError(f"{field}: use a decimal string or integer, not a float/bool")
    if isinstance(value, str) and not re.fullmatch(r"[+]?(?:\d+(?:\.\d*)?|\.\d+)", value):
        raise InputError(f"{field}: expected a nonnegative plain decimal")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise InputError(f"{field}: invalid decimal") from exc
    if not result.is_finite() or result < 0:
        raise InputError(f"{field}: expected a finite nonnegative value")
    return result


def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_document(text: str) -> dict[str, Any]:
    try:
        doc = json.loads(text, object_pairs_hook=no_duplicates,
                         parse_constant=lambda value: (_ for _ in ()).throw(InputError(f"invalid JSON constant: {value}")))
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    validate_document(doc)
    return doc


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field}: expected nonempty text")
    return value


def validate_document(doc: Any) -> None:
    if not isinstance(doc, dict):
        raise InputError("document must be an object")
    expected = {"schema_version", "input_basis", "currency", "horizon_months", "scenarios"}
    if set(doc) != expected:
        raise InputError(f"document keys must be {sorted(expected)}")
    if doc["schema_version"] != VERSION:
        raise InputError(f"schema_version must be {VERSION!r}")
    if not isinstance(doc["input_basis"], str) or doc["input_basis"] not in {"SYNTHETIC", "PLANNING_ASSUMPTIONS", "MEASURED_INPUTS"}:
        raise InputError("input_basis must state SYNTHETIC, PLANNING_ASSUMPTIONS or MEASURED_INPUTS")
    if not isinstance(doc["currency"], str) or not re.fullmatch(r"[A-Z]{3}", doc["currency"]):
        raise InputError("currency must be a three-letter uppercase code; no FX conversion is performed")
    h = doc["horizon_months"]
    if isinstance(h, bool) or not isinstance(h, int) or h <= 0:
        raise InputError("horizon_months must be a positive integer")
    if not isinstance(doc["scenarios"], list) or not doc["scenarios"]:
        raise InputError("scenarios must be a nonempty list")
    ids: set[str] = set()
    for index, scenario in enumerate(doc["scenarios"]):
        if not isinstance(scenario, dict) or set(scenario) != {"id", "group", "label", "notes", "inputs"}:
            raise InputError(f"scenario {index}: expected id/group/label/notes/inputs")
        sid = require_text(scenario["id"], "scenario.id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", sid) or sid in ids:
            raise InputError(f"scenario id must be unique and use letters/digits/._-: {sid}")
        ids.add(sid)
        for key in ("group", "label", "notes"):
            require_text(scenario[key], f"{sid}.{key}")
        inputs = scenario["inputs"]
        if not isinstance(inputs, dict) or set(inputs) != set(FIELDS):
            raise InputError(f"{sid}: input keys must exactly match the documented {len(FIELDS)} fields")
        for key, cell in inputs.items():
            if not isinstance(cell, dict) or set(cell) != {"range", "unit", "basis", "source"}:
                raise InputError(f"{sid}.{key}: expected range/unit/basis/source")
            if cell["unit"] != FIELDS[key][0]:
                raise InputError(f"{sid}.{key}: unit must be {FIELDS[key][0]!r}")
            if not isinstance(cell["basis"], str) or cell["basis"] not in {"synthetic", "assumed", "observed", "unknown"}:
                raise InputError(f"{sid}.{key}: invalid basis")
            require_text(cell["source"], f"{sid}.{key}.source")
            if doc["input_basis"] == "SYNTHETIC" and cell["basis"] not in {"synthetic", "unknown"}:
                raise InputError(f"{sid}.{key}: a synthetic document cannot claim observed inputs")
            if doc["input_basis"] == "MEASURED_INPUTS" and cell["basis"] not in {"observed", "unknown"}:
                raise InputError(f"{sid}.{key}: a measured-input document cannot relabel synthetic/assumed inputs")
            value = cell["range"]
            if value is None:
                if cell["basis"] != "unknown":
                    raise InputError(f"{sid}.{key}: null range requires unknown basis")
                continue
            if cell["basis"] == "unknown":
                raise InputError(f"{sid}.{key}: unknown basis requires null range")
            if not isinstance(value, dict) or set(value) != {"low", "base", "high"}:
                raise InputError(f"{sid}.{key}: range must be null or low/base/high")
            low, base, high = (decimal_value(value[k], key) for k in ("low", "base", "high"))
            if not low <= base <= high:
                raise InputError(f"{sid}.{key}: require low <= base <= high")
            if key in FRACTIONS and high > ONE:
                raise InputError(f"{sid}.{key}: fraction must be between zero and one")


def values_at(scenario: dict[str, Any], point: str = "base") -> dict[str, Decimal | None]:
    return {key: None if cell["range"] is None else decimal_value(cell["range"][point], key)
            for key, cell in scenario["inputs"].items()}


def evaluate(values: dict[str, Decimal | None], months: int) -> dict[str, Any] | None:
    """Evaluate known assumptions without cents rounding during intermediate steps."""
    if any(values[key] is None for key in ECONOMIC_FIELDS):
        return None
    v = values
    h = Decimal(months)
    with localcontext() as context:
        context.prec = 50
        n = v["monthly_tasks"] * v["adoption_fraction"]
        baseline = n * v["baseline_minutes"] / SIXTY
        assisted_minutes = v["author_minutes"] + v["checking_minutes"] + v["rework_fraction"] * v["rework_minutes"]
        assisted = n * assisted_minutes / SIXTY
        fixed_hours = v["support_hours"] + v["maintenance_hours"]
        net_hours = baseline - assisted - fixed_hours
        generation = v["attempts_per_task"] * v["generation_cash_per_attempt"]
        cash_month = n * generation + v["platform_cash"]
        setup = v["integration_hours"] * v["loaded_hourly_rate"] + v["setup_cash"]
        operating = net_hours * v["loaded_hourly_rate"] - cash_month
        capacity_horizon = h * net_hours - v["integration_hours"]
        cash_horizon = h * cash_month + v["setup_cash"]
        economic_net = h * operating - setup
        conversion = v["cash_conversion_fraction"]
        converted_net = None if conversion is None else capacity_horizon * v["loaded_hourly_rate"] * conversion - cash_horizon
        unit_margin = (v["baseline_minutes"] - assisted_minutes) / SIXTY * v["loaded_hourly_rate"] - generation
        fixed = fixed_hours * v["loaded_hourly_rate"] + v["platform_cash"]
        required = fixed + setup / h
        threshold = required / unit_margin if unit_margin > 0 else (ZERO if unit_margin == 0 and required == 0 else None)
        minimum_tasks = None if threshold is None else threshold.to_integral_value(rounding=ROUND_CEILING)
        adoption = None if threshold is None or v["monthly_tasks"] == 0 else threshold / v["monthly_tasks"]
        review_limit = None
        if n > 0 and v["loaded_hourly_rate"] > 0:
            review_limit = v["baseline_minutes"] - v["author_minutes"] - v["rework_fraction"] * v["rework_minutes"] - SIXTY / v["loaded_hourly_rate"] * (generation + required / n)
        payback = setup / operating if operating > 0 else (ZERO if setup == 0 and operating == 0 else None)
        return {
            "assisted_tasks_per_month": n,
            "baseline_hours_per_month": baseline,
            "assisted_hours_per_month": assisted,
            "net_capacity_hours_per_month": net_hours,
            "net_capacity_hours_horizon": capacity_horizon,
            "external_cash_per_month": cash_month,
            "external_cash_horizon": cash_horizon,
            "setup_economic_value": setup,
            "operating_economic_net_per_month": operating,
            "economic_horizon_net": economic_net,
            "cash_conversion_horizon_net": converted_net,
            "unit_economic_margin": unit_margin,
            "break_even": {
                "assisted_tasks_per_month_exact": threshold,
                "assisted_tasks_per_month_ceiling": minimum_tasks,
                "adoption_fraction_exact": adoption,
                "attainable_with_current_volume": None if adoption is None else adoption <= ONE,
                "maximum_checking_minutes": review_limit,
                "nonnegative_checking_feasible": None if review_limit is None else review_limit >= 0,
                "simple_payback_months": payback,
                "payback_within_horizon": None if payback is None else payback <= h,
                "unit_margin_status": "POSITIVE" if unit_margin > 0 else "ZERO" if unit_margin == 0 else "NEGATIVE",
            },
        }


def envelope(scenario: dict[str, Any], months: int) -> dict[str, Any] | None:
    """Exact independent-box net-value extrema using monotonicity + at most 32 points.

The formula is multi-affine. Every non-free cost coordinate is non-increasing
in each of the two net-value objectives; baseline minutes is non-decreasing.
Enumerating free-coordinate endpoints covers sign flips and shared dependencies.
This is a range envelope, not a confidence interval or likelihood statement.
    """
    base = values_at(scenario)
    if evaluate(base, months) is None:
        return None
    candidates: list[tuple[dict[str, Decimal | None], dict[str, Any]]] = []
    for favorable in (False, True):
        point = dict(base)
        for key in FIELDS:
            if key in FREE_FIELDS:
                continue
            choose_high = favorable if key == "baseline_minutes" else not favorable
            point[key] = decimal_value(scenario["inputs"][key]["range"]["high" if choose_high else "low"], key)
        choices = []
        for key in FREE_FIELDS:
            cell = scenario["inputs"][key]["range"]
            choices.append([None] if cell is None else sorted({decimal_value(cell[k], key) for k in ("low", "high")}))
        for combination in itertools.product(*choices):
            witness = dict(point, **dict(zip(FREE_FIELDS, combination)))
            candidates.append((witness, evaluate(witness, months)))
    result: dict[str, Any] = {"method": "independent_box_not_probability", "evaluated_points": len(candidates)}
    for metric in ("economic_horizon_net", "cash_conversion_horizon_net"):
        available = [(v, data[metric]) for v, data in candidates if data[metric] is not None]
        if not available:
            result[metric] = None
            continue
        low_point, low = min(available, key=lambda pair: pair[1])
        high_point, high = max(available, key=lambda pair: pair[1])
        result[metric] = {"low": low, "high": high, "low_witness": low_point, "high_witness": high_point}
    return result


def classify(bounds: dict[str, Any] | None) -> str:
    if bounds is None:
        return "UNKNOWN"
    if bounds["low"] > 0:
        return "POSITIVE_ACROSS_RANGE"
    if bounds["high"] < 0:
        return "NEGATIVE_ACROSS_RANGE"
    if bounds["low"] == bounds["high"] == 0:
        return "BREAK_EVEN_ACROSS_RANGE"
    return "SENSITIVE_TO_ASSUMPTIONS"


def sensitivity(scenario: dict[str, Any], months: int) -> list[dict[str, Any]]:
    base = values_at(scenario)
    if evaluate(base, months) is None:
        return []
    rows = []
    for field in FIELDS:
        cell = scenario["inputs"][field]["range"]
        if cell is None:
            continue
        lo = evaluate(dict(base, **{field: decimal_value(cell["low"], field)}), months)
        hi = evaluate(dict(base, **{field: decimal_value(cell["high"], field)}), months)
        rows.append({
            "field": field, "unit": FIELDS[field][0], "input_low": decimal_value(cell["low"], field),
            "input_high": decimal_value(cell["high"], field),
            "economic_at_low_input": lo["economic_horizon_net"], "economic_at_high_input": hi["economic_horizon_net"],
            "economic_swing": abs(hi["economic_horizon_net"] - lo["economic_horizon_net"]),
            "cash_at_low_input": lo["cash_conversion_horizon_net"], "cash_at_high_input": hi["cash_conversion_horizon_net"],
            "measurement": FIELDS[field][1],
        })
    return sorted(rows, key=lambda row: (-row["economic_swing"], row["field"]))


def grid(scenario: dict[str, Any], months: int) -> list[dict[str, Any]]:
    base = values_at(scenario)
    if evaluate(base, months) is None:
        return []
    rows = []
    for volume_level, checking_level in itertools.product(("low", "base", "high"), repeat=2):
        n = decimal_value(scenario["inputs"]["monthly_tasks"]["range"][volume_level], "monthly_tasks")
        c = decimal_value(scenario["inputs"]["checking_minutes"]["range"][checking_level], "checking_minutes")
        value = evaluate(dict(base, monthly_tasks=n, checking_minutes=c), months)
        rows.append({"volume_level": volume_level, "checking_level": checking_level,
                     "monthly_tasks": n, "checking_minutes": c,
                     "economic_horizon_net": value["economic_horizon_net"]})
    return rows


def canonical_hash(doc: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def analyze(doc: dict[str, Any]) -> dict[str, Any]:
    validate_document(doc)
    with localcontext() as context:
        context.prec = 50
        results = []
        for scenario in doc["scenarios"]:
            base = evaluate(values_at(scenario), doc["horizon_months"])
            bounds = envelope(scenario, doc["horizon_months"])
            missing = [key for key in FIELDS if scenario["inputs"][key]["range"] is None]
            effects = sensitivity(scenario, doc["horizon_months"])
            measurements = [{"field": key, "reason": "MISSING_INPUT", "measurement": FIELDS[key][1]} for key in missing]
            measurements += [{"field": row["field"], "reason": "RANGE_SENSITIVITY", "economic_swing": row["economic_swing"], "measurement": row["measurement"]}
                             for row in effects if row["input_low"] != row["input_high"]]
            results.append({"id": scenario["id"], "group": scenario["group"], "label": scenario["label"],
                            "notes": scenario["notes"], "missing_inputs": missing,
                            "economic_classification": classify(None if bounds is None else bounds["economic_horizon_net"]),
                            "cash_classification": classify(None if bounds is None else bounds["cash_conversion_horizon_net"]),
                            "base": base, "envelope": bounds, "sensitivity": effects,
                            "volume_checking_grid": grid(scenario, doc["horizon_months"]),
                            "measurement_plan": measurements})
        return {"schema_version": VERSION, "kind": "AI_WORKFLOW_ECONOMICS_SCENARIO",
                "input_basis": doc["input_basis"], "result_basis": "MODELED_NOT_OBSERVED",
                "institution_finding": False, "spend_authorized": False, "recognized_revenue": False,
                "currency": doc["currency"], "horizon_months": doc["horizon_months"],
                "input_sha256": canonical_hash(doc), "model_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "limitations": ["Independent box ranges are not probability distributions or confidence intervals.",
                                "A single loaded rate values capacity, not individual productivity or guaranteed cash savings.",
                                "Linear steady-state task mix, volume and costs; no discounting, seasonality, ramp or quality valuation.",
                                "Negative capacity requires staffing feasibility assessment even when cash conversion is zero.",
                                "Quality/usefulness evidence and acceptable outputs must be evaluated separately."],
                "scenarios": results}


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def display(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, Decimal):
        with localcontext() as context:
            context.prec = max(50, len(value.as_tuple().digits) + abs(value.as_tuple().exponent) + 4)
            return format(value.quantize(Decimal("0.01")), "f")
    return str(value)


def markdown_text(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# AI workflow economics — modeled preparation output", "",
             f"**{report['input_basis']} inputs; not observed University outcomes.** Horizon: {report['horizon_months']} months; currency: {report['currency']}.",
             "", "Economic net values staff capacity at the stated loaded rate and subtracts external cash. Cash conversion is a separate, signed scenario assumption, not a savings forecast.",
             "", "| Scenario | Economic range | Economic base | Cash-conversion base | Net capacity hours | Classification |",
             "|---|---:|---:|---:|---:|---|"]
    for row in report["scenarios"]:
        point, bounds = row["base"], row["envelope"]
        interval = "UNKNOWN" if bounds is None else f"{display(bounds['economic_horizon_net']['low'])} to {display(bounds['economic_horizon_net']['high'])}"
        get = lambda field: None if point is None else point[field]
        lines.append(f"| {markdown_text(row['id'])} | {interval} | {display(get('economic_horizon_net'))} | {display(get('cash_conversion_horizon_net'))} | {display(get('net_capacity_hours_horizon'))} | {row['economic_classification']} |")
    for row in report["scenarios"]:
        lines += ["", f"## {markdown_text(row['id'])}: {markdown_text(row['label'])}", "", markdown_text(row["notes"])]
        if row["missing_inputs"]:
            lines += ["", "Missing inputs (not imputed as zero): " + ", ".join(row["missing_inputs"]) + "."]
        if row["base"] is not None:
            b = row["base"]["break_even"]
            lines += ["", f"Base-assumption break-even assisted tasks/month: **{display(b['assisted_tasks_per_month_exact'])}** (whole-task ceiling: {display(b['assisted_tasks_per_month_ceiling'])}).",
                      f"Maximum checking minutes/task at base volume: **{display(b['maximum_checking_minutes'])}**; a negative value means no nonnegative checking time can break even under these assumptions.",
                      f"Simple payback months: **{display(b['simple_payback_months'])}**. Missing payback means no modeled recovery, not immediate recovery."]
        lines += ["", "### Measurements that would change the decision", ""]
        for item in row["measurement_plan"][:6]:
            lines.append(f"- **{item['field']}** ({item['reason']}): {item['measurement']}")
        if not row["measurement_plan"]:
            lines.append("Inputs have no specified ranges or gaps. This does not establish empirical certainty; collect source evidence before using the model for a decision.")
    lines += ["", "## Interpretation boundaries", ""] + [f"- {item}" for item in report["limitations"]]
    lines += ["", "Input SHA-256: `" + report["input_sha256"] + "`", "Model SHA-256: `" + report["model_sha256"] + "`", ""]
    return "\n".join(lines)


def csv_text(rows: list[dict[str, Any]], fields: list[str]) -> str:
    """Keep numeric signs; neutralize formula-like user text only. JSON is lossless."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        clean = {}
        for key in fields:
            value = row.get(key)
            if isinstance(value, Decimal):
                clean[key] = format(value, "f")
            elif value is None:
                clean[key] = "UNKNOWN"
            elif isinstance(value, str) and (value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))):
                clean[key] = "'" + value
            else:
                clean[key] = value
        writer.writerow(clean)
    return stream.getvalue()


def artifacts(doc: dict[str, Any], report: dict[str, Any]) -> dict[str, str]:
    summary, register, effects, measurements, grids = [], [], [], [], []
    for row, source in zip(report["scenarios"], doc["scenarios"]):
        point = row["base"] or {}
        bounds = row["envelope"]
        summary.append({"scenario_id": row["id"], "group": row["group"], "currency": report["currency"],
                        "horizon_months": report["horizon_months"], "input_basis": report["input_basis"],
                        "result_basis": report["result_basis"], "economic_classification": row["economic_classification"],
                        "economic_low": None if bounds is None else bounds["economic_horizon_net"]["low"],
                        "economic_base": point.get("economic_horizon_net"),
                        "economic_high": None if bounds is None else bounds["economic_horizon_net"]["high"],
                        "cash_conversion_base": point.get("cash_conversion_horizon_net"),
                        "capacity_hours_horizon": point.get("net_capacity_hours_horizon"),
                        "external_cash_horizon": point.get("external_cash_horizon")})
        for key, cell in source["inputs"].items():
            ranges = {p: None if cell["range"] is None else decimal_value(cell["range"][p], key) for p in ("low", "base", "high")}
            register.append({"scenario_id": row["id"], "field": key, **ranges, "unit": cell["unit"], "basis": cell["basis"], "source": cell["source"], "measurement": FIELDS[key][1]})
        effects += [{"scenario_id": row["id"], **item} for item in row["sensitivity"]]
        measurements += [{"scenario_id": row["id"], **item} for item in row["measurement_plan"]]
        grids += [{"scenario_id": row["id"], **item} for item in row["volume_checking_grid"]]
    return {
        "report.json": json.dumps(json_ready(report), indent=2, ensure_ascii=False) + "\n",
        "report.md": render_markdown(report),
        "summary.csv": csv_text(summary, list(summary[0])),
        "input_register.csv": csv_text(register, ["scenario_id", "field", "low", "base", "high", "unit", "basis", "source", "measurement"]),
        "sensitivity.csv": csv_text(effects, ["scenario_id", "field", "unit", "input_low", "input_high", "economic_at_low_input", "economic_at_high_input", "economic_swing", "cash_at_low_input", "cash_at_high_input", "measurement"]),
        "measurement_plan.csv": csv_text(measurements, ["scenario_id", "field", "reason", "economic_swing", "measurement"]),
        "volume_checking_grid.csv": csv_text(grids, ["scenario_id", "volume_level", "checking_level", "monthly_tasks", "checking_minutes", "economic_horizon_net"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON assumptions document")
    parser.add_argument("--out", required=True, type=Path, help="output directory; receives seven deterministic reports")
    args = parser.parse_args(argv)
    try:
        doc = load_document(args.input.read_text(encoding="utf-8"))
        report = analyze(doc)
        outputs = artifacts(doc, report)
        if any((args.out / name).resolve() == args.input.resolve() for name in outputs):
            raise InputError("output would overwrite the input document")
        args.out.mkdir(parents=True, exist_ok=True)
        for name, text in outputs.items():
            (args.out / name).write_text(text, encoding="utf-8", newline="")
    except (OSError, UnicodeError, InputError, ArithmeticError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"WROTE {len(outputs)} artifacts; {len(report['scenarios'])} scenarios; {report['input_basis']} / MODELED_NOT_OBSERVED")
    for row in report["scenarios"]:
        print(f"{row['id']}: {row['economic_classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
