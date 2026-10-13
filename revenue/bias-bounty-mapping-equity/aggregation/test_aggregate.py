import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import aggregate as a


class RegistryTests(unittest.TestCase):
    def test_region_row_counts_are_pinned(self):
        self.assertEqual(a.REGIONS, {
            "eastern-ok": 1192,
            "maricopa-az": 1593,
            "northern-ca": 591,
            "south-central-tx": 6003,
        })

    def test_registry_is_exact_and_leak_free(self):
        expected = {
            "sample", "tracts", "overture_roads", "tiger_roads",
            "overture_buildings", "microsoft_buildings", "overture_pois",
            "hifld_fire", "hifld_ems", "hifld_schools", "cbp",
        }
        for region in a.REGIONS:
            registry = a.source_registry(region)
            self.assertEqual(set(registry), expected)
            for uri in registry.values():
                self.assertTrue(uri.startswith(a.HTTPS_ROOT + "/"))
                self.assertIn(f"/{region}/", uri)
                self.assertNotIn("coverage-gap", uri.lower())
                self.assertNotIn("coverage_gap", uri.lower())

    def test_current_reference_and_strata_layout(self):
        r = a.source_registry("maricopa-az")
        self.assertIn("/reference/maricopa-az/maricopa-az-overture-roads.parquet", r["overture_roads"])
        self.assertIn("/strata/maricopa-az/maricopa-az-census-tracts.parquet", r["tracts"])
        self.assertTrue(r["sample"].endswith("maricopa-az-sample-submission.csv"))

    def test_unsafe_source_refused(self):
        with self.assertRaises(a.AggregationError):
            a._safe_source(a.HTTPS_ROOT + "/reference/x/x-coverage-gap.csv")
        with self.assertRaises(a.AggregationError):
            a._safe_source("https://example.com/clean.parquet")

    def test_schema_contract(self):
        self.assertEqual(a.REQUIRED_COLUMNS["cbp"], ("GEOID", "cbp_estab"))
        self.assertIn("MTFCC", a.REQUIRED_COLUMNS["tiger_roads"])
        self.assertIn("class", a.REQUIRED_COLUMNS["overture_roads"])
        self.assertIn("categories", a.REQUIRED_COLUMNS["overture_pois"])


class SqlTests(unittest.TestCase):
    def setUp(self):
        self.sql = a.aggregate_query("maricopa-az")

    def test_answer_artifacts_are_not_mentioned(self):
        low = self.sql.lower()
        self.assertNotIn("coverage-gap", low)
        self.assertNotIn("coverage_gap", low)
        self.assertNotIn("hifld-hospitals", low)
        self.assertNotIn("acs-housing", low)

    def test_authoritative_universe_reads_only_sample_geoid(self):
        self.assertIn("SELECT CAST(GEOID AS VARCHAR) AS GEOID", self.sql)
        self.assertIn("sample-submission.csv", self.sql)

    def test_scored_road_filters_are_exact(self):
        for klass in a.ROAD_CLASSES:
            self.assertIn(f"'{klass}'", self.sql)
        for code in a.TIGER_MTFCC:
            self.assertIn(f"'{code}'", self.sql)
        self.assertNotIn("roads-unfiltered", self.sql)

    def test_poi_categories_are_exact(self):
        self.assertIn("'fire_department'", self.sql)
        self.assertIn("'ambulance_and_ems_services'", self.sql)
        for category in a.SCHOOL_CATEGORIES:
            self.assertIn(f"'{category}'", self.sql)
        self.assertNotIn("'hospital'", self.sql)

    def test_transform_is_axis_safe(self):
        self.assertGreaterEqual(self.sql.count("always_xy := true"), 3)
        self.assertIn("'EPSG:5070'", self.sql)
        self.assertNotIn("ST_Length_Spheroid(geometry)", self.sql)

    def test_roads_are_clipped_before_length(self):
        self.assertGreaterEqual(self.sql.count("ST_Length(ST_Intersection("), 2)

    def test_buildings_use_point_on_surface_assignment(self):
        self.assertEqual(self.sql.count("ST_PointOnSurface"), 2)

    def test_bbox_overlap_has_all_four_comparisons(self):
        for feature in ("r", "b", "p"):
            fragment = a._bbox_overlap(feature)
            self.assertIn(f"{feature}.bbox.xmax >= t.bbox.xmin", fragment)
            self.assertIn(f"{feature}.bbox.xmin <= t.bbox.xmax", fragment)
            self.assertIn(f"{feature}.bbox.ymax >= t.bbox.ymin", fragment)
            self.assertIn(f"{feature}.bbox.ymin <= t.bbox.ymax", fragment)
        self.assertGreaterEqual(self.sql.count("bbox.xmax >= t.bbox.xmin"), 8)

    def test_output_contract_is_exact(self):
        for name in a.OUTPUT_COLUMNS:
            self.assertIn(name, self.sql)
        self.assertTrue(self.sql.rstrip().endswith("ORDER BY a.GEOID"))

    def test_semantic_probes_cover_nested_category_and_axis_smoke(self):
        probes = a.semantic_probe_sql("northern-ca")
        self.assertIn("categories.primary", probes[0])
        self.assertIn("always_xy := true", probes[1])


