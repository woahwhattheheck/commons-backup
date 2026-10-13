import csv
import json
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bias_discovery import (
    COMPONENT_PROVENANCE_COLUMNS,
    MIN_STRONG_BOOTSTRAP_ITERATIONS,
    MIN_STRONG_PERMUTATIONS,
    DEFAULT_EXCLUDED_PREFIXES,
    analyze,
    build_evidence_packet,
    load_scores,
    main,
)


def geoid(index: int, county: str = "04013") -> str:
    return county + f"{index:06d}"


class BiasDiscoveryTests(unittest.TestCase):
    def write_scores(self, path: Path, rows):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["GEOID", "coverage_gap_score"])
            writer.writeheader()
            writer.writerows(rows)


    def write_components(self, path: Path, rows):
        fields = ["GEOID", "coverage_gap_score", *COMPONENT_PROVENANCE_COLUMNS]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                enriched = dict(row)
                enriched.update({
                    "transport_gap": 0.2,
                    "transport_defined": True,
                    "building_gap": 0.3,
                    "building_defined": True,
                    "poi_gap": 0.4,
                    "poi_defined": True,
                })
                writer.writerow(enriched)

    def write_strata(self, path: Path, fieldnames, rows):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_ranks_reproducible_nonfixed_signal_and_excludes_fixed_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores_path = root / "scores.csv"
            strata_path = root / "strata.csv"
            score_rows = []
            strata_rows = []
            for i in range(80):
                county = "04013" if i < 40 else "06075"
                tract = geoid(i, county)
                score = i / 79
                score_rows.append({"GEOID": tract, "coverage_gap_score": score})
                strata_rows.append(
                    {
                        "GEOID": tract,
                        "broadband_metric": i,
                        "weak_metric": i % 7,
                        "SVI_score": i,
                    }
                )
            self.write_scores(scores_path, score_rows)
            self.write_strata(
                strata_path,
                ["GEOID", "broadband_metric", "weak_metric", "SVI_score"],
                strata_rows,
            )
            results = analyze(
                load_scores(scores_path),
                strata_path,
                min_rows=40,
                prefixes=("svi_",),
                bootstrap_iterations=MIN_STRONG_BOOTSTRAP_ITERATIONS,
                permutations=MIN_STRONG_PERMUTATIONS,
                seed=7,
            )
        by_field = {item["field"]: item for item in results}
        self.assertEqual(results[0]["field"], "broadband_metric")
        self.assertNotIn("SVI_score", by_field)
        signal = by_field["broadband_metric"]
        self.assertGreater(signal["signed_delta"], 0.45)
        self.assertTrue(signal["bootstrap_excludes_zero"])
        self.assertLessEqual(signal["permutation_p"], 0.02)
        self.assertLessEqual(signal["fdr_q"], 0.05)
        self.assertEqual(signal["threshold_stability"]["sign_agreement"], 1.0)
        self.assertEqual(signal["county_jackknife"]["counties"], 2)
        self.assertTrue(signal["production_resampling_budget"])
        self.assertEqual(signal["screening_strength"], "strong")

    def test_results_are_deterministic_for_seed_and_include_missingness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores_path = root / "scores.csv"
            strata_path = root / "strata.csv"
            score_rows = []
            strata_rows = []
            for i in range(40):
                tract = geoid(i)
                score_rows.append({"GEOID": tract, "coverage_gap_score": i / 39})
                strata_rows.append(
                    {
                        "GEOID": tract,
                        "access_metric": "" if i % 10 == 0 else i,
                    }
                )
            self.write_scores(scores_path, score_rows)
            self.write_strata(strata_path, ["GEOID", "access_metric"], strata_rows)
            kwargs = dict(
                scores=load_scores(scores_path),
                strata_path=strata_path,
                min_rows=24,
                prefixes=(),
                bootstrap_iterations=80,
                permutations=99,
                seed=1234,
            )
            first = analyze(**kwargs)
            second = analyze(**kwargs)
        self.assertEqual(first, second)
        missingness = first[0]["missingness"]
        self.assertEqual(missingness["matched_rows"], 40)
        self.assertEqual(missingness["missing_or_non_numeric_rows"], 4)
        self.assertAlmostEqual(missingness["missing_rate"], 0.1)

    def test_duplicate_geoid_and_out_of_range_score_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate = root / "duplicate.csv"
            self.write_scores(
                duplicate,
                [
                    {"GEOID": geoid(1), "coverage_gap_score": 0.2},
                    {"GEOID": geoid(1), "coverage_gap_score": 0.3},
                ],
            )
            with self.assertRaisesRegex(ValueError, "duplicate GEOID"):
                load_scores(duplicate)

            out_of_range = root / "out.csv"
            self.write_scores(
                out_of_range,
                [{"GEOID": geoid(2), "coverage_gap_score": 1.01}],
            )
            with self.assertRaisesRegex(ValueError, r"outside \[0,1\]"):
                load_scores(out_of_range)

    def test_non_numeric_candidate_is_skipped_and_small_min_rows_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores_path = root / "scores.csv"
            strata_path = root / "strata.csv"
            self.write_scores(
                scores_path,
                [{"GEOID": geoid(i), "coverage_gap_score": i / 11} for i in range(12)],
            )
            self.write_strata(
                strata_path,
                ["GEOID", "category"],
                [{"GEOID": geoid(i), "category": "urban" if i % 2 else "rural"} for i in range(12)],
            )
            scores = load_scores(scores_path)
            self.assertEqual(
                analyze(
                    scores,
                    strata_path,
                    min_rows=8,
                    prefixes=(),
                    bootstrap_iterations=40,
                    permutations=40,
                ),
                [],
            )
            with self.assertRaisesRegex(ValueError, "min_rows"):
                analyze(
                    scores,
                    strata_path,
                    min_rows=4,
                    prefixes=(),
                    bootstrap_iterations=40,
                    permutations=40,
                )

    def test_evidence_packet_binds_inputs_and_cli_writes_versioned_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores_path = root / "components.csv"
            strata_path = root / "strata.csv"
            output_path = root / "evidence.json"
            rows = [{"GEOID": geoid(i), "coverage_gap_score": i / 31} for i in range(32)]
            strata = [{"GEOID": geoid(i), "broadband_metric": i} for i in range(32)]
            self.write_components(scores_path, rows)
            self.write_strata(strata_path, ["GEOID", "broadband_metric"], strata)
            code = main(
                [
                    str(scores_path),
                    str(strata_path),
                    str(output_path),
                    "--min-rows",
                    "16",
                    "--bootstrap-iterations",
                    "40",
                    "--permutations",
                    "40",
                    "--seed",
                    "9",
                ]
            )
            packet = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(packet["schema_version"], "bias-discovery-evidence/v2")
        self.assertEqual(packet["method"]["seed"], 9)
        self.assertEqual(len(packet["inputs"]["components_sha256"]), 64)
        self.assertEqual(len(packet["inputs"]["strata_sha256"]), 64)
        self.assertIn("not a causal", packet["claim_boundary"])
        self.assertTrue(packet["writeup_gate"])
        self.assertEqual(packet["candidates"][0]["field"], "broadband_metric")
        self.assertEqual(packet["method"]["excluded_prefixes"], list(DEFAULT_EXCLUDED_PREFIXES))
        self.assertEqual(packet["population"]["strata_missing_scores"], 0)
        self.assertEqual(packet["method"]["strong_gate"]["minimum_permutations"], MIN_STRONG_PERMUTATIONS)

    def test_county_jackknife_exposes_single_county_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores_path = root / "scores.csv"
            strata_path = root / "strata.csv"
            scores = []
            strata = []
            for i in range(60):
                county = "01001" if i < 30 else "01003"
                tract = geoid(i, county)
                value = i % 30
                # Opposing county relationships: pooled effect can exist, but jackknife reveals fragility.
                score = value / 29 if county == "01001" else 1.0 - (value / 29)
                scores.append({"GEOID": tract, "coverage_gap_score": score})
                strata.append({"GEOID": tract, "candidate": value})
            self.write_scores(scores_path, scores)
            self.write_strata(strata_path, ["GEOID", "candidate"], strata)
            result = analyze(
                load_scores(scores_path),
                strata_path,
                min_rows=40,
                prefixes=(),
                bootstrap_iterations=60,
                permutations=60,
                seed=11,
            )[0]
        jackknife = result["county_jackknife"]
        self.assertEqual(jackknife["evaluated"], 2)
        self.assertLess(jackknife["sign_agreement"], 1.0)
        self.assertEqual(result["screening_strength"], "exploratory")


    def test_duplicate_strata_geoid_fails_closed_and_tied_extremes_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores_path = root / "scores.csv"
            strata_path = root / "strata.csv"
            self.write_scores(
                scores_path,
                [{"GEOID": geoid(i), "coverage_gap_score": i / 11} for i in range(12)],
            )
            duplicated = [{"GEOID": geoid(i), "candidate": i} for i in range(12)]
            duplicated.append({"GEOID": geoid(1), "candidate": 99})
            self.write_strata(strata_path, ["GEOID", "candidate"], duplicated)
            with self.assertRaisesRegex(ValueError, "duplicate GEOID in strata CSV"):
                analyze(
                    load_scores(scores_path),
                    strata_path,
                    min_rows=8,
                    prefixes=(),
                    bootstrap_iterations=40,
                    permutations=40,
                )

            tied_path = root / "tied.csv"
            # Four distinct values satisfy the numeric-cardinality screen, but
            # repeated middle values make q1 == q3. The extreme groups would
            # overlap, so the candidate must be skipped rather than tested.
            tied = []
            values = [0] + [1] * 9 + [2, 3]
            for i, value in enumerate(values):
                tied.append({"GEOID": geoid(i), "candidate": value})
            self.write_strata(tied_path, ["GEOID", "candidate"], tied)
            self.assertEqual(
                analyze(
                    load_scores(scores_path),
                    tied_path,
                    min_rows=8,
                    prefixes=(),
                    bootstrap_iterations=40,
                    permutations=40,
                ),
                [],
            )



    def test_cli_requires_derived_component_schema_and_rejects_target_like_strata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores_path = root / "components.csv"
            strata_path = root / "strata.csv"
            output_path = root / "evidence.json"
            rows = [{"GEOID": geoid(i), "coverage_gap_score": i / 15} for i in range(16)]
            strata = [{"GEOID": geoid(i), "candidate": i} for i in range(16)]
            self.write_scores(scores_path, rows)
            self.write_strata(strata_path, ["GEOID", "candidate"], strata)
            with self.assertRaisesRegex(ValueError, "derived diagnostic columns"):
                main([str(scores_path), str(strata_path), str(output_path), "--min-rows", "8", "--bootstrap-iterations", "40", "--permutations", "40"])

            self.write_components(scores_path, rows)
            target_strata = [dict(row, organizer_coverage_gap=i / 20) for i, row in enumerate(strata)]
            self.write_strata(strata_path, ["GEOID", "candidate", "organizer_coverage_gap"], target_strata)
            with self.assertRaisesRegex(ValueError, "target-like coverage-gap field"):
                main([str(scores_path), str(strata_path), str(output_path), "--min-rows", "8", "--bootstrap-iterations", "40", "--permutations", "40"])


    def test_cli_rejects_invalid_or_missing_derived_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores_path = root / "components.csv"
            strata_path = root / "strata.csv"
            output_path = root / "evidence.json"
            rows = [{"GEOID": geoid(i), "coverage_gap_score": i / 15} for i in range(16)]
            strata = [{"GEOID": geoid(i), "candidate": i} for i in range(16)]
            self.write_strata(strata_path, ["GEOID", "candidate"], strata)

            bad = list(rows)
            bad[0] = {"GEOID": geoid(0), "coverage_gap_score": "NaN"}
            self.write_components(scores_path, bad)
            with self.assertRaisesRegex(ValueError, "missing or non-finite derived score"):
                main([str(scores_path), str(strata_path), str(output_path), "--min-rows", "8", "--bootstrap-iterations", "40", "--permutations", "40"])

            self.write_components(scores_path, rows[:-1])
            with self.assertRaisesRegex(ValueError, "missing 1 strata GEOIDs"):
                main([str(scores_path), str(strata_path), str(output_path), "--min-rows", "8", "--bootstrap-iterations", "40", "--permutations", "40"])

    def test_development_resampling_budget_cannot_be_strong(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores_path = root / "scores.csv"
            strata_path = root / "strata.csv"
            rows = [{"GEOID": geoid(i), "coverage_gap_score": i / 63} for i in range(64)]
            strata = [{"GEOID": geoid(i), "candidate": i} for i in range(64)]
            self.write_scores(scores_path, rows)
            self.write_strata(strata_path, ["GEOID", "candidate"], strata)
            result = analyze(load_scores(scores_path), strata_path, min_rows=32, prefixes=(), bootstrap_iterations=40, permutations=40, seed=5)[0]
        self.assertTrue(result["bootstrap_excludes_zero"])
        self.assertFalse(result["production_resampling_budget"])
        self.assertEqual(result["screening_strength"], "exploratory")



if __name__ == "__main__":
    unittest.main()
