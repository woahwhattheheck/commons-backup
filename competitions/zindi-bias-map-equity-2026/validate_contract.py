#!/usr/bin/env python3
"""Offline contract checks for the 2026 Zindi Bias Mapping Equity challenge."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

REGION_ROWS = {
    "eastern-ok": 1192,
    "maricopa-az": 1593,
    "northern-ca": 591,
    "south-central-tx": 6003,
}
GEOID_RE = re.compile(r"^\d{11}$")
TARGET_NAME_RE = re.compile(
    r"(?:^|__|[-_])(target|truth|label|coverage_gap_score|transport_gap|building_gap|poi_gap)(?:$|__|[-_])",
    re.I,
)
PACKAGE_PREFIXES = (
    "https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/",
    "s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/",
    "s3://humane-intelligence/bias-bounty-mapping-equity-challenge/",
)
FORBIDDEN_SOURCE_TOKENS = (
    "coverage-gap",
    "coverage_gap",
    "ground-truth",
    "ground_truth",
    "reference-score",
    "reference_score",
    "microsoft-building",
    "microsoft_building",
    "tiger-road",
    "tiger_roads",
    "hifld",
    "county-business-pattern",
    "county_business_pattern",
    "/cbp",
    "_cbp",
    "-cbp",
)
ALLOWED_REFERENCE_FAMILIES = (
    "-overture-buildings.",
    "-overture-roads.",
    "-overture-roads-unfiltered.",
    "-overture-rail.",
    "-overture-infrastructure.",
    "-overture-pois.",
    "-census-acs-housing.",
    "-sample-submission.",
)


class ContractError(ValueError):
    pass


def read_csv(path: Path):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                raise ContractError(f"{path}: missing CSV header")
            fields = [x.strip() for x in reader.fieldnames]
            if len(fields) != len(set(fields)) or any(not x for x in fields):
                raise ContractError(f"{path}: invalid or duplicate CSV columns")
            return fields, [
                {k.strip(): (v.strip() if isinstance(v, str) else "") for k, v in row.items() if k}
                for row in reader
            ]
    except OSError as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc


def geoids(rows, label):
    seen = set()
    out = []
    for line, row in enumerate(rows, 2):
        value = row.get("GEOID", "")
        if not GEOID_RE.fullmatch(value):
            raise ContractError(f"{label}: row {line} GEOID must be 11-digit text; got {value!r}")
        if value in seen:
            raise ContractError(f"{label}: duplicate GEOID {value}")
        seen.add(value)
        out.append(value)
    return out


def validate_submission(sample: Path, candidate: Path, region: str):
    sample_fields, sample_rows = read_csv(sample)
    candidate_fields, candidate_rows = read_csv(candidate)
    if "GEOID" not in sample_fields:
        raise ContractError("official sample must contain GEOID")
    for required in ("GEOID", "coverage_gap_score"):
        if required not in candidate_fields:
            raise ContractError(f"candidate missing required column {required}")

    expected = REGION_ROWS[region]
    sample_ids = geoids(sample_rows, "sample")
    candidate_ids = geoids(candidate_rows, "candidate")
    if len(sample_ids) != expected:
        raise ContractError(f"sample has {len(sample_ids)} rows; current {region} contract is {expected}")
    if len(candidate_ids) != expected:
        raise ContractError(f"candidate has {len(candidate_ids)} rows; expected {expected}")

    missing = sorted(set(sample_ids) - set(candidate_ids))
    extra = sorted(set(candidate_ids) - set(sample_ids))
    if missing or extra:
        raise ContractError(f"candidate GEOID set differs from sample (missing={missing[:5]}, extra={extra[:5]})")

    for line, row in enumerate(candidate_rows, 2):
        for column in candidate_fields:
            if row.get(column, "") == "":
                raise ContractError(f"candidate row {line} has blank {column}")
        try:
            score = float(row["coverage_gap_score"])
        except ValueError as exc:
            raise ContractError(f"candidate row {line} score is not numeric") from exc
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ContractError(f"candidate row {line} score must be finite in [0,1]")

    return {
        "status": "PASS",
        "region": region,
        "rows": expected,
        "geoid_contract": "11-digit text; exact live sample set",
        "score_contract": "finite numeric [0,1]; no blanks",
    }


def normalize_source(source: str):
    value = source.strip().replace("\\", "/")
    for prefix in PACKAGE_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    if "://" in value:
        host = urlparse(value).netloc
        raise ContractError(f"feature source must be official Source Cooperative challenge data; unsupported host {host!r}")
    value = value.lstrip("./")
    if not value or value.startswith("../") or "/../" in value:
        raise ContractError(f"invalid feature source path {source!r}")
    return value


def validate_source(source: str):
    rel = normalize_source(source)
    low = rel.casefold()
    if any(token in low for token in FORBIDDEN_SOURCE_TOKENS):
        raise ContractError(f"forbidden target/reference source {source!r}")
    if low.startswith("reference/eastern-wa/"):
        raise ContractError("eastern-wa is not one of the four current scored regions")
    if low.startswith("reference/"):
        parts = rel.split("/", 2)
        if len(parts) != 3 or parts[1] not in REGION_ROWS:
            raise ContractError(f"unsupported reference region in {source!r}")
        filename = parts[2].casefold()
        if not any(family in filename for family in ALLOWED_REFERENCE_FAMILIES):
            raise ContractError(f"reference file family is outside the current live contract: {source!r}")
    elif not (low.startswith("strata/") or low.startswith("boundaries/")):
        raise ContractError(f"source is outside current challenge package areas: {source!r}")
    return rel


def validate_manifest(path: Path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractError(f"cannot read valid JSON manifest {path}: {exc}") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or not features:
        raise ContractError("manifest needs a non-empty features list")

    names = set()
    sources = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ContractError(f"feature {index} must be an object")
        name = feature.get("name")
        refs = feature.get("sources")
        if not isinstance(name, str) or not name.strip():
            raise ContractError(f"feature {index} needs a non-empty name")
        name = name.strip()
        if name in names:
            raise ContractError(f"duplicate feature name {name!r}")
        if TARGET_NAME_RE.search(name):
            raise ContractError(f"target-like feature name forbidden: {name!r}")
        names.add(name)
        if not isinstance(refs, list) or not refs:
            raise ContractError(f"feature {name!r} needs a non-empty sources list")
        for ref in refs:
            if not isinstance(ref, str) or not ref.strip():
                raise ContractError(f"feature {name!r} has invalid source")
            sources.add(validate_source(ref))

    return {
        "status": "PASS",
        "feature_count": len(names),
        "source_count": len(sources),
        "target_free": True,
        "regions": sorted(REGION_ROWS),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("submission")
    p.add_argument("--sample", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--region", choices=sorted(REGION_ROWS), required=True)

    p = sub.add_parser("manifest")
    p.add_argument("--manifest", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        report = (
            validate_submission(args.sample, args.candidate, args.region)
            if args.command == "submission"
            else validate_manifest(args.manifest)
        )
    except ContractError as exc:
        print(f"zindi-biasmap-contract: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
