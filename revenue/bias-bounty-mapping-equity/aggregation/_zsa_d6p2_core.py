#!/usr/bin/env python3
"""Leak-safe public-data aggregation runner for Mapping Equity.

The module has a stdlib-only plan/test surface. DuckDB is imported lazily only by
`run`, so CI can validate the registry, SQL contract and output guards without
network access or downloading the multi-GB challenge corpus.
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
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

SCHEMA = "mapping-equity-public-aggregation/v1"
DUCKDB_VERSION = "1.5.4"
OVERTURE_RELEASE = "2026-08-19.0"
HTTPS_ROOT = "https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"
REGIONS = {
    "eastern-ok": 1192,
    "maricopa-az": 1593,
    "northern-ca": 591,
    "south-central-tx": 6003,
}
OUTPUT_COLUMNS = (
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
ROAD_CLASSES = ("motorway", "trunk", "primary", "secondary")
TIGER_MTFCC = ("S1100", "S1200")
SCHOOL_CATEGORIES = (
    "elementary_school",
    "middle_school",
    "high_school",
    "school",
    "private_school",
    "public_school",
)
GEOID_RE = re.compile(r"^[0-9]{11}$")
FORBIDDEN_SOURCE_TOKENS = (
    "coverage-gap",
    "coverage_gap",
    "reference-score",
    "reference_score",
    "answer-key",
    "answer_key",
)


class AggregationError(ValueError):
    pass


def _region(region: str) -> str:
    if region not in REGIONS:
        raise AggregationError(f"unsupported region: {region!r}")
    return region


def _safe_source(uri: str, *, allow_sample_score_header: bool = False) -> str:
    low = uri.lower()
    for token in FORBIDDEN_SOURCE_TOKENS:
        if token in low:
            raise AggregationError(f"forbidden answer/reference source token {token!r}: {uri}")
    if not uri.startswith(HTTPS_ROOT + "/"):
        raise AggregationError(f"source must stay inside the public challenge product: {uri}")
    return uri


def _ref(region: str, suffix: str, ext: str = "parquet") -> str:
    region = _region(region)
    return _safe_source(f"{HTTPS_ROOT}/reference/{region}/{region}-{suffix}.{ext}")


def _strata(region: str, suffix: str) -> str:
    region = _region(region)
    return _safe_source(f"{HTTPS_ROOT}/strata/{region}/{region}-{suffix}.parquet")


def source_registry(region: str) -> dict[str, str]:
    """Return only source objects permitted to affect scored aggregates."""
    region = _region(region)
    registry = {
        "sample": _ref(region, "sample-submission", "csv"),
        "tracts": _strata(region, "census-tracts"),
        "overture_roads": _ref(region, "overture-roads"),
        "tiger_roads": _ref(region, "census-tiger-roads"),
        "overture_buildings": _ref(region, "overture-buildings"),
        "microsoft_buildings": _ref(region, "microsoft-buildings"),
        "overture_pois": _ref(region, "overture-pois"),
        "hifld_fire": _ref(region, "hifld-fire-stations"),
        "hifld_ems": _ref(region, "hifld-ems-stations"),
        "hifld_schools": _ref(region, "hifld-schools"),
        "cbp": _ref(region, "census-cbp"),
    }
    for uri in registry.values():
        _safe_source(uri)
    return registry


REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "sample": ("GEOID",),
    "tracts": ("GEOID", "geometry", "bbox"),
    "overture_roads": ("geometry", "bbox", "class"),
    "tiger_roads": ("geometry", "bbox", "MTFCC"),
    "overture_buildings": ("geometry", "bbox"),
    "microsoft_buildings": ("geometry", "bbox"),
    "overture_pois": ("geometry", "bbox", "categories"),
    "hifld_fire": ("geometry", "bbox"),
    "hifld_ems": ("geometry", "bbox"),
    "hifld_schools": ("geometry", "bbox"),
    "cbp": ("GEOID", "cbp_estab"),
}


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _bbox_overlap(feature_alias: str, tract_alias: str = "t") -> str:
    # GeoParquet 1.1 bbox order is xmin,ymin,xmax,ymax. All four comparisons
    # are intentional; two comparisons silently drop edge-straddling features.
    return (
        f"{feature_alias}.bbox.xmax >= {tract_alias}.bbox.xmin AND "
        f"{feature_alias}.bbox.xmin <= {tract_alias}.bbox.xmax AND "
        f"{feature_alias}.bbox.ymax >= {tract_alias}.bbox.ymin AND "
        f"{feature_alias}.bbox.ymin <= {tract_alias}.bbox.ymax"
    )


def aggregate_query(region: str) -> str:
    """Build the deterministic DuckDB SQL that emits the scorer's 13 columns."""
    r = source_registry(region)
    q = {k: _sql_string(v) for k, v in r.items()}
    road_classes = ", ".join(_sql_string(v) for v in ROAD_CLASSES)
    tiger_codes = ", ".join(_sql_string(v) for v in TIGER_MTFCC)
    school_categories = ", ".join(_sql_string(v) for v in SCHOOL_CATEGORIES)
    return f"""
WITH
  authoritative AS (
    SELECT CAST(GEOID AS VARCHAR) AS GEOID
    FROM read_csv_auto({q['sample']}, header=true, all_varchar=true)
  ),
  tracts AS (
    SELECT t.GEOID, t.geometry, t.bbox,
           ST_Transform(t.geometry, 'EPSG:4326', 'EPSG:5070', always_xy := true) AS geometry_5070
    FROM read_parquet({q['tracts']}) AS t
    INNER JOIN authoritative AS a USING (GEOID)
  ),
  overture_road AS (
    SELECT t.GEOID,
           SUM(ST_Length(ST_Intersection(
               ST_Transform(r.geometry, 'EPSG:4326', 'EPSG:5070', always_xy := true),
               t.geometry_5070))) AS overture_road_length
    FROM tracts AS t
    JOIN read_parquet({q['overture_roads']}) AS r
      ON {_bbox_overlap('r')}
     AND ST_Intersects(r.geometry, t.geometry)
    WHERE r."class" IN ({road_classes})
    GROUP BY t.GEOID
  ),
  tiger_road AS (
    SELECT t.GEOID,
           SUM(ST_Length(ST_Intersection(
               ST_Transform(r.geometry, 'EPSG:4326', 'EPSG:5070', always_xy := true),
               t.geometry_5070))) AS tiger_road_length
    FROM tracts AS t
    JOIN read_parquet({q['tiger_roads']}) AS r
      ON {_bbox_overlap('r')}
     AND ST_Intersects(r.geometry, t.geometry)
    WHERE r.MTFCC IN ({tiger_codes})
    GROUP BY t.GEOID
  ),
  overture_building AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS overture_buildings
    FROM tracts AS t
    JOIN read_parquet({q['overture_buildings']}) AS b
      ON {_bbox_overlap('b')}
     AND ST_Contains(t.geometry, ST_PointOnSurface(b.geometry))
    GROUP BY t.GEOID
  ),
  microsoft_building AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS microsoft_buildings
    FROM tracts AS t
    JOIN read_parquet({q['microsoft_buildings']}) AS b
      ON {_bbox_overlap('b')}
     AND ST_Contains(t.geometry, ST_PointOnSurface(b.geometry))
    GROUP BY t.GEOID
  ),
  overture_poi AS (
    SELECT t.GEOID,
           COUNT(*)::DOUBLE AS overture_places,
           COUNT(*) FILTER (WHERE p.categories.primary = 'fire_department')::DOUBLE AS overture_fire,
           COUNT(*) FILTER (WHERE p.categories.primary = 'ambulance_and_ems_services')::DOUBLE AS overture_ems,
           COUNT(*) FILTER (WHERE p.categories.primary IN ({school_categories}))::DOUBLE AS overture_schools
    FROM tracts AS t
    JOIN read_parquet({q['overture_pois']}) AS p
      ON {_bbox_overlap('p')}
     AND ST_Contains(t.geometry, p.geometry)
    GROUP BY t.GEOID
  ),
  hifld_fire AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS hifld_fire
    FROM tracts AS t JOIN read_parquet({q['hifld_fire']}) AS p
      ON {_bbox_overlap('p')} AND ST_Contains(t.geometry, p.geometry)
    GROUP BY t.GEOID
  ),
  hifld_ems AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS hifld_ems
    FROM tracts AS t JOIN read_parquet({q['hifld_ems']}) AS p
      ON {_bbox_overlap('p')} AND ST_Contains(t.geometry, p.geometry)
    GROUP BY t.GEOID
  ),
  hifld_schools AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS hifld_schools
    FROM tracts AS t JOIN read_parquet({q['hifld_schools']}) AS p
      ON {_bbox_overlap('p')} AND ST_Contains(t.geometry, p.geometry)
    GROUP BY t.GEOID
  ),
  cbp AS (
    SELECT c.GEOID, MAX(CAST(c.cbp_estab AS DOUBLE)) AS cbp_establishments
    FROM read_parquet({q['cbp']}) AS c
    INNER JOIN authoritative AS a USING (GEOID)
    GROUP BY c.GEOID
  )
SELECT a.GEOID,
       COALESCE(oroad.overture_road_length, 0.0) AS overture_road_length,
       COALESCE(troad.tiger_road_length, 0.0) AS tiger_road_length,
       COALESCE(ob.overture_buildings, 0.0) AS overture_buildings,
       COALESCE(mb.microsoft_buildings, 0.0) AS microsoft_buildings,
       COALESCE(op.overture_fire, 0.0) AS overture_fire,
       COALESCE(hf.hifld_fire, 0.0) AS hifld_fire,
       COALESCE(op.overture_ems, 0.0) AS overture_ems,
       COALESCE(he.hifld_ems, 0.0) AS hifld_ems,
       COALESCE(op.overture_schools, 0.0) AS overture_schools,
       COALESCE(hs.hifld_schools, 0.0) AS hifld_schools,
       COALESCE(op.overture_places, 0.0) AS overture_places,
       COALESCE(c.cbp_establishments, 0.0) AS cbp_establishments
FROM authoritative AS a
LEFT JOIN overture_road AS oroad USING (GEOID)
LEFT JOIN tiger_road AS troad USING (GEOID)
LEFT JOIN overture_building AS ob USING (GEOID)
LEFT JOIN microsoft_building AS mb USING (GEOID)
LEFT JOIN overture_poi AS op USING (GEOID)
LEFT JOIN hifld_fire AS hf USING (GEOID)
LEFT JOIN hifld_ems AS he USING (GEOID)
LEFT JOIN hifld_schools AS hs USING (GEOID)
LEFT JOIN cbp AS c USING (GEOID)
ORDER BY a.GEOID
""".strip()


