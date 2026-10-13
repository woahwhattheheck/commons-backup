"""JSON register to JSON, spreadsheet-readable CSV and Markdown scenarios."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import sys
from typing import Any

from .model import InputError, MAX_BYTES, analyze, load_register


def _md(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;").replace("|", "\\|").replace("`", "'").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    p = report["parameters"]
    lines = ["# Technical-debt investment scenarios", "",
        f"Evidence class: **{report['evidence_class']}**. Analyst scenarios only; no University findings, investment approval or confirmed staff availability.",
        "", f"Capacity: {p['budget_hours']} hours at upper effort bounds. Horizon: {p['horizon_weeks']} weeks.",
        f"Required scenario items: {', '.join(p['required_ids']) or 'none'}.",
        f"Decision status: **{report['decision_status']}**.", "",
        "## Competing portfolios", "",
        "| Scenario | Selected IDs | Upper effort hours | Net saved hours, low..high |",
        "|---|---|---:|---:|"]
    for name, portfolio in report["portfolios"].items():
        if portfolio is None:
            lines.append(f"| {name} | NO FEASIBLE PORTFOLIO | — | — |")
        else:
            lines.append(f"| {name} | {', '.join(portfolio['ids']) or '(defer all)'} | "
                         f"{portfolio['effort_hours_high']} | {portfolio['net_hours_low']}..{portfolio['net_hours_high']} |")
    lines += ["", "Shared prerequisites are paid once. Overlapping benefit pools and alternatives cannot be combined. Endpoint scenarios are not statistical confidence intervals. Qualitative criticality is NOT optimized or treated as a maturity score.",
        "", "## Register and deferral rationale", "",
        "| ID | Service impact | Service consequence | Standalone net hours | Disposition |",
        "|---|---|---|---:|---|"]
    for row in report["items"]:
        modeled = row["modeled"]
        net = "UNKNOWN" if modeled is None else f"{modeled['net_hours_low']}..{modeled['net_hours_high']}"
        lines.append(f"| {row['id']} | {row['service_impact']} | {_md(row['service_consequence'])} | {net} | {row['disposition']} |")
    lines += ["", "Standalone net figures exclude prerequisite costs; the portfolio totals include them. A positive standalone value is not enough to select an item.",
              "", "## Prioritized investigation questions", ""]
    for q in report["investigations"]:
        lines.append(f"- **P{q['priority']} {q['id']}**: {_md(q['question'])} Revisit: {_md(q['revisit_trigger'])}")
    lines += ["", "## Interpretation and provenance", "",
        "All benefits assume the declared delay already includes implementation, prerequisites and adoption. This is an effort-capacity model, not a calendar/resource schedule. It omits risk reduction, regulatory obligations, procurement costs and customer value; inspect those separately before deferring high-impact work. References and OBSERVED labels are supplied evidence claims, not source authentication. Synthetic references are fictional.",
        "", f"Normalized register SHA-256: `{report['register_sha256']}`.",
        f"Analysis SHA-256 (canonical JSON excluding this digest): `{report['report_sha256']}`.", ""]
    return "\n".join(lines)


def render_csv(report: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    columns = ["id", "service", "category", "service_impact", "estimate_basis", "dependencies",
               "effort_hours_low", "effort_hours_high", "net_hours_low", "net_hours_high", "disposition"]
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    def text(value: str) -> str:
        # Defensive escaping for text cells opened by spreadsheet programs.
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
    for row in report["items"]:
        record = {key: text(row[key]) for key in columns if key in row and type(row[key]) is str}
        record["dependencies"] = ";".join(row["dependencies"])
        effort, modeled = row["effort_hours"], row["modeled"]
        record.update({"effort_hours_low": effort["low"] if effort is not None else "",
                       "effort_hours_high": effort["high"] if effort is not None else "",
                       "net_hours_low": modeled["net_hours_low"] if modeled else "",
                       "net_hours_high": modeled["net_hours_high"] if modeled else ""})
        writer.writerow(record)
    return output.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("register", type=Path)
    parser.add_argument("--budget-hours", type=int, required=True)
    parser.add_argument("--horizon-weeks", type=int, required=True)
    parser.add_argument("--require", action="append", default=[], metavar="ITEM_ID",
                        help="analyst scenario constraint, not an organizational mandate")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="new directory; existing contents are never overwritten")
    args = parser.parse_args(argv)
    try:
        with args.register.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        report = analyze(load_register(raw), args.budget_hours, args.horizon_weeks, args.require)
        rendered = {"analysis.json": json.dumps(report, indent=2, sort_keys=True) + "\n",
                    "analysis.md": render_markdown(report), "priorities.csv": render_csv(report)}
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for name, content in rendered.items():
            with (args.output_dir / name).open("x", encoding="utf-8", newline="") as stream:
                stream.write(content)
    except (InputError, OSError) as exc:
        print(f"debt-analysis: {exc}", file=sys.stderr)
        return 2
    print(f"{report['decision_status']}: {report['search']['feasible_portfolios']} feasible portfolios; "
          f"receipt {report['report_sha256']}")
    return 0 if report["decision_status"] == "SCENARIOS_AVAILABLE" else 3
