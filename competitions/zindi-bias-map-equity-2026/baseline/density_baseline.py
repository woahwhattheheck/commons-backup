#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Original local-file density-rank candidate; no target fitting or network I/O.

Publication validation is static only. Read README.md before running.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys

REGION_ROWS = {
    "eastern-ok": 1192,
    "maricopa-az": 1593,
    "northern-ca": 591,
    "south-central-tx": 6003,
}
RELEASE = "2026-08-19.0"
DUCKDB_VERSION = "1.5.4"
DATA_URL = "https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/"
METHOD = "regional-density-midrank/v1"
GEOID_RE = re.compile(r"[0-9]{11}\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


class InputError(ValueError):
    pass


def required_paths(region):
    return {
        "sample": f"reference/{region}/{region}-sample-submission.csv",
        "tracts": f"strata/{region}/{region}-census-tracts.parquet",
        "buildings": f"reference/{region}/{region}-overture-buildings.parquet",
        "roads": f"reference/{region}/{region}-overture-roads.parquet",
        "pois": f"reference/{region}/{region}-overture-pois.parquet",
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def qualify_inputs(root, manifest_path, region):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise InputError("data root must be a local directory")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise InputError("input manifest must be an object")
    if manifest.get("region") != region or manifest.get("overture_release") != RELEASE:
        raise InputError("manifest region or declared Overture release does not match")
    if manifest.get("crs") != "OGC:CRS84":
        raise InputError("manifest must declare the documented OGC:CRS84 geometry")
    expected = required_paths(region)
    entries = manifest.get("files")
    if not isinstance(entries, dict) or set(entries) != set(expected.values()):
        raise InputError("manifest files must be exactly the five documented regional inputs")
    paths, receipt = {}, {}
    for role, relative in expected.items():
        item = entries[relative]
        if not isinstance(item, dict):
            raise InputError(f"{relative}: manifest record must be an object")
        digest = item.get("sha256")
        if not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
            raise InputError(f"{relative}: require a recorded lowercase SHA-256")
        if item.get("source_url") != DATA_URL + relative:
            raise InputError(f"{relative}: source URL must identify this supplied file")
        if not isinstance(item.get("retrieved_at"), str) or not item["retrieved_at"].strip():
            raise InputError(f"{relative}: record the actual retrieval date/time")
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise InputError(f"{relative}: require a regular file within data root")
        if any(char in str(path) for char in "*?[]"):
            raise InputError(f"{relative}: local path contains a Parquet glob metacharacter")
        actual = sha256_file(path)
        if actual != digest:
            raise InputError(f"{relative}: bytes differ from the supplied provenance manifest")
        paths[role] = path
        receipt[relative] = {
            "sha256": actual,
            "bytes": path.stat().st_size,
            "source_url": item["source_url"],
            "retrieved_at": item["retrieved_at"],
        }
    return paths, receipt, manifest_sha256


def sample_ids(path, region):
    # Only GEOID is consumed. Sample component/score cells are never features.
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or "GEOID" not in fields:
            raise InputError("sample requires unique column names and exact GEOID column")
        ids = []
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise InputError(f"sample row {line}: malformed CSV width")
            geoid = row["GEOID"]
            if not GEOID_RE.fullmatch(geoid):
                raise InputError(f"sample row {line}: GEOID must remain 11 ASCII digits")
            ids.append(geoid)
    if len(ids) != REGION_ROWS[region] or len(set(ids)) != len(ids):
        raise InputError("sample membership has duplicates or differs from the dated region count")
    return ids


def scalar(con, sql, parameters=None):
    return con.execute(sql, parameters or []).fetchone()[0]


def require_zero(con, sql, message):
    count = scalar(con, sql)
    if count:
        raise InputError(f"{message} ({count} rows)")


def check_geometry(con, table, types, lonlat):
    # table and types come only from fixed program constants.
    allowed = ", ".join("'" + value + "'" for value in types)
    require_zero(
        con,
        f"""SELECT count(*) FROM {table}
            WHERE g IS NULL OR ST_IsEmpty(g)
               OR NOT ST_IsValid(g)
               OR CAST(ST_GeometryType(g) AS VARCHAR) NOT IN ({allowed})""",
        f"{table}: null, empty, invalid or unsupported geometry",
    )
    checks = [
        f"NOT isfinite(ST_{axis}{edge}(g))"
        for axis in ("X", "Y") for edge in ("Min", "Max")
    ]
    if lonlat:
        checks += [
            "ST_XMin(g) < -180", "ST_XMax(g) > 180",
            "ST_YMin(g) < -90", "ST_YMax(g) > 90",
        ]
    require_zero(
        con, f"SELECT count(*) FROM {table} WHERE " + " OR ".join(checks),
        f"{table}: nonfinite geometry envelope or coordinates outside declared CRS bounds",
    )


def load_tracts(con, path, ids):
    con.execute("CREATE TABLE membership (GEOID VARCHAR PRIMARY KEY, position INTEGER)")
    con.executemany(
        "INSERT INTO membership VALUES (?, ?)",
        [(geoid, position) for position, geoid in enumerate(ids)],
    )
    schema = con.execute("DESCRIBE SELECT GEOID, geometry FROM read_parquet(?)", [str(path)]).fetchall()
    if schema[0][1] != "VARCHAR" or schema[1][1] != "GEOMETRY":
        raise InputError("tract schema must store GEOID as VARCHAR and geometry as GEOMETRY")
    con.execute(
        """CREATE TABLE tract_input AS
           SELECT GEOID, geometry AS g FROM read_parquet(?)""", [str(path)]
    )
    require_zero(
        con,
        """SELECT count(*) FROM (
             SELECT t.GEOID FROM tract_input t JOIN membership m USING (GEOID)
             GROUP BY t.GEOID HAVING count(*) <> 1
           )""",
        "scored tract geometry is duplicated",
    )
    require_zero(
        con,
        """SELECT count(*) FROM membership m
           LEFT JOIN tract_input t USING (GEOID) WHERE t.GEOID IS NULL""",
        "scored tract has no geometry; refusing zero-fill",
    )
    con.execute(
        """CREATE TABLE tract_ll AS
           SELECT t.GEOID, t.g FROM tract_input t JOIN membership m USING (GEOID)"""
    )
    check_geometry(con, "tract_ll", ("POLYGON", "MULTIPOLYGON"), True)
    con.execute(
        """CREATE TABLE tracts AS
           SELECT GEOID, ST_Transform(g, 'OGC:CRS84', 'EPSG:5070', always_xy := true) AS g
           FROM tract_ll"""
    )
    check_geometry(con, "tracts", ("POLYGON", "MULTIPOLYGON"), False)
    con.execute("ALTER TABLE tracts ADD COLUMN area_km2 DOUBLE")
    con.execute("UPDATE tracts SET area_km2 = ST_Area(g) / 1000000.0")
    require_zero(
        con, "SELECT count(*) FROM tracts WHERE NOT isfinite(area_km2) OR area_km2 <= 0",
        "scored tract has invalid/nonpositive projected area",
    )
    return {
        "scored_tracts": len(ids),
        "unscored_tract_rows_excluded": scalar(
            con, """SELECT count(*) FROM tract_input t
                    WHERE NOT EXISTS (SELECT 1 FROM membership m WHERE m.GEOID=t.GEOID)"""
        ),
    }


def load_layer(con, path, types):
    schema = con.execute("DESCRIBE SELECT geometry FROM read_parquet(?)", [str(path)]).fetchall()
    if schema[0][1] != "GEOMETRY":
        raise InputError("supplied layer must expose GeoParquet geometry as GEOMETRY")
    con.execute(
        """CREATE TABLE layer_ll AS
           SELECT row_number() OVER () AS row_id, geometry AS g FROM read_parquet(?)""",
        [str(path)],
    )
    count = scalar(con, "SELECT count(*) FROM layer_ll")
    if not count:
        raise InputError("provided feature layer is empty; refusing an unsupported all-zero family")
    check_geometry(con, "layer_ll", types, True)
    con.execute(
        """CREATE TABLE layer AS
           SELECT row_id,
             ST_Transform(g, 'OGC:CRS84', 'EPSG:5070', always_xy := true) AS g
           FROM layer_ll"""
    )
    check_geometry(con, "layer", types, False)
    return count


def clear_layer(con):
    con.execute("DROP TABLE layer")
    con.execute("DROP TABLE layer_ll")


def count_features(con, path, kind):
    types = ("POLYGON", "MULTIPOLYGON") if kind == "buildings" else ("POINT",)
    count = load_layer(con, path, types)
    point = "ST_PointOnSurface(g)" if kind == "buildings" else "g"
    con.execute(f"CREATE TABLE points AS SELECT row_id, {point} AS g FROM layer")
    # Boundary policy: one input row -> lowest lexical scored GEOID covering its point.
    con.execute(
        """CREATE TABLE assigned AS
           SELECT p.row_id, min(t.GEOID) AS GEOID, count(*) AS matches
           FROM points p JOIN tracts t ON ST_Covers(t.g,p.g)
           GROUP BY p.row_id"""
    )
    rows = con.execute(
        "SELECT GEOID, count(*) FROM assigned GROUP BY GEOID ORDER BY GEOID"
    ).fetchall()
    report = {
        "input_rows": count,
        "assigned_rows": scalar(con, "SELECT count(*) FROM assigned"),
        "unassigned_rows": count - scalar(con, "SELECT count(*) FROM assigned"),
        "multiple_matches_resolved": scalar(con, "SELECT count(*) FROM assigned WHERE matches > 1"),
        "allocation": "lowest lexical scored GEOID covering representative point",
    }
    con.execute("DROP TABLE assigned")
    con.execute("DROP TABLE points")
    clear_layer(con)
    return dict(rows), report


def road_lengths(con, path):
    count = load_layer(con, path, ("LINESTRING", "MULTILINESTRING"))
    con.execute(
        """CREATE TABLE road_clips AS
           SELECT r.row_id, t.GEOID, ST_Length(ST_Intersection(r.g,t.g)) AS metres
           FROM layer r JOIN tracts t ON ST_Intersects(r.g,t.g)"""
    )
    require_zero(
        con, "SELECT count(*) FROM road_clips WHERE metres IS NULL OR NOT isfinite(metres) OR metres < 0",
        "road intersection produced invalid length",
    )
    # A boundary-coincident segment contributes to each intersected tract.
    # This is a declared local-density convention, not a regional length inventory.
    rows = con.execute(
        """SELECT GEOID, sum(metres ORDER BY metres)
           FROM road_clips GROUP BY GEOID ORDER BY GEOID"""
    ).fetchall()
    report = {
        "input_rows": count,
        "rows_intersecting_scored_geometry": scalar(con, "SELECT count(DISTINCT row_id) FROM road_clips"),
        "positive_length_tract_intersections": scalar(con, "SELECT count(*) FROM road_clips WHERE metres > 0"),
        "allocation": "clipped length in each scored tract; shared boundary length can be credited twice",
    }
    con.execute("DROP TABLE road_clips")
    clear_layer(con)
    return dict(rows), report


def midrank_deficits(values):
    """Ties share a rank. A constant family, including all zero, yields 0.5."""
    n = len(values)
    if n < 2 or any(not math.isfinite(x) or x < 0 for x in values):
        raise InputError("density ranking requires at least two finite nonnegative values")
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    result = [0.0] * n
    lo = 0
    while lo < n:
        hi = lo + 1
        while hi < n and ordered[hi][1] == ordered[lo][1]:
            hi += 1
        deficit = 1.0 - (lo + (hi - lo - 1) / 2.0) / (n - 1)
        for index, _ in ordered[lo:hi]:
            result[index] = deficit
        lo = hi
    return result


def write_csv(path, fields, rows):
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(args):
    paths, pinned_inputs, manifest_sha256 = qualify_inputs(args.data_root, args.manifest, args.region)
    ids = sample_ids(paths["sample"], args.region)
    if args.out_dir.exists():
        raise InputError("output directory must not already exist; preserve earlier runs")
    import duckdb
    if duckdb.__version__ != DUCKDB_VERSION:
        raise InputError(f"require DuckDB {DUCKDB_VERSION}; found {duckdb.__version__}")
    con = duckdb.connect(config={
        "threads": "1",
        "memory_limit": "2GB",
        "autoinstall_known_extensions": "false",
        "autoload_known_extensions": "false",
    })
    try:
        con.execute("LOAD spatial")  # Must already be installed; no INSTALL/httpfs.
        tract_report = load_tracts(con, paths["tracts"], ids)
        buildings, building_report = count_features(con, paths["buildings"], "buildings")
        pois, poi_report = count_features(con, paths["pois"], "pois")
        roads, road_report = road_lengths(con, paths["roads"])
        areas = dict(con.execute("SELECT GEOID, area_km2 FROM tracts").fetchall())
    finally:
        con.close()
    if set(areas) != set(ids):
        raise InputError("post-aggregation tract membership changed")
    audit = []
    for geoid in ids:
        area = areas[geoid]
        row = {
            "region": args.region, "GEOID": geoid, "area_km2": area,
            "building_rows": buildings.get(geoid, 0),
            "poi_rows": pois.get(geoid, 0),
            "road_intersection_metres": roads.get(geoid, 0.0),
        }
        row["building_density"] = row["building_rows"] / area
        row["poi_density"] = row["poi_rows"] / area
        row["road_density"] = row["road_intersection_metres"] / area
        audit.append(row)
    for family in ("building", "poi", "road"):
        ranks = midrank_deficits([row[f"{family}_density"] for row in audit])
        for row, rank in zip(audit, ranks):
            row[f"{family}_rank_deficit"] = rank
    for row in audit:
        row["coverage_gap_score"] = math.fsum(
            row[f"{family}_rank_deficit"] for family in ("building", "poi", "road")
        ) / 3.0
        if not math.isfinite(row["coverage_gap_score"]) or not 0 <= row["coverage_gap_score"] <= 1:
            raise InputError("invalid candidate score")
    # Detect ordinary input mutation during the run before creating output.
    for role, path in paths.items():
        relative = required_paths(args.region)[role]
        if sha256_file(path) != pinned_inputs[relative]["sha256"]:
            raise InputError(f"{relative}: input bytes changed during the run")
    if sha256_file(args.manifest) != manifest_sha256:
        raise InputError("input manifest changed during the run")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    prediction_path = args.out_dir / "candidate.csv"
    audit_path = args.out_dir / "density-audit.csv"
    write_csv(prediction_path, ["GEOID", "coverage_gap_score"],
              ({"GEOID": row["GEOID"], "coverage_gap_score": row["coverage_gap_score"]} for row in audit))
    write_csv(audit_path, list(audit[0]), audit)
    receipt = {
        "method": METHOD, "region": args.region, "rows": len(ids),
        "overture_release_declared": RELEASE, "input_crs_declared": "OGC:CRS84",
        "projection": "EPSG:5070, always_xy=true",
        "duckdb_version": duckdb.__version__,
        "source_sha256": sha256_file(Path(__file__)),
        "manifest_sha256": manifest_sha256,
        "inputs": pinned_inputs,
        "geometry_reports": {
            "tracts": tract_report, "buildings": building_report,
            "pois": poi_report, "roads": road_report,
        },
        "outputs": {p.name: {"sha256": sha256_file(p), "bytes": p.stat().st_size}
                    for p in (prediction_path, audit_path)},
        "claim": "Uncalibrated density-rank candidate; no measured coverage, accuracy or equity claim",
        "provenance_limit": "Local pins and source URLs are caller records, not organizer authentication",
    }
    (args.out_dir / "run-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGION_ROWS), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = run(args)
    except (OSError, ValueError, ImportError) as exc:
        print(f"density-baseline: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # DuckDB spatial/binding failures also stop before a successful receipt.
        print(f"density-baseline: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"method": receipt["method"], "region": args.region,
                      "rows": receipt["rows"], "out_dir": str(args.out_dir)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
