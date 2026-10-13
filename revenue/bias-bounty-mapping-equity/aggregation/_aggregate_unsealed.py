#!/usr/bin/env python3
"""Leak-safe Mapping Equity aggregation with immutable source-generation custody.

Primary implementation/source credit: ZSA-D6P2. The original donor remains preserved
byte-exact in `_zsa_d6p2_core.py`. ZFS-R7 supplied independent alternate-carrier review
evidence. ZHD-K8P3 recovered/finalized M1 and owns this post-merge fix-forward.

The authority path in this module intentionally does not delegate scored SQL or policy
to the donor module. Public remote objects are downloaded exactly once, SHA-256 bound,
kept open as retained file generations, and every preflight + scored read consumes the
same `/proc/self/fd/<n>` generation. This closes same-URI A->B TOCTOU while retaining
the donor for provenance and compatibility review.
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
import tempfile
import urllib.request
from pathlib import Path
from typing import BinaryIO, Iterable, Mapping, Optional, Sequence
from urllib.parse import unquote, urlsplit

import _zsa_d6p2_core as _core  # provenance/compatibility only; never scoring authority

SCHEMA = "mapping-equity-public-aggregation/v2"
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
    "reference-answer",
    "reference_answer",
    "answer-key",
    "answer_key",
)
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
GEOMETRY_EXPECTATIONS: dict[str, frozenset[str]] = {
    "tracts": frozenset({"POLYGON", "MULTIPOLYGON"}),
    "overture_roads": frozenset({"LINESTRING", "MULTILINESTRING"}),
    "tiger_roads": frozenset({"LINESTRING", "MULTILINESTRING"}),
    "overture_buildings": frozenset({"POLYGON", "MULTIPOLYGON"}),
    "microsoft_buildings": frozenset({"POLYGON", "MULTIPOLYGON"}),
    "overture_pois": frozenset({"POINT", "MULTIPOINT"}),
    "hifld_fire": frozenset({"POINT", "MULTIPOINT"}),
    "hifld_ems": frozenset({"POINT", "MULTIPOINT"}),
    "hifld_schools": frozenset({"POINT", "MULTIPOINT"}),
}
PUBLISHED_POLICY_VALUES: dict[str, tuple[str, ...]] = {
    "overture_roads.class": ROAD_CLASSES,
    "tiger_roads.MTFCC": TIGER_MTFCC,
    "overture_pois.school": SCHOOL_CATEGORIES,
    "overture_pois.fire": ("fire_department",),
    "overture_pois.ems": ("ambulance_and_ems_services",),
}

_URL_OPEN = urllib.request.urlopen


class AggregationError(ValueError):
    pass


def _region_counts() -> dict[str, int]:
    return {
        "eastern-ok": 1192,
        "maricopa-az": 1593,
        "northern-ca": 591,
        "south-central-tx": 6003,
    }


def _output_columns() -> tuple[str, ...]:
    return (
        "GEOID", "overture_road_length", "tiger_road_length",
        "overture_buildings", "microsoft_buildings", "overture_fire",
        "hifld_fire", "overture_ems", "hifld_ems", "overture_schools",
        "hifld_schools", "overture_places", "cbp_establishments",
    )


def _required_columns() -> dict[str, tuple[str, ...]]:
    return {
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


def _geometry_expectations() -> dict[str, frozenset[str]]:
    return {
        "tracts": frozenset({"POLYGON", "MULTIPOLYGON"}),
        "overture_roads": frozenset({"LINESTRING", "MULTILINESTRING"}),
        "tiger_roads": frozenset({"LINESTRING", "MULTILINESTRING"}),
        "overture_buildings": frozenset({"POLYGON", "MULTIPOLYGON"}),
        "microsoft_buildings": frozenset({"POLYGON", "MULTIPOLYGON"}),
        "overture_pois": frozenset({"POINT", "MULTIPOINT"}),
        "hifld_fire": frozenset({"POINT", "MULTIPOINT"}),
        "hifld_ems": frozenset({"POINT", "MULTIPOINT"}),
        "hifld_schools": frozenset({"POINT", "MULTIPOINT"}),
    }


def _policy_values() -> dict[str, tuple[str, ...]]:
    return {
        "overture_roads.class": ("motorway", "trunk", "primary", "secondary"),
        "tiger_roads.MTFCC": ("S1100", "S1200"),
        "overture_pois.school": (
            "elementary_school", "middle_school", "high_school",
            "school", "private_school", "public_school",
        ),
        "overture_pois.fire": ("fire_department",),
        "overture_pois.ems": ("ambulance_and_ems_services",),
    }


def _region(region: str) -> str:
    if region not in _region_counts():
        raise AggregationError(f"unsupported region: {region!r}")
    return region


def _decode_bounded(value: str) -> str:
    current = value
    for _ in range(8):
        decoded = unquote(current)
        if decoded == current:
            return decoded
        current = decoded
    if unquote(current) != current:
        raise AggregationError("source encoding depth exceeds leak-fence limit")
    return current


def _normalized_label(value: str) -> str:
    decoded = _decode_bounded(value).lower().replace("\\", "/")
    return re.sub(r"[-.\s]+", "_", decoded)


def _forbidden_token(value: str) -> Optional[str]:
    normalized = _normalized_label(value)
    for token in (
        "coverage-gap", "coverage_gap", "reference-score", "reference_score",
        "reference-answer", "reference_answer", "answer-key", "answer_key",
    ):
        candidate = re.sub(r"[-.\s]+", "_", token.lower())
        if candidate in normalized:
            return token
    return None


def _safe_source(uri: str, *, allow_sample_score_header: bool = False) -> str:
    del allow_sample_score_header
    decoded = _decode_bounded(uri)
    token = _forbidden_token(decoded)
    if token is not None:
        raise AggregationError(f"forbidden answer/reference source token {token!r}: {uri}")
    root = "https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"
    if not decoded.startswith(root + "/"):
        raise AggregationError(f"source must stay inside the public challenge product: {uri}")
    parts = urlsplit(decoded)
    if parts.scheme != "https" or parts.username or parts.password:
        raise AggregationError(f"source URI must use credential-free HTTPS: {uri}")
    if any(ch in decoded for ch in ("?", "#", "\\")):
        raise AggregationError(f"source URI must be canonical and query/fragment free: {uri}")
    return uri


def source_registry(region: str) -> dict[str, str]:
    if region not in ("eastern-ok", "maricopa-az", "northern-ca", "south-central-tx"):
        raise AggregationError(f"unsupported region: {region!r}")
    root = "https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"
    ref = f"{root}/reference/{region}/{region}-"
    return {
        "sample": ref + "sample-submission.csv",
        "tracts": f"{root}/strata/{region}/{region}-census-tracts.parquet",
        "overture_roads": ref + "overture-roads.parquet",
        "tiger_roads": ref + "census-tiger-roads.parquet",
        "overture_buildings": ref + "overture-buildings.parquet",
        "microsoft_buildings": ref + "microsoft-buildings.parquet",
        "overture_pois": ref + "overture-pois.parquet",
        "hifld_fire": ref + "hifld-fire-stations.parquet",
        "hifld_ems": ref + "hifld-ems-stations.parquet",
        "hifld_schools": ref + "hifld-schools.parquet",
        "cbp": ref + "census-cbp.parquet",
    }


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _bbox_overlap(feature_alias: str, tract_alias: str = "t") -> str:
    return (
        f"{feature_alias}.bbox.xmax >= {tract_alias}.bbox.xmin AND "
        f"{feature_alias}.bbox.xmin <= {tract_alias}.bbox.xmax AND "
        f"{feature_alias}.bbox.ymax >= {tract_alias}.bbox.ymin AND "
        f"{feature_alias}.bbox.ymin <= {tract_alias}.bbox.ymax"
    )


def _aggregate_query_for_registry(region: str, registry: Mapping[str, str]) -> str:
    if region not in ("eastern-ok", "maricopa-az", "northern-ca", "south-central-tx"):
        raise AggregationError(f"unsupported region: {region!r}")
    expected_keys = (
        "sample", "tracts", "overture_roads", "tiger_roads",
        "overture_buildings", "microsoft_buildings", "overture_pois",
        "hifld_fire", "hifld_ems", "hifld_schools", "cbp",
    )
    if tuple(registry) != expected_keys:
        raise AggregationError("bound source registry keys/order mismatch")

    def quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def bbox(feature_alias: str, tract_alias: str = "t") -> str:
        return (
            f"{feature_alias}.bbox.xmax >= {tract_alias}.bbox.xmin AND "
            f"{feature_alias}.bbox.xmin <= {tract_alias}.bbox.xmax AND "
            f"{feature_alias}.bbox.ymax >= {tract_alias}.bbox.ymin AND "
            f"{feature_alias}.bbox.ymin <= {tract_alias}.bbox.ymax"
        )

    q = {key: quote(str(registry[key])) for key in expected_keys}
    road_classes = ("motorway", "trunk", "primary", "secondary")
    tiger_codes = ("S1100", "S1200")
    school_categories = (
        "elementary_school", "middle_school", "high_school",
        "school", "private_school", "public_school",
    )
    road_sql = ", ".join(quote(v) for v in road_classes)
    tiger_sql = ", ".join(quote(v) for v in tiger_codes)
    school_sql = ", ".join(quote(v) for v in school_categories)
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
      ON {bbox('r')}
     AND ST_Intersects(r.geometry, t.geometry)
    WHERE r."class" IN ({road_sql})
    GROUP BY t.GEOID
  ),
  tiger_road AS (
    SELECT t.GEOID,
           SUM(ST_Length(ST_Intersection(
               ST_Transform(r.geometry, 'EPSG:4326', 'EPSG:5070', always_xy := true),
               t.geometry_5070))) AS tiger_road_length
    FROM tracts AS t
    JOIN read_parquet({q['tiger_roads']}) AS r
      ON {bbox('r')}
     AND ST_Intersects(r.geometry, t.geometry)
    WHERE r.MTFCC IN ({tiger_sql})
    GROUP BY t.GEOID
  ),
  overture_building AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS overture_buildings
    FROM tracts AS t
    JOIN read_parquet({q['overture_buildings']}) AS b
      ON {bbox('b')}
     AND ST_Contains(t.geometry, ST_PointOnSurface(b.geometry))
    GROUP BY t.GEOID
  ),
  microsoft_building AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS microsoft_buildings
    FROM tracts AS t
    JOIN read_parquet({q['microsoft_buildings']}) AS b
      ON {bbox('b')}
     AND ST_Contains(t.geometry, ST_PointOnSurface(b.geometry))
    GROUP BY t.GEOID
  ),
  overture_poi AS (
    SELECT t.GEOID,
           COUNT(*)::DOUBLE AS overture_places,
           COUNT(*) FILTER (WHERE p.categories.primary = 'fire_department')::DOUBLE AS overture_fire,
           COUNT(*) FILTER (WHERE p.categories.primary = 'ambulance_and_ems_services')::DOUBLE AS overture_ems,
           COUNT(*) FILTER (WHERE p.categories.primary IN ({school_sql}))::DOUBLE AS overture_schools
    FROM tracts AS t
    JOIN read_parquet({q['overture_pois']}) AS p
      ON {bbox('p')}
     AND ST_Contains(t.geometry, p.geometry)
    GROUP BY t.GEOID
  ),
  hifld_fire AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS hifld_fire
    FROM tracts AS t JOIN read_parquet({q['hifld_fire']}) AS p
      ON {bbox('p')} AND ST_Contains(t.geometry, p.geometry)
    GROUP BY t.GEOID
  ),
  hifld_ems AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS hifld_ems
    FROM tracts AS t JOIN read_parquet({q['hifld_ems']}) AS p
      ON {bbox('p')} AND ST_Contains(t.geometry, p.geometry)
    GROUP BY t.GEOID
  ),
  hifld_schools AS (
    SELECT t.GEOID, COUNT(*)::DOUBLE AS hifld_schools
    FROM tracts AS t JOIN read_parquet({q['hifld_schools']}) AS p
      ON {bbox('p')} AND ST_Contains(t.geometry, p.geometry)
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


def aggregate_query(region: str) -> str:
    return _aggregate_query_for_registry(region, source_registry(region))


def _reader_sql(key: str, source: str) -> str:
    quoted = _sql_string(source)
    if key == "sample":
        return f"read_csv_auto({quoted}, header=true, all_varchar=true)"
    return f"read_parquet({quoted})"


def _schema_probe_sql_bound(key: str, source: str) -> str:
    if key not in _required_columns():
        raise AggregationError(f"unknown source key: {key!r}")
    return f"DESCRIBE SELECT * FROM {_reader_sql(key, source)}"


def schema_probe_sql(key: str, uri: str) -> str:
    _safe_source(uri)
    return _schema_probe_sql_bound(key, uri)


def _semantic_probe_sql_for_registry(registry: Mapping[str, str]) -> tuple[str, str]:
    return (
        f"SELECT categories.primary FROM {_reader_sql('overture_pois', registry['overture_pois'])} LIMIT 0",
        "SELECT ST_Length(ST_Transform(ST_GeomFromText('LINESTRING(-112 33,-111.99 33)'), "
        "'EPSG:4326', 'EPSG:5070', always_xy := true)) AS smoke_meters",
    )


def semantic_probe_sql(region: str) -> tuple[str, str]:
    return _semantic_probe_sql_for_registry(source_registry(region))


def _geometry_probe_sql_bound(key: str, source: str) -> str:
    if key not in _geometry_expectations():
        raise AggregationError(f"no geometry contract for source {key!r}")
    return (
        "SELECT DISTINCT upper(ST_GeometryType(geometry)) AS geometry_type "
        f"FROM {_reader_sql(key, source)} WHERE geometry IS NOT NULL ORDER BY 1"
    )


def _geometry_probe_sql(key: str, uri: str) -> str:
    _safe_source(uri)
    return _geometry_probe_sql_bound(key, uri)


def _domain_probe_sql_bound(key: str, source: str) -> str:
    if key == "overture_roads":
        expr = 'CAST("class" AS VARCHAR)'
    elif key == "tiger_roads":
        expr = "CAST(MTFCC AS VARCHAR)"
    elif key == "overture_pois":
        expr = "CAST(categories.primary AS VARCHAR)"
    else:
        raise AggregationError(f"no value-domain contract for source {key!r}")
    return (
        f"SELECT DISTINCT {expr} AS value FROM {_reader_sql(key, source)} "
        f"WHERE {expr} IS NOT NULL ORDER BY 1"
    )


def _domain_probe_sql(key: str, uri: str) -> str:
    _safe_source(uri)
    return _domain_probe_sql_bound(key, uri)


def _custody_probe_sql_for_registry(region: str, registry: Mapping[str, str]) -> str:
    _region(region)
    return f"""