def build_plan(region: str) -> dict[str, object]:
    region = _region(region)
    sources = source_registry(region)
    query = aggregate_query(region)
    return {
        "schema": SCHEMA,
        "region": region,
        "expected_scored_rows": REGIONS[region],
        "duckdb_version": DUCKDB_VERSION,
        "overture_release": OVERTURE_RELEASE,
        "sources": sources,
        "required_columns": {k: list(REQUIRED_COLUMNS[k]) for k in sources},
        "source_policy": {
            "answer_artifact_paths_forbidden": True,
            "sample_submission_projection": ["GEOID"],
            "sample_score_column_never_selected": True,
        },
        "geometry_policy": {
            "source_crs": "OGC:CRS84",
            "metric_crs": "EPSG:5070",
            "transform_always_xy": True,
            "road_allocation": "clip-to-tract-then-length",
            "building_allocation": "point-on-surface-within-tract",
            "point_allocation": "strictly-within-tract",
        },
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "output_columns": list(OUTPUT_COLUMNS),
    }


def schema_probe_sql(key: str, uri: str) -> str:
    _safe_source(uri)
    if key == "sample":
        return f"DESCRIBE SELECT * FROM read_csv_auto({_sql_string(uri)}, header=true, all_varchar=true)"
    return f"DESCRIBE SELECT * FROM read_parquet({_sql_string(uri)})"


