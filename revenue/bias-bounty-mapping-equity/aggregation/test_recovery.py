from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import aggregate as a


class RecoveryLeakFenceTests(unittest.TestCase):
    def test_encoded_and_case_variant_answer_paths_fail_closed(self) -> None:
        root = a.HTTPS_ROOT + "/reference/eastern-ok/"
        hostile = (
            root + "eastern-ok-COVERAGE-gap.csv",
            root + "eastern-ok-%63overage%2Dgap.csv",
            root + "eastern-ok-%2563overage%252Dgap.csv",
            root + "eastern-ok-reference%2Danswer.csv",
            root + "eastern-ok-answer%5Fkey.csv",
        )
        for uri in hostile:
            with self.subTest(uri=uri), self.assertRaisesRegex(a.AggregationError, "forbidden"):
                a._safe_source(uri)

    def test_query_fragment_and_cross_origin_sources_fail_closed(self) -> None:
        clean = a.source_registry("eastern-ok")["overture_roads"]
        with self.assertRaises(a.AggregationError):
            a._safe_source(clean + "?alt=coverage")
        with self.assertRaises(a.AggregationError):
            a._safe_source("https://example.com/reference/eastern-ok/eastern-ok-overture-roads.parquet")

    def test_encoded_answer_like_schema_label_fails_closed(self) -> None:
        columns = ["GEOID", "cbp_estab", "reference%5Fanswer"]
        with self.assertRaisesRegex(a.AggregationError, "forbidden"):
            a.validate_source_schema("cbp", columns)


class RecoveryPreflightTests(unittest.TestCase):
    def test_plan_binds_complete_preflight_transcript(self) -> None:
        one = a.build_plan("northern-ca")
        two = a.build_plan("northern-ca")
        self.assertEqual(one, two)
        preflight = one["preflight"]
        self.assertTrue(preflight["must_complete_before_aggregation"])
        probes = preflight["probe_sql"]
        for key in a.source_registry("northern-ca"):
            self.assertIn(f"schema:{key}", probes)
        self.assertIn("custody", probes)
        for key in a.GEOMETRY_EXPECTATIONS:
            self.assertIn(f"geometry:{key}", probes)
        self.assertIn("domain:overture_roads", probes)
        self.assertIn("domain:tiger_roads", probes)
        self.assertIn("domain:overture_pois", probes)
        self.assertIn("semantic:axis_order", probes)
        serialized = json.dumps(preflight, sort_keys=True)
        self.assertIn("ST_GeometryType", serialized)
        self.assertIn("regexp_full_match", serialized)
        self.assertIn("categories.primary", serialized)
        self.assertIn("DESCRIBE SELECT", serialized)
        self.assertNotIn("coverage-gap.csv", serialized.lower())
        self.assertEqual(
            one["source_policy"]["run_materialization"],
            "one remote response -> SHA-256 -> retained fd generation",
        )
        self.assertTrue(one["source_policy"]["preflight_and_scoring_share_generation"])

    def test_custody_requires_exact_authoritative_text_universe(self) -> None:
        expected = a.REGIONS["northern-ca"]
        receipt = a._validate_custody("northern-ca", (expected, expected, 0, 0, 0))
        self.assertEqual(expected, receipt["sample_unique"])
        hostile = (
            (expected - 1, expected - 1, 0, 0, 0),
            (expected, expected - 1, 0, 0, 0),
            (expected, expected, 1, 0, 0),
            (expected, expected, 0, 1, 0),
            (expected, expected, 0, 0, 1),
        )
        for row in hostile:
            with self.subTest(row=row), self.assertRaises(a.AggregationError):
                a._validate_custody("northern-ca", row)

    def test_geometry_domain_rejects_unknown_or_empty_types(self) -> None:
        self.assertEqual(
            ["LINESTRING", "MULTILINESTRING"],
            a._validate_geometry_domain("overture_roads", ["MULTILINESTRING", "LINESTRING"]),
        )
        with self.assertRaisesRegex(a.AggregationError, "unexpected geometry"):
            a._validate_geometry_domain("overture_roads", ["POLYGON"])
        with self.assertRaisesRegex(a.AggregationError, "empty geometry"):
            a._validate_geometry_domain("overture_roads", [])

    def test_observed_domain_receipt_is_deterministic_without_forcing_presence(self) -> None:
        receipt = a._domain_receipt("overture_roads.class", ["residential", "motorway", "motorway"])
        self.assertEqual(2, receipt["observed_value_count"])
        self.assertEqual(["motorway"], receipt["published_values_present"])
        self.assertEqual(receipt, a._domain_receipt("overture_roads.class", ["motorway", "residential"]))

    def test_unknown_policy_category_fails_before_query_generation(self) -> None:
        with self.assertRaisesRegex(a.AggregationError, "policy category drift"):
            a._validate_policy_categories("overture_roads.class", (*a.ROAD_CLASSES[:-1], "space_laser"))
        with self.assertRaisesRegex(a.AggregationError, "unknown published filter domain"):
            a._validate_policy_categories("unknown.domain", ("x",))

    def test_domain_probe_sql_is_exact_source_scoped(self) -> None:
        registry = a.source_registry("maricopa-az")
        roads = a._domain_probe_sql("overture_roads", registry["overture_roads"])
        tiger = a._domain_probe_sql("tiger_roads", registry["tiger_roads"])
        pois = a._domain_probe_sql("overture_pois", registry["overture_pois"])
        self.assertIn('"class"', roads)
        self.assertIn("MTFCC", tiger)
        self.assertIn("categories.primary", pois)
        self.assertIn("maricopa-az", roads)


