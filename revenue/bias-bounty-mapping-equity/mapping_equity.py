#!/usr/bin/env python3
"""Deterministic scorer/submission compiler for the Mapping Equity challenge.

This module deliberately consumes tract-level aggregates rather than geospatial files.
The geospatial aggregation step remains auditable and replaceable; this layer binds the
organizer's published ratio, undefined-component, and submission-universe semantics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

SCHEMA = "mapping-equity-coverage-gap/v1"
OVERTURE_RELEASE = "2026-08-19.0"
GEOID_RE = re.compile(r"^[0-9]{11}$")
AGGREGATE_COLUMNS = (
    "GEOID",
    "overture_road_length",
    "tiger_road_length",
    "overture_buildings",
    "microsoft_buildings",
    "overture_fire",
    "hifld_fire",
    "overture_ems",
    "hifld_ems",
    "overture_schools",
    "hifld_schools",
    "overture_places",
    "cbp_establishments",
)

class MappingEquityError(ValueError):
    pass


def _number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MappingEquityError(f"{name} must be a real number")
    out = float(value)
    if not math.isfinite(out) or out < 0:
        raise MappingEquityError(f"{name} must be finite and >= 0")
    return out


def _geoid(value: object) -> str:
    if not isinstance(value, str) or not GEOID_RE.fullmatch(value):
        raise MappingEquityError("GEOID must be an 11-digit text value")
    return value


def coverage_deficit(observed: object, reference: object, *, name: str) -> Optional[float]:
    """Return 1-min(1, observed/reference), or None if reference is zero."""
    obs = _number(f"{name}.observed", observed)
    ref = _number(f"{name}.reference", reference)
    if ref == 0:
        return None
    return 1.0 - min(1.0, obs / ref)


def _mean_defined(values: Iterable[Optional[float]]) -> Optional[float]:
    present = [float(v) for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


@dataclass(frozen=True)
class TractAggregate:
    geoid: str
    overture_road_length: float
    tiger_road_length: float
    overture_buildings: float
    microsoft_buildings: float
    overture_fire: float
    hifld_fire: float
    overture_ems: float
    hifld_ems: float
    overture_schools: float
    hifld_schools: float
    overture_places: float
    cbp_establishments: float

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "TractAggregate":
        return cls(
            geoid=_geoid(row["GEOID"]),
            overture_road_length=_number("overture_road_length", row["overture_road_length"]),
            tiger_road_length=_number("tiger_road_length", row["tiger_road_length"]),
            overture_buildings=_number("overture_buildings", row["overture_buildings"]),
            microsoft_buildings=_number("microsoft_buildings", row["microsoft_buildings"]),
            overture_fire=_number("overture_fire", row["overture_fire"]),
            hifld_fire=_number("hifld_fire", row["hifld_fire"]),
            overture_ems=_number("overture_ems", row["overture_ems"]),
            hifld_ems=_number("hifld_ems", row["hifld_ems"]),
            overture_schools=_number("overture_schools", row["overture_schools"]),
            hifld_schools=_number("hifld_schools", row["hifld_schools"]),
            overture_places=_number("overture_places", row["overture_places"]),
            cbp_establishments=_number("cbp_establishments", row["cbp_establishments"]),
        )


@dataclass(frozen=True)
class TractScore:
    geoid: str
    coverage_gap_score: float
    transport_gap: Optional[float]
    building_gap: Optional[float]
    poi_gap: Optional[float]
    poi_gap_hifld: Optional[float]
    poi_gap_fire: Optional[float]
    poi_gap_ems: Optional[float]
    poi_gap_schools: Optional[float]
    poi_gap_cbp: Optional[float]

    def canonical(self) -> dict[str, object]:
        return {
            "GEOID": self.geoid,
            "coverage_gap_score": self.coverage_gap_score,
            "transport_gap": self.transport_gap,
            "building_gap": self.building_gap,
            "poi_gap": self.poi_gap,
            "poi_gap_hifld": self.poi_gap_hifld,
            "poi_gap_fire": self.poi_gap_fire,
            "poi_gap_ems": self.poi_gap_ems,
            "poi_gap_schools": self.poi_gap_schools,
            "poi_gap_cbp": self.poi_gap_cbp,
            "transport_defined": self.transport_gap is not None,
            "building_defined": self.building_gap is not None,
            "poi_defined": self.poi_gap is not None,
        }


def score_tract(tract: TractAggregate) -> TractScore:
    transport = coverage_deficit(
        tract.overture_road_length, tract.tiger_road_length, name="transport"
    )
    building = coverage_deficit(
        tract.overture_buildings, tract.microsoft_buildings, name="building"
    )
    fire = coverage_deficit(tract.overture_fire, tract.hifld_fire, name="poi.fire")
    ems = coverage_deficit(tract.overture_ems, tract.hifld_ems, name="poi.ems")
    schools = coverage_deficit(
        tract.overture_schools, tract.hifld_schools, name="poi.schools"
    )
    hifld = _mean_defined((fire, ems, schools))
    cbp = coverage_deficit(
        tract.overture_places, tract.cbp_establishments, name="poi.cbp"
    )
    poi = _mean_defined((hifld, cbp))
    composite = _mean_defined((transport, building, poi))
    if composite is None:
        raise MappingEquityError(
            f"{tract.geoid}: all scored components are undefined; tract is not scorable"
        )
    return TractScore(
        geoid=tract.geoid,
        coverage_gap_score=composite,
        transport_gap=transport,
        building_gap=building,
        poi_gap=poi,
        poi_gap_hifld=hifld,
        poi_gap_fire=fire,
        poi_gap_ems=ems,
        poi_gap_schools=schools,
        poi_gap_cbp=cbp,
    )


def score_all(rows: Sequence[TractAggregate]) -> list[TractScore]:
    seen: set[str] = set()
    out: list[TractScore] = []
    for row in rows:
        if row.geoid in seen:
            raise MappingEquityError(f"duplicate aggregate GEOID: {row.geoid}")
        seen.add(row.geoid)
        out.append(score_tract(row))
    return sorted(out, key=lambda item: item.geoid)


def _authoritative_geoids(values: Iterable[str]) -> list[str]:
    out = [_geoid(v) for v in values]
    if len(set(out)) != len(out):
        raise MappingEquityError("authoritative tract universe contains duplicate GEOID")
    return out


def _fmt_score(value: float) -> str:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise MappingEquityError("coverage_gap_score must be finite and within [0, 1]")
    # 12 decimal places is deterministic and materially beyond leaderboard precision needs.
    return f"{value:.12f}"


def compile_submission(
    scores: Sequence[TractScore], authoritative_geoids: Sequence[str]
) -> tuple[str, str]:
    expected = _authoritative_geoids(authoritative_geoids)
    by_geoid: dict[str, TractScore] = {}
    for score in scores:
        geoid = _geoid(score.geoid)
        if geoid in by_geoid:
            raise MappingEquityError(f"duplicate score GEOID: {geoid}")
        by_geoid[geoid] = score

    expected_set = set(expected)
    actual_set = set(by_geoid)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    if missing or extra:
        raise MappingEquityError(f"tract universe mismatch: missing={missing} extra={extra}")

    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(("GEOID", "coverage_gap_score"))
    canonical_rows = []
    for geoid in expected:
        score = by_geoid[geoid]
        score_text = _fmt_score(score.coverage_gap_score)
        writer.writerow((geoid, score_text))
        canonical_rows.append(score.canonical())
    csv_text = buf.getvalue()
    csv_sha = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()

    payload = {
        "schema": SCHEMA,
        "overture_release": OVERTURE_RELEASE,
        "row_count": len(expected),
        "authoritative_geoids_sha256": hashlib.sha256(
            ("\n".join(expected) + "\n").encode("utf-8")
        ).hexdigest(),
        "submission_csv_sha256": csv_sha,
        "rows": canonical_rows,
        "source_data_policy": "aggregate-input-only-no-reference-score-column",
        "claims": {
            "real_challenge_data_executed": False,
            "submitted_to_zindi": False,
            "leaderboard_score_claimed": False,
            "award_claimed": False,
        },
    }
    receipt_body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    envelope = {
        "payload": payload,
        "payload_sha256": hashlib.sha256(receipt_body.encode("utf-8")).hexdigest(),
    }
    receipt_text = json.dumps(envelope, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    return csv_text, receipt_text


def verify_submission(
    csv_text: str, receipt_text: str, authoritative_geoids: Sequence[str]
) -> dict[str, object]:
    expected = _authoritative_geoids(authoritative_geoids)
    try:
        envelope = json.loads(receipt_text)
    except json.JSONDecodeError as exc:
        raise MappingEquityError("receipt is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "payload_sha256"}:
        raise MappingEquityError("receipt envelope shape mismatch")
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise MappingEquityError("receipt payload must be an object")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != envelope["payload_sha256"]:
        raise MappingEquityError("receipt payload digest mismatch")
    if payload.get("schema") != SCHEMA or payload.get("overture_release") != OVERTURE_RELEASE:
        raise MappingEquityError("receipt schema/release mismatch")
    if hashlib.sha256(csv_text.encode("utf-8")).hexdigest() != payload.get("submission_csv_sha256"):
        raise MappingEquityError("submission CSV digest mismatch")
    expected_digest = hashlib.sha256(("\n".join(expected) + "\n").encode("utf-8")).hexdigest()
    if payload.get("authoritative_geoids_sha256") != expected_digest:
        raise MappingEquityError("authoritative tract universe digest mismatch")

    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames != ["GEOID", "coverage_gap_score"]:
        raise MappingEquityError("submission must contain exactly GEOID,coverage_gap_score")
    rows = list(reader)
    if len(rows) != len(expected):
        raise MappingEquityError("submission row count mismatch")
    for idx, (row, geoid) in enumerate(zip(rows, expected), start=2):
        if row["GEOID"] != geoid:
            raise MappingEquityError(f"row {idx}: GEOID order/universe mismatch")
        if row["coverage_gap_score"] == "":
            raise MappingEquityError(f"row {idx}: blank score")
        try:
            value = float(row["coverage_gap_score"])
        except ValueError as exc:
            raise MappingEquityError(f"row {idx}: invalid score") from exc
        _fmt_score(value)
    if payload.get("row_count") != len(expected) or not isinstance(payload.get("rows"), list):
        raise MappingEquityError("receipt row metadata mismatch")
    if len(payload["rows"]) != len(expected):
        raise MappingEquityError("receipt score row count mismatch")
    if payload.get("source_data_policy") != "aggregate-input-only-no-reference-score-column":
        raise MappingEquityError("receipt source-data policy mismatch")
    for idx, (receipt_row, csv_row, geoid) in enumerate(zip(payload["rows"], rows, expected), start=2):
        if not isinstance(receipt_row, dict) or receipt_row.get("GEOID") != geoid:
            raise MappingEquityError(f"row {idx}: receipt GEOID mismatch")
        receipt_score = receipt_row.get("coverage_gap_score")
        if isinstance(receipt_score, bool) or not isinstance(receipt_score, (int, float)):
            raise MappingEquityError(f"row {idx}: receipt score type mismatch")
        if _fmt_score(float(receipt_score)) != csv_row["coverage_gap_score"]:
            raise MappingEquityError(f"row {idx}: receipt/CSV score mismatch")
    claims = payload.get("claims")
    expected_claims = {
        "real_challenge_data_executed": False,
        "submitted_to_zindi": False,
        "leaderboard_score_claimed": False,
        "award_claimed": False,
    }
    if claims != expected_claims:
        raise MappingEquityError("receipt authority claims mismatch")
    return {
        "schema": SCHEMA,
        "row_count": len(rows),
        "submission_csv_sha256": payload["submission_csv_sha256"],
        "verified": True,
    }


def read_aggregate_csv(path: os.PathLike[str] | str) -> list[TractAggregate]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(AGGREGATE_COLUMNS):
            raise MappingEquityError(
                "aggregate CSV columns must exactly match: " + ",".join(AGGREGATE_COLUMNS)
            )
        rows = []
        for line, row in enumerate(reader, start=2):
            parsed: dict[str, object] = {"GEOID": row["GEOID"]}
            for col in AGGREGATE_COLUMNS[1:]:
                raw = row[col]
                if raw is None or raw.strip() == "":
                    raise MappingEquityError(f"line {line}: {col} is blank")
                try:
                    parsed[col] = float(raw)
                except ValueError as exc:
                    raise MappingEquityError(f"line {line}: {col} is not numeric") from exc
            rows.append(TractAggregate.from_mapping(parsed))
    return rows


def read_authoritative_geoids(path: os.PathLike[str] | str) -> list[str]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "GEOID" not in reader.fieldnames:
            raise MappingEquityError("authoritative CSV must contain GEOID")
        return _authoritative_geoids([row["GEOID"] for row in reader])


def _write_new(path: Path, text: str) -> None:
    """Create one output exclusively and never pathname-delete on failure.

    A post-create failure may leave a partial file. That is intentional: once the
    pathname can be observed, cleanup by pathname could delete a concurrent actor's
    replacement. Callers get a hard failure and must choose a fresh output path.
    """
    if path.exists():
        raise MappingEquityError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def build_cli(aggregate_csv: str, authoritative_csv: str, output_csv: str, receipt_json: str) -> dict[str, object]:
    scores = score_all(read_aggregate_csv(aggregate_csv))
    geoids = read_authoritative_geoids(authoritative_csv)
    csv_text, receipt_text = compile_submission(scores, geoids)
    out_path = Path(output_csv)
    receipt_path = Path(receipt_json)
    if out_path.resolve() == receipt_path.resolve():
        raise MappingEquityError("submission and receipt outputs must be different files")
    _write_new(out_path, csv_text)
    _write_new(receipt_path, receipt_text)
    return verify_submission(csv_text, receipt_text, geoids)


def verify_cli(submission_csv: str, receipt_json: str, authoritative_csv: str) -> dict[str, object]:
    return verify_submission(
        Path(submission_csv).read_text(encoding="utf-8"),
        Path(receipt_json).read_text(encoding="utf-8"),
        read_authoritative_geoids(authoritative_csv),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="score tract aggregates and compile a deterministic submission")
    build.add_argument("--aggregates", required=True)
    build.add_argument("--authoritative", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--receipt", required=True)
    verify = sub.add_parser("verify", help="verify a compiled submission against its receipt/universe")
    verify.add_argument("--submission", required=True)
    verify.add_argument("--receipt", required=True)
    verify.add_argument("--authoritative", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_cli(args.aggregates, args.authoritative, args.output, args.receipt)
        else:
            result = verify_cli(args.submission, args.receipt, args.authoritative)
    except (MappingEquityError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
