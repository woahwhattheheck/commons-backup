#!/usr/bin/env python3
"""Nine fictional operator cases through the existing UIOWA-065 assessor.

No live telemetry, external action or monitoring vendor is used. A supported
measurement record is not a passed service objective or a maturity rating.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

if __package__:
    from . import observability as engine
else:
    import observability as engine

HERE = Path(__file__).resolve().parent
EXAMPLES_BLOB = "c269f42cb53d01d0f2788d7d4bb41f1fa686441d"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _scenarios() -> list[dict[str, Any]]:
    source = (HERE / "examples.json").read_bytes()
    if git_blob(source) != EXAMPLES_BLOB:
        raise ValueError("retained fictional examples changed; reconcile expected scenarios first")
    original = json.loads(source)

    def one(index: int) -> dict[str, Any]:
        packet = deepcopy(original)
        packet["services"] = [packet["services"][index]]
        return packet

    rows = [{
        "id": "baseline_three_services", "input": deepcopy(original),
        "expected_statuses": ["SUPPORTED", "SUPPORTED", "PARTIAL"],
        "required_issues": ["dependency_visibility_partial", "decision_use_not_evidenced", "indicator_not_user_visible"],
        "interpretation": "Registration and research have supported measurement metadata; sign-in has only partial infrastructure evidence. This is not three passed service objectives.",
        "next_decision": "Keep service, dependency, user-journey and decision-use questions separate in the interview.",
    }]
    packet = one(0)
    objective = packet["services"][0]["objectives"][0]
    objective["measurement_evidence"]["numerator"] = 19800
    objective["measurement_evidence"]["source_ref"] = "SYN-L9Q7-REG-BREACH-01"
    objective["decision_evidence"] = [{
        "decision_ref": "SYN-L9Q7-REG-REVIEW-01",
        "outcome": "Fictional plan: investigate timeout concentration before proposing a retry-policy change; no change is authorized.",
    }]
    rows.append({
        "id": "registration_target_missed", "input": packet,
        "expected_statuses": ["SUPPORTED"], "required_issues": ["dependency_visibility_partial"],
        "interpretation": "19,800 / 20,000 is 99.0%, below the fictional 99.5% target. SUPPORTED describes the supplied evidence structure, not service success. The assessor does not compute an SLO verdict.",
        "next_decision": "Inspect eligible-request outcomes by dependency and error class. Retain the planned investigation; do not infer that retries will fix it.",
    })
    packet = one(1)
    packet["services"][0]["objectives"][0]["measurement_evidence"] = None
    rows.append({
        "id": "research_measurement_missing", "input": packet,
        "expected_statuses": ["UNKNOWN"], "required_issues": ["measurement_evidence_missing"],
        "interpretation": "No measurement record was supplied. This is unknown acknowledgement behavior, not zero successful submissions or a failed service.",
        "next_decision": "Request the population/window definition and durable-acknowledgement evidence before interpreting a rate.",
    })
    packet = one(2)
    packet["services"][0]["objectives"][0]["indicator"]["user_visible"] = None
    rows.append({
        "id": "signin_visibility_unknown", "input": packet,
        "expected_statuses": ["PARTIAL"], "required_issues": ["indicator_user_visibility_unknown"],
        "interpretation": "Unresolved indicator scope remains null, not infrastructure-only false or user-journey true. The missing definition still makes measurement support partial.",
        "next_decision": "Ask which journey start/end events the indicator observes; do not choose the answer for the service owner.",
    })
    packet = one(2)
    objective = packet["services"][0]["objectives"][0]
    objective["indicator"].update(user_visible=True, description="Fictional sign-in journey start to usable signed-in session")
    objective["measurement_evidence"].update(source_ref="SYN-L9Q7-SIGNIN-JOURNEY-01", definition_ref="SYN-L9Q7-SIGNIN-DEFINITION-01")
    objective["diagnostic_context"] = ["fictional journey correlation id", "dependency stage", "outcome category"]
    objective["decision_evidence"] = [{"decision_ref": "SYN-L9Q7-SIGNIN-REVIEW-01", "outcome": "Fictional decision record: review the defined journey separately from backend handler duration."}]
    rows.append({
        "id": "signin_journey_definition_added", "input": packet,
        "expected_statuses": ["SUPPORTED"], "required_issues": ["dependency_visibility_unknown"],
        "interpretation": "The example now supplies journey scope and a definition-linked measurement record. No latency samples or computed percentile are supplied; target attainment remains unestablished.",
        "next_decision": "Collect the actual journey latency distribution and dependency context before comparing p95 with 1,200 ms.",
    })
    packet = one(0)
    packet["services"][0]["objectives"][0]["measurement_evidence"]["period_start"] = "2026-08-01T00:00:00Z"
    rows.append({
        "id": "reversed_measurement_interval", "input": packet,
        "expected_statuses": ["PARTIAL"], "required_issues": ["measurement_period_invalid"],
        "interpretation": "A start after the end cannot support the declared interval even when counts look plausible. The supplied record is partial, not a measured outage.",
        "next_decision": "Resolve the actual capture interval without silently swapping timestamps or inventing coverage.",
    })
    packet = one(0)
    packet["services"][0]["objectives"][0]["measurement_evidence"].update(numerator=0, denominator=0)
    rows.append({
        "id": "zero_eligible_population", "input": packet,
        "expected_statuses": ["PARTIAL"], "required_issues": ["invalid_denominator"],
        "interpretation": "0 / 0 is not 0% or 100%. Supplied zero-population evidence remains partial for this ratio; absent evidence is a different case.",
        "next_decision": "Check population inclusion, quiet periods and collection gaps before changing the objective.",
    })
    packet = one(0)
    packet["services"][0]["objectives"][0]["measurement_evidence"].update(numerator=True, denominator=True)
    rows.append({
        "id": "malformed_boolean_ratio", "input": packet,
        "expected_error": "finite number, not a Boolean",
        "interpretation": "A Boolean is not an observed count. Malformed typed input is rejected, not converted into a supported one-of-one rate.",
        "next_decision": "Correct the export's field types and retain the rejected source for diagnosis.",
    })
    packet = one(0)
    packet["services"][0]["objectives"][0]["indicator"]["user_visible"] = "false"
    rows.append({
        "id": "malformed_text_visibility", "input": packet,
        "expected_error": "must be Boolean or null",
        "interpretation": "The text false is not JSON false. It is rejected rather than promoted to a user-visible indicator through Python truthiness.",
        "next_decision": "Use true, false or null deliberately; a missing answer must remain unknown.",
    })
    return rows


def build_rehearsal() -> dict[str, Any]:
    rows = []
    for case in _scenarios():
        packet = case["input"]
        before = deepcopy(packet)
        try:
            assessment = engine.assess_packet(packet)
        except ValueError as exc:
            if "expected_error" not in case or case["expected_error"] not in str(exc):
                raise ValueError(f"{case['id']}: unexpected rejection: {exc}") from exc
            actual = {"outcome": "REJECTED", "error": str(exc)}
        else:
            if "expected_error" in case:
                raise ValueError(f"{case['id']}: malformed evidence was accepted")
            statuses = [row["status"] for row in assessment["findings"]]
            issues = {issue for row in assessment["findings"] for issue in row["issues"]}
            if statuses != case["expected_statuses"] or not set(case["required_issues"]).issubset(issues):
                raise ValueError(f"{case['id']}: expected assessment behavior changed")
            actual = {"outcome": "ASSESSED", "assessment": assessment}
        if packet != before:
            raise ValueError(f"{case['id']}: the assessor mutated supplied evidence")
        rows.append(dict(case, synthetic=True, **actual))
    return {
        "schema": "uiowa-065-operational-rehearsal-v1", "synthetic": True,
        "scope": "Fictional source records only. No live telemetry, external action, University finding or target-attainment certification.",
        "case_count": len(rows), "cases": rows,
        "source_git_blobs": {name: git_blob((HERE / name).read_bytes()) for name in ("observability.py", "examples.json", "rehearsal.py")},
        "attribution": "ZZ-Sol retains the original assessor/examples/worksheet. ZZ-KESTREL-L9Q7 / GPT-6 Astra Pro authored the typed-evidence repair and operational rehearsal.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# UIOWA-065: fictional operational rehearsal", "", report["scope"], "",
             "SUPPORTED is measurement-evidence support, not target attainment or a maturity rating.", "",
             "| Case | Actual outcome |", "|---|---|"]
    for row in report["cases"]:
        actual = ", ".join(f["status"] for f in row["assessment"]["findings"]) if row["outcome"] == "ASSESSED" else "REJECTED (malformed input)"
        lines.append(f"| {row['id']} | {actual} |")
    for row in report["cases"]:
        lines.extend(["", f"## {row['id']}", "", row["interpretation"], "", "Next decision: " + row["next_decision"]])
    lines.extend(["", "## Source identities", ""])
    lines.extend(f"- `{name}`: `{sha}`" for name, sha in report["source_git_blobs"].items())
    lines.extend(["", report["attribution"], ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)
    try:
        report = build_rehearsal()
        text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n" if args.format == "json" else render_markdown(report)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"observability rehearsal: {exc}", file=sys.stderr)
        return 2
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
