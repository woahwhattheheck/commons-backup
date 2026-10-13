"""Offline descriptive case-mix comparisons; no inference about a population or cause."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import sys
from datetime import date
from fractions import Fraction
from html import escape
from itertools import combinations
from pathlib import Path

SCHEMA = "tjlabs.case-mix.input/v1"
LIMIT = 262144
METRIC_KEYS = {"event_definition", "eligible_definition", "strata_definition", "unit",
               "window_start", "window_end", "direction", "measure_class"}


class InputError(ValueError):
    """The supplied record cannot be interpreted under this measurement contract."""


def _require(condition, message):
    if not condition:
        raise InputError(message)


def _text(value, location):
    _require(type(value) is str and 0 < len(value) <= 2048, location + ": text required")
    _require(not any(ord(c) < 32 and c not in "\n\t" for c in value), location + ": control character")
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise InputError(location + ": invalid Unicode") from exc
    return value


def _keys(value, expected, location):
    _require(type(value) is dict and set(value) == expected, location + ": unexpected or missing fields")


def _integer(value, location):
    _require(type(value) is int and 0 <= value <= 10**9, location + ": count must be an integer in [0, 1000000000]")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def loads(text):
    try:
        if type(text) is bytes:
            text = text.decode("utf-8", "strict")
        _require(type(text) is str and len(text.encode("utf-8")) <= LIMIT, "input exceeds 256 KiB")
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(InputError("nonfinite JSON: " + value)))
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("invalid JSON: " + str(exc)) from exc


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def validate(packet):
    _keys(packet, {"schema", "synthetic", "population_note", "reference", "groups"}, "packet")
    _require(packet["schema"] == SCHEMA, "unsupported schema")
    _require(type(packet["synthetic"]) is bool, "synthetic must be boolean")
    _text(packet["population_note"], "population_note")
    ref = packet["reference"]
    _keys(ref, {"rationale", "weights"}, "reference")
    _text(ref["rationale"], "reference.rationale")
    _require(type(ref["weights"]) is dict and 1 <= len(ref["weights"]) <= 64, "1..64 reference strata required")
    weights = {}
    for name, value in ref["weights"].items():
        _text(name, "reference stratum")
        _require(type(value) is str and 0 < len(value) <= 40, "weights must be short exact rational strings")
        try:
            weight = Fraction(value)
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            raise InputError("invalid reference weight: " + name) from exc
        _require(0 <= weight <= 1 and weight.denominator <= 10**9, "weight outside permitted range")
        weights[name] = weight
    _require(sum(weights.values()) == 1, "reference weights must sum exactly to 1; no implicit renormalization")
    _require(type(packet["groups"]) is list and 2 <= len(packet["groups"]) <= 20, "2..20 groups required")
    seen = set()
    for group in packet["groups"]:
        _keys(group, {"id", "label", "metric", "rows"}, "group")
        ident = _text(group["id"], "group.id")
        _require(ident not in seen, "duplicate group id: " + ident)
        seen.add(ident)
        _text(group["label"], ident + ".label")
        metric = group["metric"]
        _keys(metric, METRIC_KEYS, ident + ".metric")
        for key, value in metric.items():
            _text(value, ident + ".metric." + key)
        _require(metric["direction"] in {"higher_is_better", "lower_is_better"}, "unknown metric direction")
        _require(metric["measure_class"] in {"observed_outcome", "target", "unknown"}, "unknown measure class")
        try:
            start, end = date.fromisoformat(metric["window_start"]), date.fromisoformat(metric["window_end"])
            _require(start.isoformat() == metric["window_start"] and end.isoformat() == metric["window_end"], "use YYYY-MM-DD dates")
            _require(start < end, "measurement window must have positive length")
        except ValueError as exc:
            if isinstance(exc, InputError):
                raise
            raise InputError("invalid measurement window") from exc
        _require(type(group["rows"]) is list and len(group["rows"]) <= 64, "rows must be a list of at most 64 strata")
        strata = set()
        for row in group["rows"]:
            _keys(row, {"stratum", "events", "non_events", "unknown", "sources"}, ident + ".row")
            name = _text(row["stratum"], "row.stratum")
            _require(name in weights, "row stratum absent from reference universe: " + name)
            _require(name not in strata, "duplicate group/stratum: " + ident + "/" + name)
            strata.add(name)
            for key in ("events", "non_events", "unknown"):
                _integer(row[key], ident + "/" + name + "/" + key)
            _require(type(row["sources"]) is list and 1 <= len(row["sources"]) <= 20, "each row needs 1..20 source locators")
            for source in row["sources"]:
                _text(source, "source locator")
    return weights


def _bounds(row):
    if row is None:
        return Fraction(0), Fraction(1), "ABSENT_STRATUM"
    total = row["events"] + row["non_events"] + row["unknown"]
    if total == 0:
        return Fraction(0), Fraction(1), "NO_ELIGIBLE_RECORDS"
    return (Fraction(row["events"], total), Fraction(row["events"] + row["unknown"], total),
            "UNKNOWN_OUTCOMES" if row["unknown"] else "COMPLETE_COUNTS")


def _rate(low, high):
    return {"low": str(low), "high": str(high), "point": str(low) if low == high else None}


def _order(a, b):
    lo, hi = Fraction(a["low"]) - Fraction(b["high"]), Fraction(a["high"]) - Fraction(b["low"])
    order = "A_HIGHER" if lo > 0 else "B_HIGHER" if hi < 0 else "EQUAL" if lo == hi == 0 else "UNRESOLVED"
    return {"order": order, "difference": _rate(lo, hi)}


def analyze(packet):
    """Return exact descriptive bounds. Python callers supply ordinary trusted JSON data."""
    try:
        frozen = loads(canonical(packet))
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise InputError("input must be finite JSON data: " + str(exc)) from exc
    weights = validate(frozen)
    groups = []
    for group in sorted(frozen["groups"], key=lambda g: g["id"]):
        rows = {r["stratum"]: r for r in group["rows"]}
        totals = {k: sum(r[k] for r in rows.values()) for k in ("events", "non_events", "unknown")}
        total = sum(totals.values())
        raw_low, raw_high, raw_state = _bounds(totals)
        low, high, coverage = Fraction(0), Fraction(0), Fraction(0)
        strata = []
        for name, weight in sorted(weights.items()):
            row = rows.get(name)
            left, right, state = _bounds(row)
            if row is not None and sum(row[k] for k in ("events", "non_events", "unknown")) > 0:
                coverage += weight
            low += weight * left
            high += weight * right
            strata.append({"stratum": name, "weight": str(weight), "state": state,
                           "rate": _rate(left, right), "counts": copy.deepcopy(row)})
        groups.append({"id": group["id"], "label": group["label"], "metric": group["metric"],
                       "raw": _rate(raw_low, raw_high), "raw_state": raw_state,
                       "recorded_eligible": total, "totals": totals,
                       "raw_scope": "Supplied rows only; absent categories do not imply zero population.",
                       "standardized": _rate(low, high), "reference_coverage": str(coverage), "strata": strata})
    comparisons = []
    for a, b in combinations(groups, 2):
        mismatches = sorted(k for k in METRIC_KEYS if a["metric"][k] != b["metric"][k])
        reasons = ["DEFINITION_MISMATCH:" + k for k in mismatches]
        if any(g["metric"]["measure_class"] != "observed_outcome" for g in (a, b)):
            reasons.append("NON_OUTCOME_MEASURE")
        pair = {"a": a["id"], "b": b["id"], "eligibility": "DECLARED_DEFINITIONS_MATCH" if not reasons else "NOT_COMPARABLE",
                "reasons": reasons, "raw": None, "standardized": None, "strata": [], "uniform_reversal": "NOT_ASSESSABLE"}
        if not reasons:
            pair["raw"] = _order(a["raw"], b["raw"]) if a["recorded_eligible"] and b["recorded_eligible"] else None
            pair["standardized"] = _order(a["standardized"], b["standardized"])
            for left, right in zip(a["strata"], b["strata"]):
                pair["strata"].append({"stratum": left["stratum"], **_order(left["rate"], right["rate"])})
            orders = {row["order"] for row in pair["strata"]}
            missing = any(row["state"] in {"ABSENT_STRATUM", "NO_ELIGIBLE_RECORDS"} for g in (a, b) for row in g["strata"])
            if not missing and pair["raw"]:
                raw_order = pair["raw"]["order"]
                opposite = "B_HIGHER" if raw_order == "A_HIGHER" else "A_HIGHER" if raw_order == "B_HIGHER" else None
                pair["uniform_reversal"] = ("ROBUST_WITHIN_SUPPLIED_OUTCOME_BOUNDS" if opposite and orders == {opposite}
                                              else "NOT_DEMONSTRATED")
        comparisons.append(pair)
    return {"schema": "tjlabs.case-mix.report/v1", "synthetic": frozen["synthetic"],
            "input_sha256": hashlib.sha256(canonical(frozen).encode("utf-8")).hexdigest(),
            "boundary": "Descriptive supplied-record arithmetic, not statistical significance, causation, institutional findings or a maturity ranking. Definition equality is caller-declared, not independently authenticated.",
            "input": frozen, "groups": groups, "comparisons": comparisons}


def _cell(value):
    return escape(str(value), quote=True).replace("|", "\\|").replace("\n", "<br>").replace("\r", "")


def _display(rate):
    def percent(value):
        return f"{float(Fraction(value)) * 100:.3f}%"
    if rate["point"] is not None:
        return percent(rate["point"]) + " (" + rate["point"] + ")"
    return percent(rate["low"]) + " to " + percent(rate["high"]) + " [" + rate["low"] + ", " + rate["high"] + "]"


def markdown(report):
    out = ["# Case-mix comparison", "", "**SYNTHETIC REHEARSAL**" if report["synthetic"] else "**SUPPLIED DATA — provenance not independently verified**", "",
           report["boundary"], "", "Input digest (canonical JSON, not authenticity): `" + report["input_sha256"] + "`", "",
           "Population: " + _cell(report["input"]["population_note"]), "",
           "Reference rationale: " + _cell(report["input"]["reference"]["rationale"]), "",
           "| Group | Recorded eligible | Unknown outcomes | Raw supplied-row rate | Common-mix rate | Reference coverage |",
           "|---|---:|---:|---|---|---|"]
    for group in report["groups"]:
        out.append("| " + " | ".join(_cell(x) for x in (group["id"] + " — " + group["label"], group["recorded_eligible"], group["totals"]["unknown"],
                                                        _display(group["raw"]), _display(group["standardized"]), group["reference_coverage"])) + " |")
    for group in report["groups"]:
        out += ["", "## " + _cell(group["id"]) + " — retained measurement definition", ""]
        for key, value in sorted(group["metric"].items()):
            out.append("- **" + key + ":** " + _cell(value))
        out += ["", "| Category | Reference weight | Events / non-events / unknown | Rate or bounds | State | Sources |", "|---|---|---|---|---|---|"]
        for row in group["strata"]:
            counts = row["counts"]
            values = "absent" if counts is None else " / ".join(str(counts[k]) for k in ("events", "non_events", "unknown"))
            sources = "unavailable" if counts is None else "; ".join(counts["sources"])
            out.append("| " + " | ".join(_cell(x) for x in (row["stratum"], row["weight"], values, _display(row["rate"]), row["state"], sources)) + " |")
    out += ["", "## Pairwise descriptions — higher does not necessarily mean better", ""]
    for pair in report["comparisons"]:
        out.append("### " + _cell(pair["a"]) + " versus " + _cell(pair["b"]))
        out.append("Eligibility: " + pair["eligibility"] + ". " + _cell("; ".join(pair["reasons"])))
        if pair["standardized"]:
            out.append("Raw supplied-row order: " + (pair["raw"]["order"] if pair["raw"] else "NO_RECORDS") + "; common-mix order: " + pair["standardized"]["order"] + ".")
            out.append("Uniform aggregate reversal: " + pair["uniform_reversal"] + ".")
            out.append("Common-mix difference (first minus second): " + _cell(_display(pair["standardized"]["difference"])) + ".")
        out.append("")
    out += ["## Interpretation", "", "Bounds vary only the supplied unknown outcomes and absent-category rates from 0 to 1. They are not confidence intervals; selection bias, outcome misclassification, dependence and sampling uncertainty remain unmeasured.", "",
            "A common reference mix is an explicit comparison scenario, not a claim about either group's actual workload or a population estimate. No missing category is dropped or renormalized. Original definitions, counts and source locators remain in the JSON report.", ""]
    return "\n".join(out)


def demo(case="reversal"):
    metric = {"event_definition": "Sampled change completed without rollback within seven calendar days",
              "eligible_definition": "Sampled changes initiated in the window; unknown follow-up remains in the denominator",
              "strata_definition": "routine: one-system standard change; complex: multi-system coordinated change",
              "unit": "sampled change", "window_start": "2026-01-01", "window_end": "2026-04-01",
              "direction": "higher_is_better", "measure_class": "observed_outcome"}
    def row(name, events, other, unknown, group):
        return {"stratum": name, "events": events, "non_events": other, "unknown": unknown, "sources": ["synthetic:" + group + "/" + name]}
    packet = {"schema": SCHEMA, "synthetic": True, "population_note": "Invented A/B sampled change records; not University records or a population census. Window is start-inclusive/end-exclusive.",
              "reference": {"rationale": "Fictional 50/50 routine/complex comparison scenario, chosen explicitly rather than estimated from either group.", "weights": {"routine": "1/2", "complex": "1/2"}},
              "groups": [{"id": "A", "label": "Fictional routine-heavy team", "metric": copy.deepcopy(metric), "rows": [row("routine", 90, 10, 0, "A"), row("complex", 1, 9, 0, "A")]},
                         {"id": "B", "label": "Fictional complex-heavy team", "metric": copy.deepcopy(metric), "rows": [row("routine", 19, 1, 0, "B"), row("complex", 50, 50, 0, "B")]}]}
    if case == "missing-outcomes":
        packet["groups"][1]["rows"][1].update(non_events=30, unknown=20)
    elif case == "missing-category":
        packet["groups"][1]["rows"].pop()
    elif case == "incompatible-definition":
        packet["groups"][1]["metric"]["event_definition"] = "Sampled change completed without rollback within one calendar day"
    elif case != "reversal":
        raise InputError("unknown demo case")
    return packet


def audit_peer_csv(text):
    """Preserve the existing 019 table; never reverse-engineer counts from a percentage."""
    _require(type(text) is str and len(text.encode("utf-8")) <= LIMIT, "peer table exceeds 256 KiB")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = reader.fieldnames or []
    _require(len(headers) == len(set(headers)), "duplicate CSV headers")
    required = {"peer", "metric_or_measure", "period_or_window", "denominator_or_scope", "measure_class", "comparison_status", "source_url"}
    _require(required <= set(headers), "missing 019 peer-table columns")
    records = []
    for number, row in enumerate(reader, 2):
        _require(None not in row and all(v is not None for v in row.values()), "malformed CSV row " + str(number))
        records.append({"record_number": number, "source": row, "numeric_conversion": "NOT_ATTEMPTED",
                        "next_input": "Bind event/non-event/unknown counts, category definitions and a common measurement contract; do not infer these from targets or percentages."})
    return {"schema": "tjlabs.case-mix.peer-table-review/v1", "record_count": len(records), "records": records,
            "boundary": "Source-row preservation only; this is not an assessment of the cited institutions or a numeric benchmark."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    d = commands.add_parser("demo", help="Run or export an explicitly fictional packet")
    d.add_argument("--case", choices=("reversal", "missing-outcomes", "missing-category", "incompatible-definition"), default="reversal")
    d.add_argument("--format", choices=("json", "markdown", "input"), default="markdown")
    c = commands.add_parser("compare", help="Read a supplied JSON packet; no network or input mutation")
    c.add_argument("path", type=Path)
    c.add_argument("--format", choices=("json", "markdown"), default="markdown")
    p = commands.add_parser("peer-table", help="Preserve and inspect the existing 019 CSV contract without converting it to rates")
    p.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "peer-table":
            with args.path.open("r", encoding="utf-8", newline="") as handle:
                result = audit_peer_csv(handle.read(LIMIT + 1))
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
        if args.command == "demo":
            packet = demo(args.case)
        else:
            with args.path.open("rb") as handle:
                packet = loads(handle.read(LIMIT + 1))
        result = packet if args.format == "input" else analyze(packet)
        print(markdown(result) if args.format == "markdown" else json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (OSError, UnicodeError, InputError, csv.Error) as exc:
        print("case-mix: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
