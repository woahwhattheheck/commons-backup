#!/usr/bin/env python3
"""Describe outcome counts and explicitly conditional binomial precision offline."""
from __future__ import annotations

import argparse
import copy
from fractions import Fraction
import html
import json
import math
from pathlib import Path
import re
from statistics import NormalDist
import sys

SCHEMA = "uiowa-sample-precision/v1"
RESULT_SCHEMA = "uiowa-sample-precision-result/v1"
DESIGNS = {"independent_bernoulli", "convenience", "prepared_demo", "census",
           "clustered", "unknown"}
COUNT_LIMIT = 10**12
TEXT_FIELDS = ("id", "label", "unit", "outcome", "observation_window", "design_basis")
COUNT_FIELDS = ("eligible", "success", "failure", "unknown")
METHOD_URL = "https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm"


def _confidence(value):
    if (type(value) not in (int, float) or not 0.5 <= value <= 0.9999
            or not math.isfinite(value)):
        raise ValueError("confidence must be a finite number from 0.5 to 0.9999")
    return float(value)


def _count(value, name):
    if type(value) is not int or not 0 <= value <= COUNT_LIMIT:
        raise ValueError(f"{name} must be an integer from 0 to {COUNT_LIMIT}")
    return value


def wilson_interval(success, total, confidence=0.95):
    """Two-sided Wilson score interval; caller establishes the model's relevance."""
    success = _count(success, "success")
    total = _count(total, "total")
    level = _confidence(confidence)
    if total == 0 or success > total:
        raise ValueError("Wilson interval needs 0 <= success <= total and total > 0")
    z = NormalDist().inv_cdf((1 + level) / 2)
    z2 = z * z
    p = success / total
    denominator = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total**2)) / denominator
    lower = max(0.0, center - half)
    upper = min(1.0, center + half)
    # Preserve mathematically exact boundary endpoints despite floating-point noise.
    return (0.0 if success == 0 else lower,
            1.0 if success == total else upper)


def _rate(numerator, denominator):
    if denominator == 0:
        return None
    return {"numerator": numerator, "denominator": denominator,
            "ratio": numerator / denominator,
            "exact": str(Fraction(numerator, denominator))}


def _validate_sample(row, index, seen):
    prefix = f"samples[{index}]"
    if not isinstance(row, dict):
        raise ValueError(f"{prefix} must be an object")
    for field in TEXT_FIELDS:
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"{prefix}.{field} must be a nonempty string")
    if row["id"] in seen:
        raise ValueError(f"duplicate sample id: {row['id']}")
    seen.add(row["id"])
    for field in COUNT_FIELDS:
        _count(row.get(field), f"{prefix}.{field}")
    if row["success"] + row["failure"] + row["unknown"] != row["eligible"]:
        raise ValueError(f"{prefix}: success + failure + unknown must equal eligible")
    design = row.get("sampling_design")
    if not isinstance(design, str) or design not in DESIGNS:
        raise ValueError(f"{prefix}.sampling_design must be one of {sorted(DESIGNS)}")
    refs = row.get("source_refs")
    if (not isinstance(refs, list) or not refs
            or any(not isinstance(x, str) or not x.strip() for x in refs)):
        raise ValueError(f"{prefix}.source_refs must contain nonempty reference strings")


def evaluate(document):
    """Return a new result, retaining exact input values and extension fields."""
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError(f"input schema must be {SCHEMA}")
    if type(document.get("synthetic")) is not bool:
        raise ValueError("synthetic must be an explicit boolean")
    rows = document.get("samples")
    if not isinstance(rows, list):
        raise ValueError("samples must be a list")
    level = _confidence(document.get("confidence", 0.95))
    seen = set()
    for index, row in enumerate(rows):
        _validate_sample(row, index, seen)
    result = {"schema": RESULT_SCHEMA, "confidence": level,
              "synthetic": document["synthetic"],
              "input_context": copy.deepcopy({k: v for k, v in document.items()
                                               if k != "samples"}),
              "samples": [],
              "interpretation": [
                  "Counts describe separate collections; no pooled rate or ranking is produced.",
                  "Collection bounds vary only the unknown outcomes in the stated collection.",
                  "Sampling design is declared input, not a fact verified by this utility.",
                  "A Wilson interval is conditional on independent Bernoulli observations with a common probability.",
                  "Intervals are not maturity, evidence-confidence scores, future prediction or significance tests."]}
    for row in rows:
        total, successes = row["eligible"], row["success"]
        known = successes + row["failure"]
        unknown = row["unknown"]
        bounds = None if total == 0 else {
            "denominator": total, "lower": _rate(successes, total),
            "upper": _rate(successes + unknown, total)}
        reasons = []
        if row["sampling_design"] != "independent_bernoulli":
            reasons.append("SAMPLING_DESIGN_" + row["sampling_design"].upper())
        if unknown:
            reasons.append("INCOMPLETE_OUTCOMES")
        if known == 0:
            reasons.append("NO_OBSERVED_OUTCOMES")
        interval = {"status": "NOT_COMPUTED", "reasons": reasons, "level": level}
        if not reasons:
            lower, upper = wilson_interval(successes, total, level)
            interval.update(status="CONDITIONAL_MODEL", method="Wilson score",
                            lower=lower, upper=upper, source=METHOD_URL)
        notes = []
        if unknown:
            notes.append("Complete-case rate excludes unknown outcomes; do not report it as the full-collection rate.")
        if total == 0:
            notes.append("No eligible observations: rate and collection bounds are undefined, not zero.")
        elif known == 0:
            notes.append("All outcomes are unknown; collection bounds span 0 to 1.")
        if row["sampling_design"] != "independent_bernoulli":
            notes.append("Descriptive collection only; the independent-binomial model is not selected.")
        result["samples"].append({"input": copy.deepcopy(row), "known": known,
                                  "observed_rate": _rate(successes, known),
                                  "collection_bounds": bounds,
                                  "interval": interval, "notes": notes})
    return result


