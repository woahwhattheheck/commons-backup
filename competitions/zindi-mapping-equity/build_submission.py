#!/usr/bin/env python3
"""Build raw tract aggregates from public Source Cooperative challenge data.

Requires DuckDB 1.5.4 with httpfs + spatial extensions. The authoritative
coverage-gap label files are deliberately never referenced. This script reads
only the supplied raw/reference layers plus the sample-submission tract list,
then delegates challenge math to score.py.
"""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path
from typing import Optional
from score import AGGREGATE_COLUMNS, read_aggregates, write_diagnostics, write_submission

BASE = "s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"
REGIONS = ("eastern-ok", "maricopa-az", "northern-ca", "south-central-tx")
OVERTURE_RELEASE = "2026-08-19.0"
BUILDING_ASSIGNMENTS = ("centroid", "intersects")

def ref(region: str, suffix: str) -> str: return f"{BASE}/reference/{region}/{region}-{suffix}"
def strata(region: str, suffix: str) -> str: return f"{BASE}/strata/{region}/{region}-{suffix}"
def _sql_string(value: str) -> str: return "'" + value.replace("'", "''") + "'"
def setup_sql() -> str:
    return """INSTALL httpfs;
LOAD httpfs;
INSTALL spatial;
LOAD spatial;
SET s3_region='us-west-2';
SET s3_url_style='path';
"""