WITH authoritative AS (
  SELECT CAST(GEOID AS VARCHAR) AS GEOID
  FROM {_reader_sql('sample', registry['sample'])}
), tract_raw AS (
  SELECT CAST(GEOID AS VARCHAR) AS GEOID
  FROM {_reader_sql('tracts', registry['tracts'])}
), tract_ids AS (
  SELECT DISTINCT GEOID FROM tract_raw
)
SELECT (SELECT COUNT(*) FROM authoritative) AS sample_rows,
       (SELECT COUNT(DISTINCT GEOID) FROM authoritative) AS sample_unique,
       (SELECT COUNT(*) FROM authoritative WHERE NOT regexp_full_match(GEOID, '^[0-9]{{11}}$')) AS bad_geoid,
       (SELECT COUNT(*) FROM authoritative a LEFT JOIN tract_ids t USING (GEOID) WHERE t.GEOID IS NULL) AS missing_tract,
       (SELECT COUNT(*) - COUNT(DISTINCT tr.GEOID)
          FROM tract_raw tr INNER JOIN authoritative a USING (GEOID)) AS duplicate_tract_rows
""".strip()


def _custody_probe_sql(region: str) -> str:
    return _custody_probe_sql_for_registry(region, source_registry(region))


def _preflight_probe_sql_for_registry(region: str, registry: Mapping[str, str]) -> dict[str, str]:
    _region(region)
    expected_keys = tuple(source_registry(region))
    if tuple(registry) != expected_keys:
        raise AggregationError("bound source registry keys/order mismatch")
    probes: dict[str, str] = {}
    for key in expected_keys:
        probes[f"schema:{key}"] = _schema_probe_sql_bound(key, registry[key])
    probes["custody"] = _custody_probe_sql_for_registry(region, registry)
    for key in _geometry_expectations():
        probes[f"geometry:{key}"] = _geometry_probe_sql_bound(key, registry[key])
    probes["domain:overture_roads"] = _domain_probe_sql_bound("overture_roads", registry["overture_roads"])
    probes["domain:tiger_roads"] = _domain_probe_sql_bound("tiger_roads", registry["tiger_roads"])
    probes["domain:overture_pois"] = _domain_probe_sql_bound("overture_pois", registry["overture_pois"])
    nested, axis = _semantic_probe_sql_for_registry(registry)
    probes["semantic:overture_poi_category"] = nested
    probes["semantic:axis_order"] = axis
    return probes


def preflight_probe_sql(region: str) -> dict[str, str]:
    return _preflight_probe_sql_for_registry(region, source_registry(region))


def validate_source_schema(key: str, columns: Iterable[str]) -> None:
    columns = tuple(str(column) for column in columns)
    required = _required_columns()
    if key not in required:
        raise AggregationError(f"unknown source key: {key!r}")
    actual = set(columns)
    missing = sorted(set(required[key]) - actual)
    if missing:
        raise AggregationError(f"{key}: current source schema missing required columns {missing}")
    if key == "sample":
        return
    for column in columns:
        token = _forbidden_token(column)
        if token is not None:
            raise AggregationError(
                f"{key}: forbidden answer/reference-like column present: {column!r}"
            )


def _validate_policy_categories(name: str, values: Sequence[str]) -> None:
    expected = _policy_values().get(name)
    if expected is None:
        raise AggregationError(f"unknown published filter domain: {name}")
    if tuple(values) != expected:
        raise AggregationError(
            f"{name}: policy category drift; expected {expected!r}, got {tuple(values)!r}"
        )


def _validate_custody(region: str, row: Sequence[object]) -> dict[str, int]:
    if len(row) != 5:
        raise AggregationError(f"{region}: custody probe shape mismatch")
    sample_rows, sample_unique, bad_geoid, missing_tract, duplicate_tract_rows = (int(v) for v in row)
    expected = _region_counts()[_region(region)]
    if sample_rows != expected or sample_unique != expected:
        raise AggregationError(
            f"{region}: authoritative GEOID custody drift: rows={sample_rows}, "
            f"unique={sample_unique}, expected={expected}"
        )
    if bad_geoid or missing_tract or duplicate_tract_rows:
        raise AggregationError(
            f"{region}: authoritative GEOID custody failure: bad_geoid={bad_geoid}, "
            f"missing_tract={missing_tract}, duplicate_tract_rows={duplicate_tract_rows}"
        )
    return {
        "sample_rows": sample_rows,
        "sample_unique": sample_unique,
        "bad_geoid": bad_geoid,
        "missing_tract": missing_tract,
        "duplicate_tract_rows": duplicate_tract_rows,
    }


def _validate_geometry_domain(key: str, values: Iterable[object]) -> list[str]:
    observed = sorted({str(value).upper() for value in values if value is not None})
    allowed = _geometry_expectations()[key]
    if not observed:
        raise AggregationError(f"{key}: empty geometry domain")
    unexpected = sorted(set(observed) - set(allowed))
    if unexpected:
        raise AggregationError(f"{key}: unexpected geometry types {unexpected}; allowed={sorted(allowed)}")
    return observed


def _domain_receipt(name: str, observed: Iterable[object]) -> dict[str, object]:
    values = sorted({str(value) for value in observed if value is not None})
    serialized = json.dumps(values, ensure_ascii=True, separators=(",", ":"))
    published = _policy_values()[name]
    return {
        "observed_value_count": len(values),
        "observed_values_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "published_values_present": sorted(set(values).intersection(published)),
    }


def _canonicalize_bound_sql(sql: str, registry: Mapping[str, str],
                            generations: Mapping[str, Mapping[str, object]]) -> str:
    canonical = sql
    for key, path in registry.items():
        digest = str(generations[key]["sha256"])
        canonical = canonical.replace(str(path), f"sha256://{digest}/{key}")
    return canonical


def run_preflight(
    connection: object,
    region: str,
    registry: Optional[Mapping[str, str]] = None,
    generations: Optional[Mapping[str, Mapping[str, object]]] = None,
) -> dict[str, object]:
    bound = dict(registry) if registry is not None else source_registry(region)
    probes = _preflight_probe_sql_for_registry(region, bound)
    schemas: dict[str, object] = {}
    public_sources = source_registry(region)

    for key in public_sources:
        description = connection.execute(probes[f"schema:{key}"]).fetchall()
        columns = [str(row[0]) for row in description]
        validate_source_schema(key, columns)
        item: dict[str, object] = {
            "uri": public_sources[key],
            "columns": columns,
            "describe_sha256": _digest_schema(description),
        }
        if generations is not None:
            item["content_sha256"] = generations[key]["sha256"]
            item["content_bytes"] = generations[key]["bytes"]
        schemas[key] = item

    custody_row = connection.execute(probes["custody"]).fetchone()
    if custody_row is None:
        raise AggregationError(f"{region}: custody probe returned no row")
    custody = _validate_custody(region, custody_row)

    geometries: dict[str, list[str]] = {}
    for key in _geometry_expectations():
        rows = connection.execute(probes[f"geometry:{key}"]).fetchall()
        geometries[key] = _validate_geometry_domain(key, (row[0] for row in rows))

    road_rows = connection.execute(probes["domain:overture_roads"]).fetchall()
    tiger_rows = connection.execute(probes["domain:tiger_roads"]).fetchall()
    poi_rows = connection.execute(probes["domain:overture_pois"]).fetchall()
    poi_values = [row[0] for row in poi_rows]
    domains = {
        "overture_roads.class": _domain_receipt("overture_roads.class", (row[0] for row in road_rows)),
        "tiger_roads.MTFCC": _domain_receipt("tiger_roads.MTFCC", (row[0] for row in tiger_rows)),
        "overture_pois.school": _domain_receipt("overture_pois.school", poi_values),
        "overture_pois.fire": _domain_receipt("overture_pois.fire", poi_values),
        "overture_pois.ems": _domain_receipt("overture_pois.ems", poi_values),
    }

    connection.execute(probes["semantic:overture_poi_category"])
    axis_row = connection.execute(probes["semantic:axis_order"]).fetchone()
    if axis_row is None:
        raise AggregationError("axis-order smoke probe returned no row")
    smoke = float(axis_row[0])
    if not math.isfinite(smoke) or not 500.0 < smoke < 2000.0:
        raise AggregationError(f"EPSG axis-order smoke test failed: {smoke!r} metres")

    if generations is None:
        transcript = json.dumps(probes, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    else:
        canonical_probes = {
            name: _canonicalize_bound_sql(sql, bound, generations)
            for name, sql in probes.items()
        }
        transcript = json.dumps(canonical_probes, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "probe_sql_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        "schemas": schemas,
        "custody": custody,
        "geometry_domains": geometries,
        "value_domains": domains,
        "axis_order_smoke_meters": smoke,
    }


def build_plan(region: str) -> dict[str, object]:
    region = _region(region)
    sources = source_registry(region)
    query = aggregate_query(region)
    probes = preflight_probe_sql(region)
    transcript = json.dumps(probes, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "schema": "mapping-equity-public-aggregation/v2",
        "region": region,
        "expected_scored_rows": _region_counts()[region],
        "duckdb_version": "1.5.4",
        "overture_release": "2026-08-19.0",
        "sources": sources,
        "required_columns": {k: list(_required_columns()[k]) for k in sources},
        "source_policy": {
            "answer_artifact_paths_forbidden": True,
            "sample_submission_projection": ["GEOID"],
            "sample_score_column_never_selected": True,
            "run_materialization": "one remote response -> SHA-256 -> retained fd generation",
            "preflight_and_scoring_share_generation": True,
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
        "output_columns": list(_output_columns()),
        "preflight": {
            "must_complete_before_aggregation": True,
            "probe_sql": probes,
            "probe_sql_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
            "geometry_expectations": {k: sorted(v) for k, v in _geometry_expectations().items()},
            "published_policy_values": {k: list(v) for k, v in _policy_values().items()},
        },
    }


def validate_rows(region: str, fieldnames: Sequence[str], rows: Sequence[Sequence[object]]) -> list[tuple[object, ...]]:
    region = _region(region)
    output_columns = _output_columns()
    if tuple(fieldnames) != output_columns:
        raise AggregationError(f"aggregate output columns mismatch: {fieldnames!r}")
    expected = _region_counts()[region]
    if len(rows) != expected:
        raise AggregationError(f"{region}: expected {expected} scored tracts, got {len(rows)}")
    seen: set[str] = set()
    cleaned: list[tuple[object, ...]] = []
    geoid_re = re.compile(r"^[0-9]{11}$")
    for index, row in enumerate(rows, start=1):
        if len(row) != len(output_columns):
            raise AggregationError(f"row {index}: expected {len(output_columns)} values")
        geoid = row[0]
        if type(geoid) is not str or geoid_re.fullmatch(geoid) is None:
            raise AggregationError(f"row {index}: GEOID must remain 11-digit text")
        if geoid in seen:
            raise AggregationError(f"duplicate GEOID: {geoid}")
        seen.add(geoid)
        values: list[object] = [geoid]
        for name, raw in zip(output_columns[1:], row[1:]):
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
    writer.writerow(_output_columns())
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


class _MaterializedSources:
    def __init__(self, tempdir: tempfile.TemporaryDirectory[str], registry: dict[str, str], generations: dict[str, dict[str, object]], fds: list[int]) -> None:
        self.tempdir = tempdir
        self.registry = registry
        self.generations = generations
        self.fds = fds

    def close(self) -> None:
        for fd in self.fds:
            try:
                os.close(fd)
            except OSError:
                pass
        self.fds.clear()
        self.tempdir.cleanup()


def _stream_response_to_retained_fd(key: str, uri: str, response: BinaryIO, temp_root: Path) -> tuple[int, str, dict[str, object]]:
    """Stream one response into an anonymous inode, then retain it read-only."""
    hasher = hashlib.sha256()
    byte_count = 0
    writer = tempfile.TemporaryFile(mode="w+b", dir=temp_root)
    try:
        while True:
            chunk = response.read(8 * 1024 * 1024)
            if not chunk:
                break
            if not isinstance(chunk, (bytes, bytearray)):
                raise AggregationError(f"{key}: source response yielded non-bytes")
            writer.write(chunk)
            hasher.update(chunk)
            byte_count += len(chunk)
        writer.flush()
        os.fsync(writer.fileno())
        if byte_count <= 0:
            raise AggregationError(f"{key}: empty source object")
        fd = os.open(f"/proc/self/fd/{writer.fileno()}", os.O_RDONLY)
        stat = os.fstat(fd)
        if stat.st_size != byte_count:
            os.close(fd)
            raise AggregationError(f"{key}: retained source size changed during materialization")
    finally:
        writer.close()
    digest = hasher.hexdigest()
    return fd, f"/proc/self/fd/{fd}", {
        "uri": uri,
        "sha256": digest,
        "bytes": byte_count,
        "generation": f"sha256:{digest}",
    }


def _materialize_one(key: str, uri: str, temp_root: Path, _opener=_URL_OPEN) -> tuple[int, str, dict[str, object]]:
    _safe_source(uri)
    try:
        response = _opener(uri, timeout=300)
    except Exception as exc:
        raise AggregationError(f"{key}: public source download failed") from exc
    try:
        final_url = getattr(response, "geturl", lambda: uri)()
        parts = urlsplit(str(final_url))
        if parts.scheme != "https" or parts.username or parts.password:
            raise AggregationError(f"{key}: source redirect left credential-free HTTPS")
        token = _forbidden_token(str(final_url))
        if token is not None:
            raise AggregationError(f"{key}: source redirect contains forbidden token {token!r}")
        return _stream_response_to_retained_fd(key, uri, response, temp_root)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _materialize_sources(region: str, _one=_materialize_one) -> _MaterializedSources:
    region = _region(region)
    if not Path("/proc/self/fd").is_dir():
        raise AggregationError("run requires Linux /proc/self/fd so DuckDB can consume retained exact source generations")
    tempdir = tempfile.TemporaryDirectory(prefix=f"mapping-equity-{region}-")
    root = Path(tempdir.name)
    os.chmod(root, 0o700)
    registry: dict[str, str] = {}
    generations: dict[str, dict[str, object]] = {}
    fds: list[int] = []
    try:
        for key, uri in source_registry(region).items():
            fd, fd_path, generation = _one(key, uri, root)
            fds.append(fd)
            registry[key] = fd_path
            generations[key] = generation
        return _MaterializedSources(tempdir, registry, generations, fds)
    except Exception:
        for fd in fds:
            try:
                os.close(fd)
            except OSError:
                pass
        tempdir.cleanup()
        raise


def _connect_duckdb():
    try:
        import duckdb  # type: ignore
    except ImportError as exc:
        raise AggregationError("run requires duckdb==1.5.4; plan/tests are stdlib-only") from exc
    if duckdb.__version__ != "1.5.4":
        raise AggregationError(f"duckdb version drift: require 1.5.4, found {duckdb.__version__}")
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    return con


def execute_region(region: str, output: Path, receipt: Path, _materializer=_materialize_sources, _connector=_connect_duckdb, _query_builder=_aggregate_query_for_registry) -> dict[str, object]:
    region = _region(region)
    if output.resolve() == receipt.resolve():
        raise AggregationError("output and receipt must be different paths")
    if output.exists() or receipt.exists():
        raise AggregationError("run outputs are create-exclusive; choose fresh paths")
    materialized = _materializer(region)
    con = None
    try:
        con = _connector()
        preflight = run_preflight(con, region, materialized.registry, materialized.generations)
        query = _query_builder(region, materialized.registry)
        cursor = con.execute(query)
        fieldnames = [str(desc[0]) for desc in cursor.description]
        rows = cursor.fetchall()
        cleaned = validate_rows(region, fieldnames, rows)
        csv_text = render_csv(cleaned)
        csv_sha = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
        canonical_query = _canonicalize_bound_sql(query, materialized.registry, materialized.generations)
        generation_receipt = {
            key: {"uri": value["uri"], "sha256": value["sha256"], "bytes": value["bytes"], "generation": value["generation"]}
            for key, value in materialized.generations.items()
        }
        payload = {
            "schema": "mapping-equity-public-aggregation/v2",
            "region": region,
            "duckdb_version": "1.5.4",
            "overture_release": "2026-08-19.0",
            "real_public_data_executed": True,
            "row_count": len(cleaned),
            "output_csv_sha256": csv_sha,
            "input_generations": generation_receipt,
            "bound_query_sha256": hashlib.sha256(canonical_query.encode("utf-8")).hexdigest(),
            "preflight": preflight,
            "plan": build_plan(region),
            "claims": {
                "zindi_registered": False,
                "submitted_to_zindi": False,
                "leaderboard_score_claimed": False,
                "award_claimed": False,
                "payment_claimed": False,
            },
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        envelope = {"payload": payload, "payload_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}
        receipt_text = json.dumps(envelope, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
        _write_new(output, csv_text)
        _write_new(receipt, receipt_text)
        return {"region": region, "rows": len(cleaned), "output_csv_sha256": csv_sha}
    finally:
        if con is not None:
            con.close()
        materialized.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan_cmd = sub.add_parser("plan", help="emit deterministic no-download plan + preflight SQL")
    plan_cmd.add_argument("--region", required=True, choices=tuple(REGIONS))
    plan_cmd.add_argument("--sql", action="store_true", help="include aggregate SQL")
    run_cmd = sub.add_parser("run", help="materialize + execute one public region with DuckDB 1.5.4")
    run_cmd.add_argument("--region", required=True, choices=tuple(REGIONS))
    run_cmd.add_argument("--output", required=True)
    run_cmd.add_argument("--receipt", required=True)
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