class GenerationCustodyRegressionTests(unittest.TestCase):
    def test_same_uri_a_to_b_cannot_cross_retained_generation(self) -> None:
        uri = a.source_registry("northern-ca")["sample"]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fd_a, path_a, gen_a = a._stream_response_to_retained_fd("sample", uri, io.BytesIO(b"generation-A"), root)
            fd_b, path_b, gen_b = a._stream_response_to_retained_fd("sample", uri, io.BytesIO(b"generation-B"), root)
            try:
                self.assertNotEqual(gen_a["sha256"], gen_b["sha256"])
                self.assertEqual(gen_a["sha256"], hashlib.sha256(b"generation-A").hexdigest())
                self.assertEqual(gen_b["sha256"], hashlib.sha256(b"generation-B").hexdigest())
                with open(path_a, "rb") as retained:
                    self.assertEqual(retained.read(), b"generation-A")
                with open(path_b, "rb") as later:
                    self.assertEqual(later.read(), b"generation-B")
                bound = {key: path_a for key in a.source_registry("northern-ca")}
                probes = a._preflight_probe_sql_for_registry("northern-ca", bound)
                scored = a._aggregate_query_for_registry("northern-ca", bound)
                self.assertNotIn(uri, scored)
                self.assertNotIn(uri, json.dumps(probes, sort_keys=True))
                self.assertIn(path_a, scored)
                self.assertIn(path_a, json.dumps(probes, sort_keys=True))
                self.assertNotIn(path_b, scored)
            finally:
                os.close(fd_a)
                os.close(fd_b)

    def test_canonical_runtime_sql_binds_digest_not_ephemeral_fd_number(self) -> None:
        keys = tuple(a.source_registry("northern-ca"))
        reg1 = {key: f"/proc/self/fd/{100+i}" for i, key in enumerate(keys)}
        reg2 = {key: f"/proc/self/fd/{200+i}" for i, key in enumerate(keys)}
        generations = {key: {"sha256": hashlib.sha256(key.encode()).hexdigest(), "bytes": 1} for key in keys}
        q1 = a._aggregate_query_for_registry("northern-ca", reg1)
        q2 = a._aggregate_query_for_registry("northern-ca", reg2)
        c1 = a._canonicalize_bound_sql(q1, reg1, generations)
        c2 = a._canonicalize_bound_sql(q2, reg2, generations)
        self.assertEqual(c1, c2)
        self.assertNotIn("/proc/self/fd/", c1)
        self.assertIn("sha256://", c1)

    def test_scoring_policy_ignores_mutable_donor_and_public_policy_globals(self) -> None:
        before = a.aggregate_query("northern-ca")
        donor_road, donor_tiger, donor_school = a._core.ROAD_CLASSES, a._core.TIGER_MTFCC, a._core.SCHOOL_CATEGORIES
        public_road, public_tiger, public_school = a.ROAD_CLASSES, a.TIGER_MTFCC, a.SCHOOL_CATEGORIES
        try:
            a._core.ROAD_CLASSES = ("residential",)
            a._core.TIGER_MTFCC = ("S1400",)
            a._core.SCHOOL_CATEGORIES = ("hospital",)
            a.ROAD_CLASSES = ("residential",)
            a.TIGER_MTFCC = ("S1400",)
            a.SCHOOL_CATEGORIES = ("hospital",)
            after = a.aggregate_query("northern-ca")
            self.assertEqual(before, after)
            self.assertIn("'motorway'", after)
            self.assertIn("'S1100'", after)
            self.assertIn("'elementary_school'", after)
            self.assertNotIn("'residential'", after)
            self.assertNotIn("'S1400'", after)
            self.assertNotIn("'hospital'", after)
        finally:
            a._core.ROAD_CLASSES, a._core.TIGER_MTFCC, a._core.SCHOOL_CATEGORIES = donor_road, donor_tiger, donor_school
            a.ROAD_CLASSES, a.TIGER_MTFCC, a.SCHOOL_CATEGORIES = public_road, public_tiger, public_school

    def test_retained_generation_has_no_mutable_source_path(self) -> None:
        uri = a.source_registry("northern-ca")["sample"]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fd, path, generation = a._stream_response_to_retained_fd("sample", uri, io.BytesIO(b"immutable"), root)
            try:
                self.assertEqual(generation["generation"], "sha256:" + generation["sha256"])
                self.assertEqual(list(root.iterdir()), [])
                with open(path, "rb") as retained:
                    self.assertEqual(retained.read(), b"immutable")
            finally:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
