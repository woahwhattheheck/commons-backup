"""Portable JSON/CSV/Markdown reporting; no network calls or source mutation."""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

try:
    from .analyze import analyze
    from .contract import load
except ImportError:
    from analyze import analyze
    from contract import load


def cell(value) -> str:
    text = "UNKNOWN" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;").replace("\r", "").replace("\n", "<br>")


def markdown(report: dict) -> str:
    lines = ["# Incident-learning assessment", "", "**Classification: " + report["classification"].upper() + "**",
             "", "As of: " + report["as_of"], "", *report["limits"], "", "## Incident evidence"]
    for incident in report["incidents"]:
        lines += ["", "### " + cell(incident["id"]) + " / " + incident["group"],
                  "", cell(incident["service"]) + ": " + cell(incident["impact"]),
                  "", "Coverage: " + incident["coverage"] + ". Evidence: " + cell(", ".join(incident["evidence_ids"])),
                  "", "| Milestone | Timestamp | Source IDs | Meaning |", "|---|---|---|---|"]
        for event in incident["events"]:
            lines.append("| " + " | ".join(cell(v) for v in (event["kind"], event["at"], ", ".join(event["evidence_ids"]) or None, event["note"])) + " |")
        lines += ["", "Measured intervals (minutes; evidence-linked endpoints only): " + cell(json.dumps(incident["minutes"], sort_keys=True)),
                  "", "Missing/unsupported milestones: " + cell(", ".join(incident["milestones_missing_evidence"]) or "none"),
                  "", "Analysis: " + cell(incident["review"]["analysis"]),
                  "", "Open questions: " + cell("; ".join(incident["review"]["unresolved_questions"]) or "none recorded"),
                  "", "Backlog: " + cell(", ".join(incident["action_ids"]) or "none"),
                  "", "Conditions without actions: " + cell(", ".join(incident["conditions_without_actions"]) or "none")]
    lines += ["", "## Corrective work", "", "| Action / role | Reported | Evidence state | Days overdue unresolved | Effectiveness |", "|---|---|---|---|---|"]
    for action in report["actions"]:
        lines.append("| " + " | ".join(cell(v) for v in (action["id"] + " / " + (action["owner_role"] or "UNKNOWN"),
            action["reported_status"], action["evidence_state"], action["days_past_due"], action["effectiveness"]["state"])) + " |")
    for action in report["actions"]:
        lines += ["", "### " + cell(action["id"]), "", cell(action["description"]),
                  "", "Incident → condition: " + cell(", ".join(action["incident_ids"]) + " → " + ", ".join(action["condition_ids"])),
                  "", "Implementation / verification sources: " + cell(", ".join(action["implementation_evidence_ids"]) or "UNKNOWN") + " / " + cell(", ".join(action["verification_evidence_ids"]) or "UNKNOWN"),
                  "", "Follow-up: " + cell("; ".join(action["issues"]) or "none from structural checks"),
                  "", "Comparison: " + cell(json.dumps(action["effectiveness"], sort_keys=True)),
                  "", "Measurement windows, counts and exposure: " + cell(json.dumps(action["measurement"], sort_keys=True))]
        if action["replacement"]:
            lines += ["", "Replacement decision: " + cell(json.dumps(action["replacement"], sort_keys=True))]
    lines += ["", "## Contributing-condition trace", ""]
    for condition in report["conditions"]:
        lines += [cell(condition["id"]) + ": " + cell(condition["description"]),
                  "", "Incidents: " + cell(", ".join(condition["incident_ids"])) + "; unresolved work: " + cell(", ".join(condition["unresolved_action_ids"]) or "none"), "", condition["interpretation"], ""]
    lines += ["## Source appendix", "", "Every identifier below resolves to the supplied source record; locators are not fetched automatically.", ""]
    for source in report["sources"]:
        lines += ["### " + cell(source["id"]), "", cell(source["kind"]) + " — " + cell(source["observed_at"]),
                  "", "Locator: " + cell(source["locator"]), "", cell(source["excerpt"]), ""]
    return "\n".join(lines) + "\n"


def actions_csv(report: dict) -> str:
    out = io.StringIO(newline="")
    fields = ["id", "owner_role", "reported_status", "evidence_state", "due_at", "overdue_unresolved", "days_past_due", "incident_ids", "condition_ids", "implementation_evidence_ids", "verification_evidence_ids", "issues", "effectiveness", "created_at", "completed_at", "late_completion_days", "measurement", "description", "replacement"]
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for action in report["actions"]:
        # JSON in every cell is a reversible typed interchange, not spreadsheet
        # formulas. Null, empty string and arrays remain distinguishable. The
        # appended context fields retain the work text and replacement decision
        # without shifting the original columns consumed by existing readers.
        writer.writerow({k: json.dumps(action[k], ensure_ascii=False, sort_keys=True) for k in fields})
    return out.getvalue()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--format", choices=("json", "csv", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    try:
        result = analyze(load(args.input))
        output = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n" if args.format == "json" else actions_csv(result) if args.format == "csv" else markdown(result)
        sys.stdout.write(output)
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("Invalid assessment input: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
