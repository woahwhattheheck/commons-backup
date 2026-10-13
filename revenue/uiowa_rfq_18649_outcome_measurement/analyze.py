#!/usr/bin/env python3
"""Validate and report UIOWA-087 recommendation-linked outcome measures.

The tool reports directional measurement evidence. It never attributes causality,
combines adoption and outcome into an effectiveness score, or rates individuals.
"""

from __future__ import annotations

import argparse
import csv
import json
import html
from fractions import Fraction
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


MEASURE_CLASSES = {"adoption", "outcome"}
DIRECTIONS = {"higher_better", "lower_better", "context_only"}
PERIOD_ROLES = {"baseline", "followup"}


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str
    key: str = ""


@dataclass(frozen=True)
class Comparison:
    measure_id: str
    recommendation_id: str
    assessment_area: str
    measure_class: str
    measure_name: str
    baseline_rate_pct: float | None
    followup_rate_pct: float | None
    absolute_change_pp: float | None
    comparability: str
    directional_signal: str
    baseline_evidence: str
    followup_evidence: str
    collection_effort_minutes: int | None
    interpretation_limit: str


REC_FIELDS = ("recommendation_id", "assessment_area", "title", "intended_change")
MEASURE_FIELDS = (
    "measure_id", "recommendation_id", "assessment_area", "measure_class",
    "measure_name", "numerator_definition", "denominator_definition", "unit",
    "direction", "evidence_source", "collection_cadence", "interpretation_limit",
)
OBS_FIELDS = (
    "measure_id", "period_id", "period_role", "numerator", "denominator",
    "population_definition", "evidence_locator",
)