def semantic_probe_sql(region: str) -> tuple[str, ...]:
    r = source_registry(region)
    return (
        # The POI category is a nested Overture struct; selecting it at LIMIT 0
        # proves the current object still exposes the expected field.
        f"SELECT categories.primary FROM read_parquet({_sql_string(r['overture_pois'])}) LIMIT 0",
        # A deterministic synthetic road checks the exact axis-order transform used
        # by the aggregate query. A poisoned transform returns inf/non-finite.
        "SELECT ST_Length(ST_Transform(ST_GeomFromText('LINESTRING(-112 33,-111.99 33)'), "
        "'EPSG:4326', 'EPSG:5070', always_xy := true)) AS smoke_meters",
    )


def validate_source_schema(key: str, columns: Iterable[str]) -> None:
    actual = set(columns)
    needed = set(REQUIRED_COLUMNS[key])
    missing = sorted(needed - actual)
    if missing:
        raise AggregationError(f"{key}: current source schema missing required columns {missing}")
    low_columns = {c.lower() for c in actual}
    if key != "sample":
        for token in FORBIDDEN_SOURCE_TOKENS:
            normalized = token.replace("-", "_")
            if any(normalized in col for col in low_columns):
                raise AggregationError(f"{key}: forbidden answer/reference-like column present: {token}")


def validate_rows(region: str, fieldnames: Sequence[str], rows: Sequence[Sequence[object]]) -> list[tuple[object, ...]]:
    region = _region(region)
    if tuple(fieldnames) != OUTPUT_COLUMNS:
        raise AggregationError(f"aggregate output columns mismatch: {fieldnames!r}")
    expected = REGIONS[region]
    if len(rows) != expected:
        raise AggregationError(f"{region}: expected {expected} scored tracts, got {len(rows)}")
    seen: set[str] = set()
    cleaned: list[tuple[object, ...]] = []
    for index, row in enumerate(rows, start=1):
        if len(row) != len(OUTPUT_COLUMNS):
            raise AggregationError(f"row {index}: expected {len(OUTPUT_COLUMNS)} values")
        geoid = row[0]
        if not isinstance(geoid, str) or not GEOID_RE.fullmatch(geoid):
            raise AggregationError(f"row {index}: GEOID must remain 11-digit text")
        if geoid in seen:
            raise AggregationError(f"duplicate GEOID: {geoid}")
        seen.add(geoid)
        values: list[object] = [geoid]
        for name, raw in zip(OUTPUT_COLUMNS[1:], row[1:]):
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise AggregationError(f"{geoid}: {name} must be numeric")
            value = float(raw)
            if not math.isfinite(value) or value < 0:
                raise AggregationError(f"{geoid}: {name} must be finite and nonnegative")
            values.append(value)
        cleaned.append(tuple(values))
    if cleaned != sorted(cleaned, key=lambda row: row[0]):
        raise AggregationError("aggregate rows must be ordered by GEOID")
    return cleaned