def region_sql(region: str, building_assignment: str = "centroid") -> str:
    if region not in REGIONS: raise ValueError(f"unknown region: {region}")
    if building_assignment not in BUILDING_ASSIGNMENTS: raise ValueError(f"unknown building assignment: {building_assignment}")
    sample=ref(region,"sample-submission.csv"); tracts=strata(region,"census-tracts.parquet")
    overture_roads=ref(region,"overture-roads.parquet"); tiger_roads=ref(region,"census-tiger-roads.parquet")
    overture_buildings=ref(region,"overture-buildings.parquet"); microsoft_buildings=ref(region,"microsoft-buildings.parquet")
    overture_pois=ref(region,"overture-pois.parquet"); cbp=ref(region,"census-cbp.parquet")
    fire=ref(region,"hifld-fire-stations.parquet"); ems=ref(region,"hifld-ems-stations.parquet"); schools=ref(region,"hifld-schools.parquet")
    if building_assignment == "centroid":
        overture_building_join="ST_Intersects(t.geometry, ST_Centroid(b.geometry))"; microsoft_building_join=overture_building_join
    else:
        overture_building_join="ST_Intersects(t.geometry, b.geometry)"; microsoft_building_join=overture_building_join
    return f"""
CREATE OR REPLACE TEMP VIEW scored_tracts AS
SELECT CAST(s.GEOID AS VARCHAR) AS GEOID, t.geometry
FROM read_csv({_sql_string(sample)}, types={{'GEOID': 'VARCHAR'}}) AS s
JOIN read_parquet({_sql_string(tracts)}) AS t ON CAST(t.GEOID AS VARCHAR)=CAST(s.GEOID AS VARCHAR);

CREATE OR REPLACE TEMP VIEW overture_road_by_tract AS
SELECT t.GEOID, COALESCE(SUM(ST_Length(ST_Transform(ST_Intersection(r.geometry,t.geometry),'EPSG:4326','EPSG:5070',always_xy := true))),0.0) AS overture_road_m
FROM scored_tracts t LEFT JOIN read_parquet({_sql_string(overture_roads)}) r ON ST_Intersects(t.geometry,r.geometry) AND r."class" IN ('motorway','trunk','primary','secondary') GROUP BY t.GEOID;

CREATE OR REPLACE TEMP VIEW tiger_road_by_tract AS
SELECT t.GEOID, COALESCE(SUM(ST_Length(ST_Transform(ST_Intersection(r.geometry,t.geometry),'EPSG:4326','EPSG:5070',always_xy := true))),0.0) AS tiger_road_m
FROM scored_tracts t LEFT JOIN read_parquet({_sql_string(tiger_roads)}) r ON ST_Intersects(t.geometry,r.geometry) AND r.MTFCC IN ('S1100','S1200') GROUP BY t.GEOID;

CREATE OR REPLACE TEMP VIEW overture_building_by_tract AS
SELECT t.GEOID, COUNT(b.geometry)::DOUBLE AS overture_buildings FROM scored_tracts t LEFT JOIN read_parquet({_sql_string(overture_buildings)}) b ON {overture_building_join} GROUP BY t.GEOID;
CREATE OR REPLACE TEMP VIEW microsoft_building_by_tract AS
SELECT t.GEOID, COUNT(b.geometry)::DOUBLE AS microsoft_buildings FROM scored_tracts t LEFT JOIN read_parquet({_sql_string(microsoft_buildings)}) b ON {microsoft_building_join} GROUP BY t.GEOID;

CREATE OR REPLACE TEMP VIEW overture_poi_features AS
SELECT ROW_NUMBER() OVER () AS feature_id, geometry, categories FROM read_parquet({_sql_string(overture_pois)});
CREATE OR REPLACE TEMP VIEW overture_poi_assignment AS
SELECT p.feature_id,t.GEOID,p.categories FROM overture_poi_features p JOIN scored_tracts t ON ST_Intersects(t.geometry,p.geometry)
QUALIFY ROW_NUMBER() OVER (PARTITION BY p.feature_id ORDER BY t.GEOID)=1;
CREATE OR REPLACE TEMP VIEW overture_poi_by_tract AS
SELECT t.GEOID, COUNT(p.feature_id)::DOUBLE AS overture_pois,
 COUNT(p.feature_id) FILTER (WHERE p.categories.primary='fire_department')::DOUBLE AS overture_fire,
 COUNT(p.feature_id) FILTER (WHERE p.categories.primary='ambulance_and_ems_services')::DOUBLE AS overture_ems,
 COUNT(p.feature_id) FILTER (WHERE p.categories.primary IN ('elementary_school','middle_school','high_school','school','private_school','public_school'))::DOUBLE AS overture_schools
FROM scored_tracts t LEFT JOIN overture_poi_assignment p USING (GEOID) GROUP BY t.GEOID;

CREATE OR REPLACE TEMP VIEW cbp_by_tract AS
SELECT CAST(GEOID AS VARCHAR) AS GEOID, COALESCE(cbp_estab,0)::DOUBLE AS cbp_establishments FROM read_parquet({_sql_string(cbp)});

CREATE OR REPLACE TEMP VIEW fire_features AS SELECT ROW_NUMBER() OVER () AS feature_id,geometry FROM read_parquet({_sql_string(fire)});
CREATE OR REPLACE TEMP VIEW fire_assignment AS SELECT p.feature_id,t.GEOID FROM fire_features p JOIN scored_tracts t ON ST_Intersects(t.geometry,p.geometry)
QUALIFY ROW_NUMBER() OVER (PARTITION BY p.feature_id ORDER BY t.GEOID)=1;
CREATE OR REPLACE TEMP VIEW fire_by_tract AS SELECT t.GEOID,COUNT(p.feature_id)::DOUBLE AS hifld_fire FROM scored_tracts t LEFT JOIN fire_assignment p USING (GEOID) GROUP BY t.GEOID;

CREATE OR REPLACE TEMP VIEW ems_features AS SELECT ROW_NUMBER() OVER () AS feature_id,geometry FROM read_parquet({_sql_string(ems)});
CREATE OR REPLACE TEMP VIEW ems_assignment AS SELECT p.feature_id,t.GEOID FROM ems_features p JOIN scored_tracts t ON ST_Intersects(t.geometry,p.geometry)
QUALIFY ROW_NUMBER() OVER (PARTITION BY p.feature_id ORDER BY t.GEOID)=1;
CREATE OR REPLACE TEMP VIEW ems_by_tract AS SELECT t.GEOID,COUNT(p.feature_id)::DOUBLE AS hifld_ems FROM scored_tracts t LEFT JOIN ems_assignment p USING (GEOID) GROUP BY t.GEOID;

CREATE OR REPLACE TEMP VIEW schools_features AS SELECT ROW_NUMBER() OVER () AS feature_id,geometry FROM read_parquet({_sql_string(schools)});
CREATE OR REPLACE TEMP VIEW schools_assignment AS SELECT p.feature_id,t.GEOID FROM schools_features p JOIN scored_tracts t ON ST_Intersects(t.geometry,p.geometry)
QUALIFY ROW_NUMBER() OVER (PARTITION BY p.feature_id ORDER BY t.GEOID)=1;
CREATE OR REPLACE TEMP VIEW schools_by_tract AS SELECT t.GEOID,COUNT(p.feature_id)::DOUBLE AS hifld_schools FROM scored_tracts t LEFT JOIN schools_assignment p USING (GEOID) GROUP BY t.GEOID;

SELECT t.GEOID,COALESCE(oroad.overture_road_m,0) overture_road_m,COALESCE(troad.tiger_road_m,0) tiger_road_m,
 COALESCE(ob.overture_buildings,0) overture_buildings,COALESCE(mb.microsoft_buildings,0) microsoft_buildings,
 COALESCE(op.overture_pois,0) overture_pois,COALESCE(cbp.cbp_establishments,0) cbp_establishments,
 COALESCE(op.overture_fire,0) overture_fire,COALESCE(fire.hifld_fire,0) hifld_fire,
 COALESCE(op.overture_ems,0) overture_ems,COALESCE(ems.hifld_ems,0) hifld_ems,
 COALESCE(op.overture_schools,0) overture_schools,COALESCE(schools.hifld_schools,0) hifld_schools
FROM scored_tracts t LEFT JOIN overture_road_by_tract oroad USING(GEOID) LEFT JOIN tiger_road_by_tract troad USING(GEOID)
LEFT JOIN overture_building_by_tract ob USING(GEOID) LEFT JOIN microsoft_building_by_tract mb USING(GEOID)
LEFT JOIN overture_poi_by_tract op USING(GEOID) LEFT JOIN cbp_by_tract cbp USING(GEOID)
LEFT JOIN fire_by_tract fire USING(GEOID) LEFT JOIN ems_by_tract ems USING(GEOID) LEFT JOIN schools_by_tract schools USING(GEOID)
ORDER BY t.GEOID;
"""