def read_csv(path: str, required_fields: tuple[str, ...] = ()) -> list[dict[str, str]]:
    """Preserve field contents; reject layouts that DictReader would silently lose."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        try:
            headers = reader.fieldnames
            if not headers or any(not h.strip() for h in headers):
                raise ValueError(f"{path}: missing or blank CSV header")
            if len(headers) != len(set(headers)):
                raise ValueError(f"{path}: duplicate CSV header")
            missing = sorted(set(required_fields) - set(headers))
            if missing:
                raise ValueError(f"{path}: missing required columns: {', '.join(missing)}")
            rows = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"{path}: CSV row width mismatch ending at line {reader.line_num}")
                rows.append(row)
            return rows
        except csv.Error as exc:
            raise ValueError(f"{path}: CSV parse error at line {reader.line_num}: {exc}") from exc


def parse_nonnegative_int(raw: str, *, field: str, key: str, findings: list[Finding]) -> int | None:
    text = (raw or "").strip()
    if not text:
        findings.append(Finding("ERROR", "MISSING_COUNT", f"{field} is missing", key))
        return None
    try:
        value = int(text)
    except ValueError:
        findings.append(Finding("ERROR", "INVALID_COUNT", f"{field} must be an integer", key))
        return None
    if value < 0:
        findings.append(Finding("ERROR", "NEGATIVE_COUNT", f"{field} must be nonnegative", key))
        return None
    return value


def parse_effort(raw: str, key: str, findings: list[Finding]) -> int | None:
    text = (raw or "").strip()
    if not text:
        findings.append(Finding("WARNING", "EFFORT_UNKNOWN", "Collection effort is not estimated", key))
        return None
    try:
        value = int(text)
    except ValueError:
        findings.append(Finding("ERROR", "INVALID_EFFORT", "Collection effort must be an integer minute estimate", key))
        return None
    if value < 0:
        findings.append(Finding("ERROR", "INVALID_EFFORT", "Collection effort cannot be negative", key))
        return None
    return value


def unique_by(rows: list[dict[str, str]], key_name: str, findings: list[Finding]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        key = (row.get(key_name) or "").strip()
        if not key:
            findings.append(Finding("ERROR", "MISSING_ID", f"{key_name} missing at CSV record {index - 1}"))
            continue
        if key in result:
            findings.append(Finding("ERROR", "DUPLICATE_ID", f"Duplicate {key_name}: {key}", key))
            continue
        result[key] = row
    return result


def required(row: dict[str, str], fields: tuple[str, ...], key: str, findings: list[Finding]) -> None:
    for field in fields:
        if not (row.get(field) or "").strip():
            findings.append(Finding("ERROR", "MISSING_FIELD", f"{field} is required", key))


def validate_and_compare(
    recommendations: list[dict[str, str]],
    register: list[dict[str, str]],
    observations: list[dict[str, str]],
) -> tuple[list[Finding], list[Comparison]]:
    """Validate every supplied record before deriving eligible comparisons.

    Diagnostics are scoped by record kind and ID. An invalid observation or
    definition suppresses its measure, not valid unrelated measures. An invalid
    recommendation suppresses all measures that refer to it. The raw source
    rows remain the caller's evidence; duplicates are not silently reconciled.
    """
    rec_findings: list[Finding] = []
    recs = unique_by(recommendations, "recommendation_id", rec_findings)
    if not recommendations:
        rec_findings.append(Finding("ERROR", "EMPTY_RECOMMENDATIONS", "No recommendation definitions"))
    for rec_id, row in recs.items():
        required(row, REC_FIELDS[1:], rec_id, rec_findings)
    invalid_recs = {f.key for f in rec_findings if f.level == "ERROR"}

    findings: list[Finding] = []
    measures = unique_by(register, "measure_id", findings)
    ambiguous_measures = {f.key for f in findings if f.code == "DUPLICATE_ID"}
    if not register:
        findings.append(Finding("ERROR", "EMPTY_REGISTER", "No measure definitions"))
    efforts: dict[str, int | None] = {}
    for measure_id, row in measures.items():
        required(row, MEASURE_FIELDS[1:], measure_id, findings)
        rec_id = (row.get("recommendation_id") or "").strip()
        if rec_id and rec_id not in recs:
            findings.append(Finding("ERROR", "BROKEN_RECOMMENDATION_LINK", f"Unknown recommendation {rec_id}", measure_id))
        elif rec_id in invalid_recs:
            findings.append(Finding("ERROR", "INVALID_RECOMMENDATION", f"Recommendation {rec_id} has invalid or ambiguous metadata", measure_id))
        for field, choices, code in (
            ("measure_class", MEASURE_CLASSES, "INVALID_MEASURE_CLASS"),
            ("direction", DIRECTIONS, "INVALID_DIRECTION"),
            ("unit", {"percent"}, "UNSUPPORTED_UNIT"),
        ):
            value = (row.get(field) or "").strip()
            if value and value not in choices:
                findings.append(Finding("ERROR", code, f"{field} must be one of {sorted(choices)}", measure_id))
        efforts[measure_id] = parse_effort(row.get("estimated_minutes_per_cycle", ""), measure_id, findings)
    invalid_measures = {f.key for f in findings if f.level == "ERROR"}
    findings = rec_findings + findings

    grouped: dict[str, dict[str, dict[str, str]]] = {}
    counts: dict[tuple[str, str], tuple[int | None, int | None]] = {}
    duplicate_roles: set[tuple[str, str]] = set()
    for record_number, row in enumerate(observations, start=1):
        measure_id = (row.get("measure_id") or "").strip()
        role = (row.get("period_role") or "").strip()
        key = f"{measure_id}:{role or '?'}"
        local: list[Finding] = []
        required(row, tuple(f for f in OBS_FIELDS if f not in {"numerator", "denominator"}), key, local)
        num = parse_nonnegative_int(row.get("numerator", ""), field="numerator", key=key, findings=local)
        den = parse_nonnegative_int(row.get("denominator", ""), field="denominator", key=key, findings=local)
        if den == 0:
            local.append(Finding("ERROR", "ZERO_DENOMINATOR", "Denominator cannot be zero", key))
        if num is not None and den not in (None, 0) and num > den:
            local.append(Finding("ERROR", "NUMERATOR_EXCEEDS_DENOMINATOR", "Numerator exceeds denominator", key))
        if measure_id not in measures:
            local.append(Finding("ERROR", "UNKNOWN_MEASURE", f"Observation references unknown measure {measure_id}", key))
        if role not in PERIOD_ROLES:
            local.append(Finding("ERROR", "INVALID_PERIOD_ROLE", f"Expected baseline or followup at CSV record {record_number}", key))
        period_key = (measure_id, role)
        if period_key in counts:
            duplicate_roles.add(period_key)
            local.append(Finding("ERROR", "DUPLICATE_PERIOD_ROLE", f"Duplicate {role} row for {measure_id}; no row is selected as authoritative", key))
        if any(f.level == "ERROR" for f in local) and measure_id in measures:
            invalid_measures.add(measure_id)
        findings.extend(local)
        if measure_id in measures and role in PERIOD_ROLES and period_key not in counts:
            grouped.setdefault(measure_id, {})[role] = row
            counts[period_key] = (num, den)

    comparisons: list[Comparison] = []
    for measure_id, measure in sorted(measures.items()):
        pair = grouped.get(measure_id, {})
        baseline, followup = pair.get("baseline"), pair.get("followup")
        for role, row in (("baseline", baseline), ("followup", followup)):
            if row is None:
                findings.append(Finding("WARNING", f"{role.upper()}_MISSING", f"No {role} observation", measure_id))
        if baseline is not None and followup is not None:
            b_period = (baseline.get("period_id") or "").strip()
            f_period = (followup.get("period_id") or "").strip()
            if b_period and b_period == f_period:
                findings.append(Finding("ERROR", "SAME_PERIOD", "Baseline and follow-up require distinct period_id values", measure_id))
                invalid_measures.add(measure_id)

        b_rate = f_rate = change = None
        comparability, signal = "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"
        b_evidence = (baseline or {}).get("evidence_locator", "")
        f_evidence = (followup or {}).get("evidence_locator", "")
        if (measure_id, "baseline") in duplicate_roles:
            b_evidence = ""
        if (measure_id, "followup") in duplicate_roles:
            f_evidence = ""

        if measure_id in invalid_measures:
            comparability = "INVALID_DATA"
        elif baseline is not None and followup is not None:
            if baseline["population_definition"].strip() != followup["population_definition"].strip():
                comparability = "NOT_COMPARABLE"
                findings.append(Finding("WARNING", "POPULATION_CHANGED", "Baseline and follow-up population definitions differ; direct rate comparison is suppressed", measure_id))
            else:
                # Validation above proves finite, nonnegative integer proportions.
                # Fraction avoids intermediate overflow and tolerance-based sign loss.
                b_num, b_den = counts[(measure_id, "baseline")]
                f_num, f_den = counts[(measure_id, "followup")]
                b_exact = Fraction(100 * b_num, b_den)
                f_exact = Fraction(100 * f_num, f_den)
                b_rate, f_rate, change = float(b_exact), float(f_exact), float(f_exact - b_exact)
                comparability = "COMPARABLE"
                direction = measure["direction"].strip()
                if b_exact == f_exact:
                    signal = "UNCHANGED"
                elif direction == "context_only":
                    signal = "CONTEXT_ONLY"
                else:
                    favorable = (f_exact > b_exact) == (direction == "higher_better")
                    signal = "FAVORABLE_DIRECTION" if favorable else "UNFAVORABLE_DIRECTION"

        ambiguous = measure_id in ambiguous_measures
        comparisons.append(Comparison(
            measure_id=measure_id,
            recommendation_id="" if ambiguous else (measure.get("recommendation_id") or "").strip(),
            assessment_area="" if ambiguous else (measure.get("assessment_area") or "").strip(),
            measure_class="" if ambiguous else (measure.get("measure_class") or "").strip(),
            measure_name="Ambiguous measure definition" if ambiguous else (measure.get("measure_name") or "").strip(),
            baseline_rate_pct=b_rate, followup_rate_pct=f_rate, absolute_change_pp=change,
            comparability=comparability, directional_signal=signal,
            baseline_evidence=b_evidence, followup_evidence=f_evidence,
            collection_effort_minutes=None if ambiguous else efforts[measure_id],
            interpretation_limit="Resolve duplicate measure definitions before interpretation." if ambiguous else (measure.get("interpretation_limit") or "").strip(),
        ))

    by_rec: dict[str, set[str]] = {}
    for measure_id, measure in measures.items():
        if measure_id not in ambiguous_measures:
            by_rec.setdefault((measure.get("recommendation_id") or "").strip(), set()).add((measure.get("measure_class") or "").strip())
    for rec_id in sorted(recs):
        classes = by_rec.get(rec_id, set())
        for cls, code in (("adoption", "ADOPTION_MEASURE_MISSING"), ("outcome", "OUTCOME_MEASURE_MISSING")):
            if cls not in classes:
                findings.append(Finding("WARNING", code, f"Recommendation has no {cls} measure", rec_id))
    return findings, comparisons


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}%"


def _fmt_pp(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.3g} pp" if 0 < abs(value) < 0.005 else f"{value:+.2f} pp"


def _cell(value: str) -> str:
    """Render source text without turning embedded pipes/newlines into table syntax."""
    return html.escape(value, quote=False).replace("|", "&#124;").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def render_markdown(
    recommendations: list[dict[str, str]],
    comparisons: list[Comparison],
    findings: list[Finding],
) -> str:
    rec_map = {}
    for row in recommendations:
        rec_id = (row.get("recommendation_id") or "").strip()
        if rec_id in rec_map:
            rec_map[rec_id] = {"title": "Ambiguous recommendation", "intended_change": "Resolve duplicate recommendation definitions."}
        else:
            rec_map[rec_id] = row
    out = [
        "# Synthetic improvement outcome-measurement report",
        "",
        "> Directional measurement evidence only. This report does not establish causality, release approval, maturity, compliance, or individual performance.",
        "",
    ]

    grouped: dict[str, list[Comparison]] = {}
    for comparison in comparisons:
        grouped.setdefault(comparison.recommendation_id, []).append(comparison)

    for rec_id, rows in sorted(grouped.items()):
        rec = rec_map.get(rec_id, {})
        out.extend(
            [
                f"## {_cell(rec_id)} — {_cell(rec.get('title', 'Unknown recommendation'))}",
                "",
                f"**Intended change:** {_cell(rec.get('intended_change', ''))}",
                "",
                "| Class | Measure | Baseline | Follow-up | Change | Comparability | Directional signal | Effort/cycle |",
                "| --- | --- | ---: | ---: | ---: | --- | --- | ---: |",
            ]
        )
        for row in sorted(rows, key=lambda r: (r.measure_class, r.measure_id)):
            effort = "—" if row.collection_effort_minutes is None else f"{row.collection_effort_minutes} min"
            out.append(
                f"| {_cell(row.measure_class)} | {_cell(row.measure_id)}: {_cell(row.measure_name)} | "
                f"{_fmt(row.baseline_rate_pct)} | {_fmt(row.followup_rate_pct)} | "
                f"{_fmt_pp(row.absolute_change_pp)} | {row.comparability} | "
                f"{row.directional_signal} | {effort} |"
            )
        out.extend(["", "### Evidence locators", "", "| Measure | Baseline source | Follow-up source |", "| --- | --- | --- |"])
        for row in sorted(rows, key=lambda r: r.measure_id):
            out.append(f"| {_cell(row.measure_id)} | {_cell(row.baseline_evidence) or 'Missing or ambiguous'} | {_cell(row.followup_evidence) or 'Missing or ambiguous'} |")
        out.extend(["", "### Interpretation limits", ""])
        for row in sorted(rows, key=lambda r: r.measure_id):
            out.append(f"- **{_cell(row.measure_id)}:** {_cell(row.interpretation_limit)}")
        out.append("")

    out.extend(["## Validation findings", ""])
    if findings:
        for finding in findings:
            key = f" [{_cell(finding.key)}]" if finding.key else ""
            out.append(f"- **{finding.level} {finding.code}**{key}: {_cell(finding.message)}")
    else:
        out.append("- No structural or comparability findings.")

    out.extend(
        [
            "",
            "## Reading rule",
            "",
            "Adoption and outcome rows are intentionally not averaged into a single effectiveness score. "
            "Favorable movement in both classes is useful evidence for follow-up discussion, but still does not establish that the recommendation caused the outcome change.",
            "",
        ]
    )
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "report"):
        p = sub.add_parser(command)
        p.add_argument("--recommendations", required=True)
        p.add_argument("--register", required=True)
        p.add_argument("--measurements", required=True)
        if command == "validate":
            p.add_argument("--json", action="store_true", dest="json_output")
        else:
            p.add_argument("-o", "--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        recs = read_csv(args.recommendations, REC_FIELDS)
        register = read_csv(args.register, MEASURE_FIELDS)
        observations = read_csv(args.measurements, OBS_FIELDS)
    except (OSError, UnicodeError, ValueError) as exc:
        finding = Finding("ERROR", "INPUT_ERROR", str(exc))
        if args.command == "validate" and args.json_output:
            print(json.dumps({"findings": [asdict(finding)], "comparisons": []}, indent=2, sort_keys=True))
        else:
            print(f"ERROR INPUT_ERROR: {exc}", file=sys.stderr)
        return 2
    findings, comparisons = validate_and_compare(recs, register, observations)

    if args.command == "validate":
        if args.json_output:
            print(
                json.dumps(
                    {
                        "findings": [asdict(f) for f in findings],
                        "comparisons": [asdict(c) for c in comparisons],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            for finding in findings:
                key = f" [{finding.key}]" if finding.key else ""
                print(f"{finding.level} {finding.code}{key}: {finding.message}")
            print(f"comparisons={len(comparisons)} errors={sum(f.level == 'ERROR' for f in findings)}")
    else:
        report = render_markdown(recs, comparisons, findings)
        if args.output:
            Path(args.output).write_text(report, encoding="utf-8")
        else:
            print(report)

    return 2 if any(f.level == "ERROR" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