def render_csv(rows: Sequence[Sequence[object]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(OUTPUT_COLUMNS)
    for row in rows:
        writer.writerow([row[0], *[f"{float(v):.12f}" for v in row[1:]]])
    return buf.getvalue()


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise AggregationError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _digest_schema(columns: Sequence[tuple[object, ...]]) -> str:
    body = json.dumps([list(row) for row in columns], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _connect_duckdb():
    try:
        import duckdb  # type: ignore
    except ImportError as exc:
        raise AggregationError(
            f"run requires duckdb=={DUCKDB_VERSION}; plan/tests are stdlib-only"
        ) from exc
    if duckdb.__version__ != DUCKDB_VERSION:
        raise AggregationError(
            f"duckdb version drift: require {DUCKDB_VERSION}, found {duckdb.__version__}"
        )
    con = duckdb.connect()
    # Ordinary connected environments can install the public core extensions if
    # missing. This cloud turn cannot resolve outbound DNS, so no real-data claim
    # is made from it.
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("SET s3_region='us-west-2'; SET s3_url_style='path';")
    return con


def execute_region(region: str, output: Path, receipt: Path) -> dict[str, object]:
    region = _region(region)
    if output.resolve() == receipt.resolve():
        raise AggregationError("output and receipt must be different paths")
    if output.exists() or receipt.exists():
        raise AggregationError("run outputs are create-exclusive; choose fresh paths")
    con = _connect_duckdb()
    registry = source_registry(region)
    schema_receipts: dict[str, dict[str, object]] = {}
    try:
        for key, uri in registry.items():
            description = con.execute(schema_probe_sql(key, uri)).fetchall()
            columns = [str(row[0]) for row in description]
            validate_source_schema(key, columns)
            schema_receipts[key] = {
                "uri": uri,
                "columns": columns,
                "describe_sha256": _digest_schema(description),
            }
        con.execute(semantic_probe_sql(region)[0])
        smoke = float(con.execute(semantic_probe_sql(region)[1]).fetchone()[0])
        if not math.isfinite(smoke) or not 500.0 < smoke < 2000.0:
            raise AggregationError(f"EPSG axis-order smoke test failed: {smoke!r} metres")

        cursor = con.execute(aggregate_query(region))
        fieldnames = [str(desc[0]) for desc in cursor.description]
        rows = cursor.fetchall()
        cleaned = validate_rows(region, fieldnames, rows)
        csv_text = render_csv(cleaned)
        csv_sha = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
        plan = build_plan(region)
        payload = {
            "schema": SCHEMA,
            "region": region,
            "duckdb_version": DUCKDB_VERSION,
            "overture_release": OVERTURE_RELEASE,
            "real_public_data_executed": True,
            "row_count": len(cleaned),
            "output_csv_sha256": csv_sha,
            "axis_order_smoke_meters": smoke,
            "plan": plan,
            "source_schemas": schema_receipts,
            "claims": {
                "zindi_registered": False,
                "submitted_to_zindi": False,
                "leaderboard_score_claimed": False,
                "award_claimed": False,
                "payment_claimed": False,
            },
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        envelope = {
            "payload": payload,
            "payload_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        }
        receipt_text = json.dumps(envelope, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
        _write_new(output, csv_text)
        _write_new(receipt, receipt_text)
        return {"region": region, "rows": len(cleaned), "output_csv_sha256": csv_sha}
    finally:
        con.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="emit the deterministic no-download execution plan")
    plan.add_argument("--region", required=True, choices=tuple(REGIONS))
    plan.add_argument("--sql", action="store_true", help="include the generated aggregate SQL")
    run = sub.add_parser("run", help="execute one public region with DuckDB 1.5.4")
    run.add_argument("--region", required=True, choices=tuple(REGIONS))
    run.add_argument("--output", required=True)
    run.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            payload = build_plan(args.region)
            if args.sql:
                payload["sql"] = aggregate_query(args.region)
            print(json.dumps(payload, sort_keys=True, indent=2))
        else:
            result = execute_region(args.region, Path(args.output), Path(args.receipt))
            print(json.dumps(result, sort_keys=True))
    except (AggregationError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
