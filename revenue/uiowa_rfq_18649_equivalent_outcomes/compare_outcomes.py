#!/usr/bin/env python3
"""Join native outcome comparison and explicit rating observations for review.

Implementation style never supplies a maturity rank. This offline adapter retains
both component reports and fills missing rating observations as unassessed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from revenue.uiowa_rfq_18649_cross_stack import compare
from revenue.uiowa_rfq_18649_rating_model import rating_model

SCHEMA = "uiowa-equivalent-outcomes/v1"
RATINGS_SCHEMA = SCHEMA + "/ratings"
NOTICE = ("Outcome equivalence describes supplied samples, not statistical equivalence. "
          "Maturity observations require separate explicit calibration; neither report "
          "establishes University findings, source authenticity or approval.")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def component_sources() -> dict[str, str]:
    return {str(Path(module.__file__).resolve().relative_to(ROOT)):
            hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in (compare, rating_model)}


def unassessed(practice: dict) -> dict:
    return {"criterion_id": practice["id"], "area": practice["area"],
            "service": practice["group"], "assessment_status": "unassessed"}


def ratings_template(packet: dict) -> dict:
    native = compare.analyze(packet)
    return {"schema": RATINGS_SCHEMA, "comparison_input_sha256": native["input_sha256"],
            "calibration": None,
            "criteria": [unassessed(p) for p in sorted(packet["practices"], key=lambda p: p["id"])]}


def rating_input(packet: dict, comparison: dict, observations: dict | None) -> tuple[dict, dict]:
    practices = {p["id"]: p for p in packet["practices"]}
    supplied: dict[str, dict] = {}
    calibration = None
    settings = {}
    if observations is not None:
        require(isinstance(observations, dict), "ratings must be an object")
        required = {"schema", "comparison_input_sha256", "calibration", "criteria"}
        require(required <= observations.keys() and observations.keys() <= required | {"settings"},
                "ratings require schema, comparison_input_sha256, calibration, criteria; only settings is optional")
        require(observations["schema"] == RATINGS_SCHEMA, "unsupported ratings schema")
        require(observations["comparison_input_sha256"] == comparison["input_sha256"],
                "ratings are bound to a different comparison input")
        calibration = observations["calibration"]
        if calibration is not None:
            require(isinstance(calibration, dict) and set(calibration) == {"reference", "version"},
                    "calibration must contain reference and version")
            require(all(isinstance(v, str) and v.strip() for v in calibration.values()),
                    "calibration reference and version must be nonblank")
        rows = observations["criteria"]
        require(isinstance(rows, list), "ratings criteria must be an array")
        required_row = {"criterion_id", "area", "service", "assessment_status"}
        optional_row = {"criticality", "maturity_rank", "maturity_label", "confidence",
                        "material_gap", "evidence_ids", "applicability_reason"}
        for row in rows:
            require(isinstance(row, dict) and required_row <= row.keys()
                    and row.keys() <= required_row | optional_row, "invalid native rating row fields")
            ident = row["criterion_id"]
            require(isinstance(ident, str) and ident in practices, "rating criterion_id must identify a compared practice")
            require(ident not in supplied, f"duplicate rating for {ident}")
            practice = practices[ident]
            require(row["area"] == practice["area"] and row["service"] == practice["group"],
                    f"{ident}: rating area/group differs from comparison practice")
            if row["assessment_status"] != "unassessed":
                require(calibration is not None, f"{ident}: an assessment/applicability decision requires explicit calibration")
            if row["assessment_status"] == "assessed":
                refs = row.get("evidence_ids")
                require(isinstance(refs, list) and bool(refs)
                        and all(isinstance(ref, str) for ref in refs), f"{ident}: assessed rating requires evidence IDs")
                require(len(refs) == len(set(refs)) and set(refs) <= set(practice["evidence_ids"] + practice["dissent_ids"]),
                        f"{ident}: rating evidence must be unique and retained by that practice")
            supplied[ident] = copy.deepcopy(row)
        settings = observations.get("settings", {})
    criteria = [supplied.get(ident, unassessed(practice)) for ident, practice in sorted(practices.items())]
    require(bool(criteria), "comparison has no practices to compose")
    payload = {"engagement": {"comparison_input_sha256": comparison["input_sha256"],
                              "synthetic": packet["synthetic"], "as_of": packet["as_of"]},
               "settings": copy.deepcopy(settings), "criteria": criteria}
    metadata = {"calibration": copy.deepcopy(calibration), "supplied_practice_ids": sorted(supplied),
                "unassessed_default_ids": sorted(set(practices) - set(supplied)),
                "ratings_input_sha256": None if observations is None else digest(observations)}
    return payload, metadata


def analyze(packet: dict, observations: dict | None = None) -> dict:
    sources = component_sources()
    comparison = compare.analyze(packet)
    native_input, metadata = rating_input(packet, comparison, observations)
    ratings = rating_model.compose(native_input)
    normalized = {r["criterion_id"]: r for r in rating_model.normalize_criteria(native_input)}
    rows = []
    for pair in comparison["pairs"]:
        row = {"pair_id": pair["id"], "verdict": pair["verdict"],
               "measurement": copy.deepcopy(pair["measurement"])}
        for side in ("left", "right"):
            practice = pair[side]
            rating = normalized[practice["id"]]
            row[side] = {"practice_id": practice["id"], "group": practice["group"],
                         "implementation": practice["implementation"],
                         "comparison_support": pair[side + "_support"]["state"],
                         "rating_status": rating["assessment_status"],
                         "maturity_rank": rating["maturity_rank"],
                         "maturity_label": rating["maturity_label"],
                         "confidence": rating["confidence"],
                         "rating_origin": "explicit_input" if practice["id"] in metadata["supplied_practice_ids"] else "unassessed_default"}
        rows.append(row)
    require(component_sources() == sources, "native component source changed during analysis")
    return {"schema": SCHEMA + "/report", "synthetic": packet["synthetic"], "as_of": packet["as_of"],
            "interpretation": NOTICE, "component_sources_sha256": sources,
            "rating_input": native_input, "rating_observations": metadata,
            "comparison": comparison, "ratings": ratings, "review_table": rows}


def markdown(report: dict) -> str:
    calibration = report["rating_observations"]["calibration"]
    calibration_text = "Calibration: NOT SUPPLIED."
    if calibration is not None:
        calibration_text = (f"Supplied calibration: {compare.escape(calibration['reference'])}; "
                            f"version {compare.escape(calibration['version'])}. Reference authenticity is not established here.")
    lines = ["# Equivalent-outcome review", "", NOTICE, "",
             "SYNTHETIC preparation" if report["synthetic"] else "Supplied-record preparation", "",
             calibration_text, "",
             "| Pair | Left practice / implementation | Right practice / implementation | Outcome verdict | Left rating | Right rating | Measurement |",
             "|---|---|---|---|---|---|---|"]
    for row in report["review_table"]:
        def side(which: str) -> str:
            item = row[which]
            return f"{item['group']} / {item['practice_id']} / {item['implementation']}"
        def rating(which: str) -> str:
            item = row[which]
            if item["rating_status"] != "assessed":
                return item["rating_status"]
            return f"{item['maturity_label']} (rank {item['maturity_rank']}); confidence {item['confidence']}; supplied calibration"
        measurement = row["measurement"]
        shown = measurement["state"]
        if measurement["state"] == "DESCRIPTIVE_ONLY":
            left, right = measurement["left"], measurement["right"]
            shown += (f"; {left['numerator']}/{left['denominator']} vs "
                      f"{right['numerator']}/{right['denominator']}; delta {measurement['delta_fraction']}")
        values = [row["pair_id"], side("left"), side("right"), row["verdict"], rating("left"), rating("right"), shown]
        lines.append("| " + " | ".join(compare.escape(v) for v in values) + " |")
    lines += ["", "Ratings are supplied separately; the comparison verdict never supplies a rank. "
              "Missing ratings remain unassessed even when both outcomes meet their supplied criterion. "
              "The native comparison below retains source locators, denominators, dissent, context and follow-up questions.", "",
              rating_model.render_markdown(report["ratings"]), "", compare.markdown(report["comparison"])]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparison", type=Path, help="Native cross-stack-calibration/v1 input")
    parser.add_argument("--ratings", type=Path, help="Explicit snapshot-bound calibration and native rating rows")
    parser.add_argument("--format", choices=("json", "markdown", "ratings-template"), default="json")
    args = parser.parse_args(argv)
    try:
        packet = compare.load(args.comparison)
        if args.format == "ratings-template":
            require(args.ratings is None, "ratings-template does not consume --ratings")
            result = ratings_template(packet)
        else:
            observations = compare.load(args.ratings) if args.ratings else None
            result = analyze(packet, observations)
        rendered = markdown(result) if args.format == "markdown" else json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        print(rendered, end="")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"equivalent-outcomes error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