class PlanTests(unittest.TestCase):
    def test_plan_is_deterministic(self):
        one = a.build_plan("eastern-ok")
        two = a.build_plan("eastern-ok")
        self.assertEqual(one, two)
        self.assertEqual(one["duckdb_version"], "1.5.4")
        self.assertEqual(one["overture_release"], "2026-08-19.0")
        self.assertTrue(one["source_policy"]["answer_artifact_paths_forbidden"])
        self.assertEqual(one["source_policy"]["sample_submission_projection"], ["GEOID"])

    def test_plan_hash_binds_region_sql(self):
        for region in a.REGIONS:
            expected = hashlib.sha256(a.aggregate_query(region).encode()).hexdigest()
            self.assertEqual(a.build_plan(region)["query_sha256"], expected)
        self.assertNotEqual(
            a.build_plan("eastern-ok")["query_sha256"],
            a.build_plan("northern-ca")["query_sha256"],
        )

    def test_schema_probe_is_source_scoped(self):
        r = a.source_registry("northern-ca")
        self.assertIn("read_csv_auto", a.schema_probe_sql("sample", r["sample"]))
        self.assertIn("read_parquet", a.schema_probe_sql("cbp", r["cbp"]))

    def test_missing_schema_column_fails_closed(self):
        with self.assertRaisesRegex(a.AggregationError, "missing required columns"):
            a.validate_source_schema("tiger_roads", ["geometry", "bbox"])

    def test_answer_like_column_fails_closed(self):
        with self.assertRaisesRegex(a.AggregationError, "forbidden"):
            a.validate_source_schema("cbp", ["GEOID", "cbp_estab", "coverage_gap_score"])

    def test_sample_may_be_submission_shaped_but_only_geoid_is_required(self):
        # SampleSubmission is explicitly the authoritative tract universe. Its score
        # placeholder is ignored, not treated as a scored-data source.
        a.validate_source_schema("sample", ["GEOID", "coverage_gap_score"])


class OutputGuardTests(unittest.TestCase):
    def rows(self, region="northern-ca"):
        out = []
        count = a.REGIONS[region]
        # 11 digit synthetic GEOIDs, lexicographically ordered.
        for i in range(count):
            out.append((f"04{i:09d}", *([float(i % 7)] * 12)))
        return out

    def test_valid_rows_and_deterministic_csv(self):
        rows = self.rows()
        cleaned = a.validate_rows("northern-ca", a.OUTPUT_COLUMNS, rows)
        one = a.render_csv(cleaned)
        two = a.render_csv(cleaned)
        self.assertEqual(one, two)
        self.assertTrue(one.startswith("GEOID,overture_road_length,tiger_road_length"))
        self.assertIn("04000000000", one)

    def test_leading_zero_geoid_required(self):
        rows = self.rows()
        rows[0] = (4000000000, *rows[0][1:])
        with self.assertRaisesRegex(a.AggregationError, "GEOID"):
            a.validate_rows("northern-ca", a.OUTPUT_COLUMNS, rows)

    def test_duplicate_geoid_refused(self):
        rows = self.rows()
        rows[1] = rows[0]
        with self.assertRaisesRegex(a.AggregationError, "duplicate GEOID"):
            a.validate_rows("northern-ca", a.OUTPUT_COLUMNS, rows)

    def test_nonfinite_and_negative_refused(self):
        for bad in (float("nan"), float("inf"), -1.0):
            rows = self.rows()
            row = list(rows[0]); row[1] = bad; rows[0] = tuple(row)
            with self.assertRaisesRegex(a.AggregationError, "finite and nonnegative"):
                a.validate_rows("northern-ca", a.OUTPUT_COLUMNS, rows)

    def test_row_count_mismatch_refused(self):
        with self.assertRaisesRegex(a.AggregationError, "expected 591"):
            a.validate_rows("northern-ca", a.OUTPUT_COLUMNS, self.rows()[:-1])

    def test_column_mismatch_refused(self):
        with self.assertRaisesRegex(a.AggregationError, "columns mismatch"):
            a.validate_rows("northern-ca", a.OUTPUT_COLUMNS[:-1], self.rows())

    def test_order_mismatch_refused(self):
        rows = self.rows()
        rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaisesRegex(a.AggregationError, "ordered by GEOID"):
            a.validate_rows("northern-ca", a.OUTPUT_COLUMNS, rows)

    def test_exclusive_writer_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.csv"
            a._write_new(path, "first")
            with self.assertRaisesRegex(a.AggregationError, "overwrite"):
                a._write_new(path, "second")
            self.assertEqual(path.read_text(), "first")


class CliTests(unittest.TestCase):
    def test_plan_cli_needs_no_duckdb(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "aggregate.py"), "plan", "--region", "maricopa-az", "--sql"],
            check=True, capture_output=True, text=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["region"], "maricopa-az")
        self.assertEqual(payload["expected_scored_rows"], 1593)
        self.assertIn("always_xy := true", payload["sql"])
        self.assertNotIn("coverage-gap", payload["sql"].lower())

    def test_run_without_duckdb_fails_with_pin(self):
        # This assertion adapts to developer machines that already have DuckDB:
        # only test the lazy-import diagnostic when the dependency is absent.
        try:
            import duckdb  # noqa: F401
        except ImportError:
            with self.assertRaisesRegex(a.AggregationError, "duckdb==1.5.4"):
                a._connect_duckdb()


if __name__ == "__main__":
    unittest.main()
