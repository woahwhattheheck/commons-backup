#!/usr/bin/env python3
"""Pure scoring core for the Zindi Bias Bounty Mapping Equity Challenge.

This module intentionally accepts tract-level aggregates instead of raw geospatial
features. Keeping the scoring contract independent from spatial tooling makes the
variable-divisor and undefined-reference rules easy to test without DuckDB/GDAL.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Iterable, Mapping, Optional

SCHOOL_CATEGORIES = frozenset({
    "elementary_school", "middle_school", "high_school", "school",
    "private_school", "public_school",
})
OVERTURE_ROAD_CLASSES = frozenset({"motorway", "trunk", "primary", "secondary"})
TIGER_MTFCC = frozenset({"S1100", "S1200"})

AGGREGATE_COLUMNS = (
    "GEOID", "overture_road_m", "tiger_road_m", "overture_buildings",
    "microsoft_buildings", "overture_pois", "cbp_establishments",
    "overture_fire", "hifld_fire", "overture_ems", "hifld_ems",
    "overture_schools", "hifld_schools",
)

class ScoreInputError(ValueError):
    """Raised when aggregate inputs cannot represent a valid challenge tract."""

def _finite_nonnegative(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ScoreInputError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise ScoreInputError(f"{field} must be finite and non-negative")
    return number

def _geoid(value: object) -> str:
    if not isinstance(value, str):
        raise ScoreInputError("GEOID must be text so leading zeroes cannot be lost")
    geoid = value.strip()
    if not geoid or not geoid.isdigit():
        raise ScoreInputError("GEOID must contain decimal digits")
    if len(geoid) != 11:
        raise ScoreInputError("GEOID must be the 11-digit tract identifier")
    return geoid

def ratio_gap(observed: float, reference: float) -> Optional[float]:
    """Return 1-min(1, observed/reference); None means no reference exists."""
    observed = _finite_nonnegative(observed, "observed")
    reference = _finite_nonnegative(reference, "reference")
    if reference == 0:
        return None
    return 1.0 - min(1.0, observed / reference)

def mean_defined(values: Iterable[Optional[float]]) -> Optional[float]:
    defined = [value for value in values if value is not None]
    if not defined:
        return None
    return fmean(defined)

@dataclass(frozen=True)
class ScoreResult:
    GEOID: str
    coverage_gap_score: float
    transport_gap: Optional[float]
    building_gap: Optional[float]
    poi_gap: Optional[float]
    poi_gap_hifld: Optional[float]
    poi_gap_cbp: Optional[float]
    poi_gap_fire: Optional[float]
    poi_gap_ems: Optional[float]
    poi_gap_schools: Optional[float]

    @property
    def transport_defined(self) -> bool: return self.transport_gap is not None
    @property
    def building_defined(self) -> bool: return self.building_gap is not None
    @property
    def poi_defined(self) -> bool: return self.poi_gap is not None

    def submission_row(self) -> dict[str, object]:
        return {"GEOID": self.GEOID, "coverage_gap_score": self.coverage_gap_score}

    def diagnostic_row(self) -> dict[str, object]:
        def cell(value: Optional[float]) -> object:
            return "" if value is None else value
        return {
            "GEOID": self.GEOID,
            "coverage_gap_score": self.coverage_gap_score,
            "transport_gap": cell(self.transport_gap),
            "transport_defined": self.transport_defined,
            "building_gap": cell(self.building_gap),
            "building_defined": self.building_defined,
            "poi_gap": cell(self.poi_gap),
            "poi_defined": self.poi_defined,
            "poi_gap_hifld": cell(self.poi_gap_hifld),
            "poi_gap_cbp": cell(self.poi_gap_cbp),
            "poi_gap_fire": cell(self.poi_gap_fire),
            "poi_gap_ems": cell(self.poi_gap_ems),
            "poi_gap_schools": cell(self.poi_gap_schools),
        }

def score_aggregate(row: Mapping[str, object]) -> ScoreResult:
    missing = [column for column in AGGREGATE_COLUMNS if column not in row]
    if missing:
        raise ScoreInputError(f"missing aggregate columns: {', '.join(missing)}")
    geoid = _geoid(row["GEOID"])
    n = {column: _finite_nonnegative(row[column], column) for column in AGGREGATE_COLUMNS[1:]}
    transport_gap = ratio_gap(n["overture_road_m"], n["tiger_road_m"])
    building_gap = ratio_gap(n["overture_buildings"], n["microsoft_buildings"])
    poi_gap_fire = ratio_gap(n["overture_fire"], n["hifld_fire"])
    poi_gap_ems = ratio_gap(n["overture_ems"], n["hifld_ems"])
    poi_gap_schools = ratio_gap(n["overture_schools"], n["hifld_schools"])
    poi_gap_hifld = mean_defined((poi_gap_fire, poi_gap_ems, poi_gap_schools))
    poi_gap_cbp = ratio_gap(n["overture_pois"], n["cbp_establishments"])
    poi_gap = mean_defined((poi_gap_hifld, poi_gap_cbp))
    composite = mean_defined((transport_gap, building_gap, poi_gap))
    if composite is None:
        raise ScoreInputError(f"{geoid}: all three challenge components are undefined")
    return ScoreResult(
        GEOID=geoid, coverage_gap_score=composite,
        transport_gap=transport_gap, building_gap=building_gap, poi_gap=poi_gap,
        poi_gap_hifld=poi_gap_hifld, poi_gap_cbp=poi_gap_cbp,
        poi_gap_fire=poi_gap_fire, poi_gap_ems=poi_gap_ems,
        poi_gap_schools=poi_gap_schools,
    )

def read_aggregates(path: Path) -> list[ScoreResult]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ScoreInputError("aggregate CSV has no header")
        missing = [column for column in AGGREGATE_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ScoreInputError(f"aggregate CSV missing: {', '.join(missing)}")
        results = [score_aggregate(row) for row in reader]
    geoids = [row.GEOID for row in results]
    if len(set(geoids)) != len(geoids):
        raise ScoreInputError("aggregate CSV contains duplicate GEOIDs")
    if not results:
        raise ScoreInputError("aggregate CSV is empty")
    return results

def _write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)

def write_submission(results: list[ScoreResult], path: Path) -> None:
    rows = [item.submission_row() for item in sorted(results, key=lambda item: item.GEOID)]
    _write_csv(path, rows, ["GEOID", "coverage_gap_score"])

def write_diagnostics(results: list[ScoreResult], path: Path) -> None:
    rows = [item.diagnostic_row() for item in sorted(results, key=lambda item: item.GEOID)]
    _write_csv(path, rows, list(rows[0]))

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aggregates", type=Path)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--diagnostics", type=Path)
    args = parser.parse_args(argv)
    results = read_aggregates(args.aggregates)
    write_submission(results, args.submission)
    if args.diagnostics: write_diagnostics(results, args.diagnostics)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