def _text(value):
    text = html.escape(str(value), quote=False).replace("|", "&#124;")
    for char in ("\\", "`", "*", "_", "[", "]"):
        text = text.replace(char, "\\" + char)
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " / ")


def _percentage(value):
    return f"{value * 100:.4f}%"


def _reference(value):
    if re.fullmatch(r"https?://[^\s<>]+", value):
        return f"[{_text(value)}](<{value}>)"
    return _text(value)


def _display_rate(value):
    if value is None:
        return "UNKNOWN (no observed outcomes)"
    return f"{value['numerator']}/{value['denominator']} ({_percentage(value['ratio'])})"


def render_markdown(result):
    banner = ("SYNTHETIC EXERCISE — fictional observations, not University findings."
              if result["synthetic"] else "Input is declared non-synthetic; source provenance has not been independently verified.")
    lines = ["# Denominators, unknown outcomes and conditional precision", "", banner, "",
             "Each row is a separate collection. Collection bounds are not statistical intervals.", "",
             "| Sample | Success / failure / unknown | Complete-case rate | Full-collection bounds | Wilson interval |",
             "|---|---|---|---|---|"]
    for row in result["samples"]:
        source, bounds, interval = row["input"], row["collection_bounds"], row["interval"]
        btext = "UNDEFINED (eligible = 0)" if bounds is None else (
            f"{bounds['lower']['exact']} to {bounds['upper']['exact']} "
            f"({_percentage(bounds['lower']['ratio'])}–{_percentage(bounds['upper']['ratio'])}); n={bounds['denominator']}")
        itext = (f"{_percentage(interval['lower'])}–{_percentage(interval['upper'])} "
                 f"at {interval['level'] * 100:g}%, model-conditional"
                 if interval["status"] == "CONDITIONAL_MODEL" else "NOT COMPUTED")
        lines.append(f"| {_text(source['id'])}: {_text(source['label'])} | "
                     f"{source['success']} / {source['failure']} / {source['unknown']} | "
                     f"{_display_rate(row['observed_rate'])} | {btext} | {itext} |")
    for row in result["samples"]:
        source, interval = row["input"], row["interval"]
        lines.extend(["", "## " + _text(source["id"]), "",
                      "- Outcome: " + _text(source["outcome"]),
                      "- Unit: " + _text(source["unit"]),
                      "- Observation window: " + _text(source["observation_window"]),
                      "- Declared sampling design: " + _text(source["sampling_design"]),
                      "- Basis supplied: " + _text(source["design_basis"]),
                      "- Eligible collection: " + str(source["eligible"]),
                      "- Interval status: " + interval["status"]])
        if interval["reasons"]:
            lines.append("- Reasons: " + ", ".join(interval["reasons"]))
        if source.get("retained_limit"):
            lines.append("- Source interpretation limit: " + _text(source["retained_limit"]))
        lines.extend("- " + _text(note) for note in row["notes"])
        lines.append("- Source references:")
        lines.extend("  - " + _reference(ref) for ref in source["source_refs"])
    lines.extend(["", "## Interpretation", ""])
    lines.extend("- " + item for item in result["interpretation"])
    lines.extend(["", f"Formula reference: [NIST §7.2.4.1]({METHOD_URL}).", ""])
    return "\n".join(lines)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"),
                              object_pairs_hook=_unique_object,
                              parse_constant=lambda value: (_ for _ in ()).throw(
                                  ValueError(f"non-finite JSON value: {value}")))
        result = evaluate(document)
        output = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True,
                             allow_nan=False) + "\n" if args.format == "json"
                  else render_markdown(result))
    except (OSError, UnicodeError, ValueError, OverflowError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