def connect_duckdb():
    try: import duckdb
    except ModuleNotFoundError as exc: raise RuntimeError("DuckDB is required; install exactly duckdb==1.5.4") from exc
    if getattr(duckdb,"__version__",None)!="1.5.4": raise RuntimeError(f"expected duckdb==1.5.4, got {duckdb.__version__}")
    con=duckdb.connect()
    for statement in setup_sql().split(";\n"):
        if statement.strip(): con.execute(statement.strip())
    return con

def extract_region(con, region: str, building_assignment: str) -> list[dict[str,object]]:
    statements=[part.strip() for part in region_sql(region,building_assignment).split(";\n") if part.strip()]
    for statement in statements[:-1]: con.execute(statement)
    relation=con.execute(statements[-1]); names=[d[0] for d in relation.description]
    return [dict(zip(names,row,strict=True)) for row in relation.fetchall()]

def write_aggregate_csv(rows, path: Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=list(AGGREGATE_COLUMNS),lineterminator="\n"); w.writeheader(); w.writerows(rows)

def main(argv: Optional[list[str]]=None)->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--out-dir",type=Path,default=Path("build/zindi-mapping-equity")); p.add_argument("--region",action="append",choices=REGIONS,dest="regions"); p.add_argument("--building-assignment",choices=BUILDING_ASSIGNMENTS,default="centroid"); p.add_argument("--print-sql",action="store_true"); a=p.parse_args(argv); regions=tuple(a.regions or REGIONS)
    if a.print_sql:
        print(setup_sql())
        for region in regions: print(f"-- region: {region}; Overture release: {OVERTURE_RELEASE}\n{region_sql(region,a.building_assignment)}")
        return 0
    con=connect_duckdb(); a.out_dir.mkdir(parents=True,exist_ok=True); all_rows=[]
    try:
        for region in regions:
            rows=extract_region(con,region,a.building_assignment); write_aggregate_csv(rows,a.out_dir/f"{region}-aggregates.csv"); all_rows.extend(rows)
    finally: con.close()
    write_aggregate_csv(all_rows,a.out_dir/"all-aggregates.csv"); results=read_aggregates(a.out_dir/"all-aggregates.csv"); write_submission(results,a.out_dir/"submission.csv"); write_diagnostics(results,a.out_dir/"components.csv"); return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except RuntimeError as exc: print(f"error: {exc}",file=sys.stderr); raise SystemExit(2)
