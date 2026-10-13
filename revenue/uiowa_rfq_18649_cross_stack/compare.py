#!/usr/bin/env python3
"""Outcome-based comparison of supplied practice records; no maturity scoring.

Python 3.10+, standard library only. Input evidence is analyst-supplied metadata:
this program neither fetches source documents nor establishes their authenticity.
"""
from __future__ import annotations

import argparse
import csv
import copy
import hashlib
import io
import json
import sys
from collections import Counter
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Any

SCHEMA = "cross-stack-calibration/v1"
AREAS = ("software-development", "security", "deployment-operations", "ai-readiness")
DIMENSIONS = ("criticality", "workload", "release_cadence", "sampling_basis")
CLAIMS = ("meets", "does_not_meet", "unknown", "not_applicable")


class InputError(ValueError):
    """An input is malformed; no partial assessment is emitted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def text(value: Any, where: str) -> None:
    require(isinstance(value, str) and bool(value.strip()), f"{where}: nonblank text required")


def fields(value: Any, required: set[str], optional: set[str], where: str) -> None:
    require(isinstance(value, dict), f"{where}: object required")
    require(all(isinstance(key, str) for key in value), f"{where}: text keys required")
    require(required <= value.keys(), f"{where}: missing {sorted(required - value.keys())}")
    require(value.keys() <= required | optional, f"{where}: unexpected {sorted(value.keys() - required - optional)}")


def day(value: Any, where: str) -> date:
    text(value, where)
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"{where}: ISO date YYYY-MM-DD required") from exc
    require(result.isoformat() == value, f"{where}: ISO date YYYY-MM-DD required")
    return result


def unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    def invalid_constant(value: str) -> None:
        raise InputError(f"non-finite JSON value: {value}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_json,
                      parse_constant=invalid_constant)


def references(value: Any, evidence: dict[str, Any], where: str) -> None:
    require(isinstance(value, list), f"{where}: list required")
    for ref in value:
        text(ref, where)
        require(ref in evidence, f"{where}: unresolved evidence {ref}")
    require(len(value) == len(set(value)), f"{where}: repeated evidence ID")


def indexed(rows: Any, where: str) -> dict[str, dict[str, Any]]:
    require(isinstance(rows, list), f"{where}: list required")
    result = {}
    for row in rows:
        require(isinstance(row, dict), f"{where}: object row required")
        text(row.get("id"), where + ".id")
        require(row["id"] not in result, f"{where}: duplicate ID {row['id']}")
        result[row["id"]] = row
    return result


def validate(packet: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    fields(packet, {"schema", "synthetic", "as_of", "evidence", "practices", "pairs"}, set(), "packet")
    require(packet["schema"] == SCHEMA, "unsupported schema")
    require(type(packet["synthetic"]) is bool, "synthetic must be boolean")
    as_of = day(packet["as_of"], "as_of")
    evidence = indexed(packet["evidence"], "evidence")
    for ident, item in evidence.items():
        fields(item, {"id", "kind", "source", "locator", "observed_on", "valid_through", "independence_key"}, set(), ident)
        require(item["kind"] in ("observation", "policy", "interview"), f"{ident}: unknown evidence kind")
        for field in ("source", "locator", "independence_key"):
            text(item[field], ident + "." + field)
        require(day(item["observed_on"], ident) <= day(item["valid_through"], ident), f"{ident}: inverted validity window")
    practices = indexed(packet["practices"], "practices")
    for ident, item in practices.items():
        fields(item, {"id", "group", "area", "implementation", "description", "outcome", "context", "claim", "basis", "evidence_ids", "dissent_ids"}, {"applicability_reason", "measurement"}, ident)
        require(item["group"] in ("ESS", "RIS", "IAM"), f"{ident}: unknown group")
        require(item["area"] in AREAS, f"{ident}: unknown area")
        require(item["implementation"] in ("manual", "automated", "shared-service", "hybrid"), f"{ident}: unknown implementation")
        require(item["claim"] in CLAIMS, f"{ident}: unknown claim")
        for field in ("description", "basis"):
            text(item[field], ident + "." + field)
        fields(item["outcome"], {"id", "version", "criterion"}, set(), ident + ".outcome")
        for field, value in item["outcome"].items():
            text(value, ident + ".outcome." + field)
        fields(item["context"], set(DIMENSIONS), set(), ident + ".context")
        for field, value in item["context"].items():
            if value is not None:
                text(value, ident + ".context." + field)
        references(item["evidence_ids"], evidence, ident)
        references(item["dissent_ids"], evidence, ident)
        require(not set(item["evidence_ids"]) & set(item["dissent_ids"]), f"{ident}: evidence both supports and dissents")
        if "applicability_reason" in item:
            text(item["applicability_reason"], ident + ".applicability_reason")
        if item["claim"] == "not_applicable":
            text(item.get("applicability_reason"), ident + ".applicability_reason")
        m = item.get("measurement")
        if m is not None:
            fields(m, {"definition", "population", "window_start", "window_end", "numerator", "denominator"}, set(), ident + ".measurement")
            for field in ("definition", "population"):
                text(m[field], ident + ".measurement." + field)
            require(day(m["window_start"], ident) <= day(m["window_end"], ident) <= as_of, f"{ident}: invalid measurement window")
            for field in ("numerator", "denominator"):
                require(m[field] is None or (type(m[field]) is int and m[field] >= 0), f"{ident}: {field} must be a nonnegative integer or null")
            if m["numerator"] is not None and m["denominator"] is not None:
                require(m["numerator"] <= m["denominator"], f"{ident}: numerator exceeds denominator")
    pairs = indexed(packet["pairs"], "pairs")
    for ident, item in pairs.items():
        fields(item, {"id", "left", "right", "context_decisions"}, set(), ident)
        text(item["left"], ident + ".left")
        text(item["right"], ident + ".right")
        require(item["left"] in practices and item["right"] in practices, f"{ident}: unresolved practice")
        require(item["left"] != item["right"], f"{ident}: self-comparison")
        require(isinstance(item["context_decisions"], list), f"{ident}: decisions must be a list")
        seen = set()
        for decision in item["context_decisions"]:
            fields(decision, {"dimension", "decision", "rationale", "evidence_ids"}, set(), ident + ".decision")
            require(decision["dimension"] in DIMENSIONS and decision["dimension"] not in seen, f"{ident}: unknown/repeated context dimension")
            seen.add(decision["dimension"])
            require(decision["decision"] in ("aligned_for_outcome", "material_difference", "unresolved"), f"{ident}: unknown context decision")
            text(decision["rationale"], ident + ".rationale")
            references(decision["evidence_ids"], evidence, ident)
    return evidence, practices, pairs


def current(item: dict[str, Any], as_of: str) -> bool:
    return item["observed_on"] <= as_of <= item["valid_through"]


def support(practice: dict[str, Any], evidence: dict[str, Any], as_of: str) -> dict[str, Any]:
    direct = sorted(ref for ref in practice["evidence_ids"]
                    if evidence[ref]["kind"] == "observation" and current(evidence[ref], as_of))
    inactive = sorted(ref for ref in practice["evidence_ids"] if not current(evidence[ref], as_of))
    claim = practice["claim"]
    if practice["dissent_ids"]:
        state = "DISPUTED"
    elif claim == "not_applicable":
        state = "NOT_APPLICABLE"
    elif claim == "unknown":
        state = "UNKNOWN"
    elif not direct:
        state = "INSUFFICIENT_DIRECT_EVIDENCE"
    else:
        state = "SUPPORTED_MEETS" if claim == "meets" else "SUPPORTED_GAP"
    return {"state": state, "claim": claim, "basis": practice["basis"], "direct_evidence": direct,
            "inactive_evidence": inactive, "dissent_ids": sorted(practice["dissent_ids"]),
            "provenance_clusters": sorted({evidence[ref]["independence_key"] for ref in direct})}


def context(left: dict[str, Any], right: dict[str, Any], pair: dict[str, Any], evidence: dict[str, Any], as_of: str) -> dict[str, Any]:
    decisions = {row["dimension"]: row for row in pair["context_decisions"]}
    rows = []
    for dimension in DIMENSIONS:
        a, b = left["context"][dimension], right["context"][dimension]
        decision = decisions.get(dimension)
        usable = decision and any(current(evidence[r], as_of) and evidence[r]["kind"] != "interview"
                                  for r in decision["evidence_ids"])
        if a is None or b is None:
            state = "UNKNOWN"
        elif decision is not None:
            # Explicit dissent or unresolved judgments take precedence over matching labels.
            if decision["decision"] == "material_difference":
                state = "MATERIAL_DIFFERENCE"
            elif decision["decision"] == "aligned_for_outcome" and usable:
                state = "ALIGNED_BY_RECORDED_JUDGMENT"
            else:
                state = "UNRESOLVED"
        elif a == b:
            state = "MATCHED_RECORDED_CONTEXT"
        else:
            state = "UNRESOLVED"
        rows.append({"dimension": dimension, "left": a, "right": b, "state": state, "decision": decision})
    states = {row["state"] for row in rows}
    status = "NOT_COMPARABLE" if "MATERIAL_DIFFERENCE" in states else (
        "UNRESOLVED" if states & {"UNKNOWN", "UNRESOLVED"} else "ALIGNED")
    return {"state": status, "dimensions": rows}


def rates(left: dict[str, Any], right: dict[str, Any], comparable: bool) -> dict[str, Any]:
    a, b = left.get("measurement"), right.get("measurement")
    result = {"state": "NOT_REQUESTED", "left": a, "right": b, "delta_fraction": None}
    if a is None and b is None:
        return result
    if a is None or b is None:
        result["state"] = "MISSING_MEASUREMENT"
    elif not comparable:
        result["state"] = "COMPARISON_NOT_ESTABLISHED"
    elif any(a[key] != b[key] for key in ("definition", "population", "window_start", "window_end")):
        result["state"] = "INCOMPARABLE_MEASUREMENTS"
    elif any(m["numerator"] is None or m["denominator"] is None for m in (a, b)):
        result["state"] = "MISSING_COUNTS"
    elif any(m["denominator"] == 0 for m in (a, b)):
        result["state"] = "NO_OBSERVED_OPPORTUNITIES"
    else:
        fa, fb = Fraction(a["numerator"], a["denominator"]), Fraction(b["numerator"], b["denominator"])
        result.update(state="DESCRIPTIVE_ONLY", left_fraction=str(fa), right_fraction=str(fb), delta_fraction=str(fa - fb))
    return result


def analyze(packet: dict[str, Any]) -> dict[str, Any]:
    evidence, practices, pairs = validate(packet)
    results = []
    for ident, pair in sorted(pairs.items()):
        left, right = practices[pair["left"]], practices[pair["right"]]
        a, b = (support(p, evidence, packet["as_of"]) for p in (left, right))
        ctx = context(left, right, pair, evidence, packet["as_of"])
        same = left["area"] == right["area"] and left["outcome"] == right["outcome"]
        states = {a["state"], b["state"]}
        if not same:
            verdict = "DIFFERENT_OUTCOME_DEFINITIONS"
        elif ctx["state"] != "ALIGNED":
            verdict = "CONTEXT_" + ctx["state"]
        elif "DISPUTED" in states:
            verdict = "DISPUTED"
        elif "NOT_APPLICABLE" in states:
            verdict = "NOT_APPLICABLE"
        elif not states <= {"SUPPORTED_MEETS", "SUPPORTED_GAP"}:
            verdict = "INSUFFICIENT_EVIDENCE"
        elif states == {"SUPPORTED_MEETS"}:
            verdict = "EQUIVALENT_OUTCOME_IN_SUPPLIED_SAMPLE"
        elif states == {"SUPPORTED_GAP"}:
            verdict = "SHARED_GAP_IN_SUPPLIED_SAMPLE"
        else:
            verdict = "DIFFERENT_OUTCOMES_IN_SUPPLIED_SAMPLE"
        shared = sorted(set(a["provenance_clusters"]) & set(b["provenance_clusters"]))
        refs = set(left["evidence_ids"] + right["evidence_ids"] + left["dissent_ids"] + right["dissent_ids"])
        for decision in pair["context_decisions"]:
            refs.update(decision["evidence_ids"])
        results.append({"id": ident, "left": left, "right": right, "left_support": a, "right_support": b,
                        "outcome_aligned": same, "context": ctx, "verdict": verdict,
                        "shared_provenance_clusters": shared,
                        "distinct_provenance_clusters": len(set(a["provenance_clusters"]) | set(b["provenance_clusters"])),
                        "measurement": rates(left, right, same and ctx["state"] == "ALIGNED" and states <= {"SUPPORTED_MEETS", "SUPPORTED_GAP"}),
                        "follow_up": follow_up(same, ctx, a, b),
                        "citations": [evidence[r] for r in sorted(refs)]})
    canonical = json.dumps(packet, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    return {"schema": SCHEMA + "/report", "synthetic": packet["synthetic"], "as_of": packet["as_of"],
            "input_sha256": hashlib.sha256(canonical).hexdigest(),
            "interpretation": "Supplied-record comparisons, not verified sources, institutional findings, maturity scores, statistical equivalence, or approvals.",
            "summary": dict(sorted(Counter(r["verdict"] for r in results).items())), "pairs": copy.deepcopy(results)}


def follow_up(same: bool, ctx: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    questions = []
    if not same:
        questions.append("Which exact outcome definition and version should be applied to both samples?")
    for row in ctx["dimensions"]:
        if row["state"] in ("UNKNOWN", "UNRESOLVED"):
            questions.append(f"What dated source establishes {row['dimension']} and whether its difference matters to this outcome?")
        elif row["state"] == "MATERIAL_DIFFERENCE":
            questions.append(f"Which locally appropriate outcome or additional exercise addresses the {row['dimension']} difference?")
    for side, support_row in (("left", a), ("right", b)):
        if support_row["state"] == "DISPUTED":
            questions.append(f"For {side}, reconcile the retained dissent against the same service, period and outcome; what remains unresolved?")
        elif support_row["state"] in ("UNKNOWN", "INSUFFICIENT_DIRECT_EVIDENCE"):
            questions.append(f"For {side}, can a current completed example with source locator establish the practice, rather than policy alone?")
        elif support_row["state"] == "NOT_APPLICABLE":
            questions.append(f"For {side}, which scope record confirms the stated applicability reason?")
    return questions


def escape(value: Any) -> str:
    raw = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for symbol in ("\\", "`", "*", "_", "[", "]", "(", ")", "!", "#", "|"):
        raw = raw.replace(symbol, "\\" + symbol)
    return raw.replace("\n", "<br>")


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Cross-stack calibration rehearsal", "", "**SYNTHETIC**" if report["synthetic"] else "**ASSESSMENT PREPARATION — NOT VERIFIED FINDINGS**", "", report["interpretation"], "", f"As of: {report['as_of']}; input SHA-256: `{report['input_sha256']}`.", ""]
    for row in report["pairs"]:
        lines += [f"## {escape(row['id'])}: {escape(row['verdict'])}", "",
                  f"{escape(row['left']['group'])} / {escape(row['left']['id'])} ({escape(row['left']['implementation'])}) versus {escape(row['right']['group'])} / {escape(row['right']['id'])} ({escape(row['right']['implementation'])}).",
                  f"Outcome definitions aligned: {row['outcome_aligned']}. Context: {row['context']['state']}.", "",
                  "| Dimension | Left | Right | Treatment |", "| --- | --- | --- | --- |"]
        for dim in row["context"]["dimensions"]:
            lines.append("| " + " | ".join(escape(dim[k]) for k in ("dimension", "left", "right", "state")) + " |")
        for dim in row["context"]["dimensions"]:
            if dim["decision"]:
                lines.append(f"\nRecorded judgment ({escape(dim['dimension'])}): {escape(dim['decision']['rationale'])}\n")
        for side in ("left", "right"):
            s = row[side + "_support"]
            lines += ["", f"**{side.title()}: {s['state']}** — {escape(s['basis'])}",
                      f"Direct support: {escape(', '.join(s['direct_evidence']) or 'none')}; inactive support: {escape(', '.join(s['inactive_evidence']) or 'none')}; unresolved dissent: {escape(', '.join(s['dissent_ids']) or 'none')}."]
        lines += ["", f"Distinct provenance clusters: {row['distinct_provenance_clusters']}; shared: {escape(', '.join(row['shared_provenance_clusters']) or 'none')}. These are provenance groups, **not a statistical sample size**.",
                  "", "Measurement comparison: `" + escape(json.dumps(row["measurement"], ensure_ascii=False, sort_keys=True)) + "`.",
                  "", "Source locators (analyst-supplied; contents not fetched):"]
        lines += [f"- {escape(c['id'])}: {escape(c['source'])} — {escape(c['locator'])} ({c['kind']}, {c['observed_on']} through {c['valid_through']})." for c in row["citations"]]
        if row["follow_up"]:
            lines += ["", "Focused follow-up:"] + ["- " + escape(q) for q in row["follow_up"]]
        lines.append("")
    return "\n".join(lines) + "\n"


def spreadsheet_text(value: Any) -> str:
    raw = "" if value is None else str(value)
    # Human-readable CSV view, not the lossless JSON interchange contract.
    return "'" + raw if raw.lstrip().startswith(("=", "+", "-", "@")) or raw.startswith(("\t", "\r")) else raw


def comparison_csv(report: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["synthetic", "as_of", "pair_id", "left_id", "right_id", "area", "verdict", "left_support", "right_support", "context", "distinct_provenance_clusters", "shared_provenance_clusters", "measurement_status", "delta_fraction", "input_sha256"])
    for r in report["pairs"]:
        writer.writerow([spreadsheet_text(v) for v in (report["synthetic"], report["as_of"], r["id"], r["left"]["id"], r["right"]["id"], r["left"]["area"], r["verdict"], r["left_support"]["state"], r["right_support"]["state"], r["context"]["state"], r["distinct_provenance_clusters"], ";".join(r["shared_provenance_clusters"]), r["measurement"]["state"], r["measurement"]["delta_fraction"], report["input_sha256"])])
    return output.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--format", choices=("json", "csv", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        report = analyze(load(args.input))
        result = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n" if args.format == "json" else (comparison_csv(report) if args.format == "csv" else markdown(report))
        sys.stdout.write(result)
    except (InputError, OSError, ValueError, TypeError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
