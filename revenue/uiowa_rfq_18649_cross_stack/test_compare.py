"""Executable semantics, malformed-input and operator-flow regression tests."""
import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

if __package__:
    from . import compare, examples
else:
    import compare
    import examples


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.packet, self.passages = examples.make_packet()

    def report(self, number=0):
        return compare.analyze(self.packet)["pairs"][number]

    def practice(self, ident):
        return next(p for p in self.packet["practices"] if p["id"] == ident)

    def evidence(self, ident):
        return next(e for e in self.packet["evidence"] if e["id"] == ident)

    def test_twelve_hand_worked_verdicts(self):
        expected = ["EQUIVALENT_OUTCOME_IN_SUPPLIED_SAMPLE", "EQUIVALENT_OUTCOME_IN_SUPPLIED_SAMPLE",
                    "CONTEXT_NOT_COMPARABLE", "INSUFFICIENT_EVIDENCE", "EQUIVALENT_OUTCOME_IN_SUPPLIED_SAMPLE",
                    "SHARED_GAP_IN_SUPPLIED_SAMPLE", "INSUFFICIENT_EVIDENCE", "DISPUTED",
                    "DIFFERENT_OUTCOME_DEFINITIONS", "NOT_APPLICABLE", "CONTEXT_UNRESOLVED",
                    "EQUIVALENT_OUTCOME_IN_SUPPLIED_SAMPLE"]
        self.assertEqual([r["verdict"] for r in compare.analyze(self.packet)["pairs"]], expected)
        self.assertEqual({p["area"] for p in self.packet["practices"]}, set(compare.AREAS))

    def test_implementation_permutation_never_changes_verdict(self):
        original = self.report()["verdict"]
        for left in ("manual", "automated", "shared-service", "hybrid"):
            for right in ("manual", "automated", "shared-service", "hybrid"):
                self.practice("dev-manual")["implementation"] = left
                self.practice("dev-automated")["implementation"] = right
                self.assertEqual(self.report()["verdict"], original)

    def test_shared_observation_is_one_provenance_cluster_not_two(self):
        row = self.report(1)
        self.assertEqual(row["distinct_provenance_clusters"], 1)
        self.assertEqual(row["shared_provenance_clusters"], ["shared-lifecycle-exercise-1"])
        self.assertEqual(len(row["citations"]), 1)

    def test_distinct_evidence_ids_can_share_one_provenance_cluster(self):
        self.evidence("E02")["independence_key"] = "E01"
        self.assertEqual(self.report()["distinct_provenance_clusters"], 1)

    def test_unknown_context_cannot_be_overridden(self):
        self.practice("dev-manual")["context"]["workload"] = None
        self.packet["pairs"][0]["context_decisions"] = [dict(dimension="workload", decision="aligned_for_outcome", rationale="Proposed match", evidence_ids=["E01"])]
        row = self.report()
        self.assertEqual(row["verdict"], "CONTEXT_UNRESOLVED")
        self.assertIn("workload", " ".join(row["follow_up"]))

    def test_matching_context_labels_do_not_erase_explicit_dissent(self):
        self.packet["pairs"][0]["context_decisions"] = [dict(dimension="workload", decision="material_difference", rationale="The same label hides distinct workload bounds", evidence_ids=[])]
        self.assertEqual(self.report()["verdict"], "CONTEXT_NOT_COMPARABLE")

    def test_adjustment_needs_current_source_not_just_rationale(self):
        self.packet["pairs"][4]["context_decisions"][0]["evidence_ids"] = []
        self.assertEqual(self.report(4)["verdict"], "CONTEXT_UNRESOLVED")

    def test_interview_alone_does_not_establish_context_adjustment(self):
        self.evidence("E08")["kind"] = "interview"
        self.assertEqual(self.report(4)["verdict"], "CONTEXT_UNRESOLVED")

    def test_policy_alone_does_not_establish_operating_outcome(self):
        row = self.report(3)
        self.assertEqual(row["left_support"]["state"], "INSUFFICIENT_DIRECT_EVIDENCE")
        self.assertEqual(row["right_support"]["state"], "SUPPORTED_MEETS")

    def test_old_and_future_evidence_not_current(self):
        for start, end in (("2025-01-01", "2025-12-31"), ("2026-10-01", "2026-12-31")):
            self.evidence("E01").update(observed_on=start, valid_through=end)
            row = self.report()
            self.assertEqual(row["verdict"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(row["left_support"]["inactive_evidence"], ["E01"])

    def test_stale_dissent_is_not_silently_resolved(self):
        self.evidence("E10").update(observed_on="2025-01-01", valid_through="2025-12-31")
        row = self.report(7)
        self.assertEqual(row["verdict"], "DISPUTED")
        self.assertEqual(row["left_support"]["dissent_ids"], ["E10"])

    def test_unknown_claim_not_promoted_by_attached_evidence(self):
        self.practice("dev-manual")["claim"] = "unknown"
        self.assertEqual(self.report()["left_support"]["state"], "UNKNOWN")

    def test_absent_evidence_cannot_establish_gap(self):
        self.practice("dev-manual").update(claim="does_not_meet", evidence_ids=[])
        self.assertEqual(self.report()["verdict"], "INSUFFICIENT_EVIDENCE")

    def test_supported_difference_is_not_an_ordinal_rating(self):
        self.practice("dev-manual")["claim"] = "does_not_meet"
        self.assertEqual(self.report()["verdict"], "DIFFERENT_OUTCOMES_IN_SUPPLIED_SAMPLE")
        self.assertNotIn("score", self.report())

    def test_na_requires_rationale(self):
        del self.practice("security-na")["applicability_reason"]
        with self.assertRaises(compare.InputError):
            compare.analyze(self.packet)

    def test_outcome_version_and_criterion_must_match(self):
        for key, value in (("version", "v99"), ("criterion", "A different outcome")):
            self.packet, _ = examples.make_packet()
            self.practice("dev-manual")["outcome"][key] = value
            self.assertEqual(self.report()["verdict"], "DIFFERENT_OUTCOME_DEFINITIONS")

    def test_exact_fraction_and_unequal_denominator_sizes(self):
        self.practice("dev-manual")["measurement"].update(numerator=1, denominator=3)
        self.practice("dev-automated")["measurement"].update(numerator=1, denominator=6)
        r = self.report()["measurement"]
        self.assertEqual(r["delta_fraction"], "1/6")
        self.assertEqual(r["left"]["denominator"], 3)
        self.assertEqual(r["right"]["denominator"], 6)

    def test_zero_denominator_is_not_zero_rate(self):
        self.practice("dev-manual")["measurement"].update(numerator=0, denominator=0)
        r = self.report()["measurement"]
        self.assertEqual(r["state"], "NO_OBSERVED_OPPORTUNITIES")
        self.assertIsNone(r["delta_fraction"])

    def test_missing_counts_are_not_zero(self):
        self.practice("dev-manual")["measurement"]["numerator"] = None
        r = self.report()["measurement"]
        self.assertEqual(r["state"], "MISSING_COUNTS")
        self.assertIsNone(r["delta_fraction"])

    def test_different_population_blocks_rate_delta(self):
        self.practice("dev-manual")["measurement"]["population"] = "urgent changes only"
        self.assertEqual(self.report()["measurement"]["state"], "INCOMPARABLE_MEASUREMENTS")

    def test_different_period_blocks_rate_not_qualitative_outcome(self):
        r = self.report(11)
        self.assertEqual(r["verdict"], "EQUIVALENT_OUTCOME_IN_SUPPLIED_SAMPLE")
        self.assertEqual(r["measurement"]["state"], "INCOMPARABLE_MEASUREMENTS")
        self.assertIsNone(r["measurement"]["delta_fraction"])

    def test_invalid_count_types_and_ranges(self):
        for value in (True, -1, 0.5, "1", [], float("nan")):
            with self.subTest(value=value):
                self.practice("dev-manual")["measurement"]["numerator"] = value
                with self.assertRaises(compare.InputError):
                    compare.analyze(self.packet)

    def test_numerator_cannot_exceed_denominator(self):
        self.practice("dev-manual")["measurement"]["numerator"] = 5
        with self.assertRaises(compare.InputError):
            compare.analyze(self.packet)

    def test_invalid_or_reversed_dates(self):
        for value in ("2026-02-30", "20260901", 20260901):
            self.evidence("E01")["observed_on"] = value
            with self.assertRaises(compare.InputError):
                compare.analyze(self.packet)
        self.evidence("E01")["observed_on"] = "2026-10-01"
        with self.assertRaises(compare.InputError):
            compare.analyze(self.packet)

    def test_duplicate_ids_and_unknown_fields(self):
        self.packet["evidence"].append(copy.deepcopy(self.packet["evidence"][0]))
        with self.assertRaises(compare.InputError):
            compare.analyze(self.packet)
        self.packet, _ = examples.make_packet()
        self.practice("dev-manual")["cliam"] = "meets"
        with self.assertRaises(compare.InputError):
            compare.analyze(self.packet)

    def test_broken_and_repeated_references(self):
        for refs in (["missing"], ["E01", "E01"]):
            self.practice("dev-manual")["evidence_ids"] = refs
            with self.assertRaises(compare.InputError):
                compare.analyze(self.packet)

    def test_bad_pair_reference_types(self):
        self.packet["pairs"][0]["left"] = []
        with self.assertRaises(compare.InputError):
            compare.analyze(self.packet)

    def test_same_evidence_cannot_support_and_dissent(self):
        self.practice("dev-manual")["dissent_ids"] = ["E01"]
        with self.assertRaises(compare.InputError):
            compare.analyze(self.packet)

    def test_input_not_mutated_and_output_is_a_detached_snapshot(self):
        before = copy.deepcopy(self.packet)
        result = compare.analyze(self.packet)
        self.assertEqual(self.packet, before)
        result["pairs"][0]["left"]["context"]["workload"] = "modified"
        self.assertEqual(self.packet, before)

    def test_json_roundtrip_and_determinism(self):
        first = compare.analyze(self.packet)
        self.assertEqual(first, compare.analyze(json.loads(json.dumps(self.packet))))
        self.assertEqual(compare.comparison_csv(first), compare.comparison_csv(compare.analyze(self.packet)))
        self.assertEqual(compare.markdown(first), compare.markdown(compare.analyze(self.packet)))

    def test_digest_changes_with_source_locator(self):
        before = compare.analyze(self.packet)["input_sha256"]
        self.evidence("E01")["locator"] = "#different"
        self.assertNotEqual(before, compare.analyze(self.packet)["input_sha256"])

    def test_duplicate_json_keys_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            for value in ('{"synthetic": true, "synthetic": false}', '{"value": NaN}'):
                path.write_text(value)
                with self.assertRaises(compare.InputError):
                    compare.load(path)

    def test_synthetic_label_and_as_of_survive_csv_export(self):
        rows = list(csv.DictReader(io.StringIO(compare.comparison_csv(compare.analyze(self.packet)))))
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(row["synthetic"] == "True" for row in rows))
        self.assertTrue(all(row["as_of"] == "2026-09-19" for row in rows))

    def test_csv_formula_like_labels_are_literal(self):
        self.packet["pairs"][0]["id"] = "=1+1"
        csv_text = compare.comparison_csv(compare.analyze(self.packet))
        row = next(r for r in csv.DictReader(io.StringIO(csv_text)) if r["pair_id"].startswith("'="))
        self.assertEqual(row["pair_id"], "'=1+1")
        self.assertEqual(compare.spreadsheet_text(" \t@SUM(1)"), "' \t@SUM(1)")

    def test_markdown_preserves_data_without_active_image_or_html(self):
        self.practice("dev-manual")["basis"] = '<script>bad</script> ![tracking](https://example.invalid/pixel) | note\nnext'
        rendered = compare.markdown(compare.analyze(self.packet))
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("![tracking]", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("\\| note<br>next", rendered)

    def test_fixture_locator_targets_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example"
            examples.write_example(path)
            source = (path / "synthetic-evidence.md").read_text()
            for evidence in self.packet["evidence"]:
                self.assertIn("## " + evidence["id"] + "\n", source)
                self.assertEqual(evidence["locator"], "#" + evidence["id"].lower())
            with (path / "context-worksheet.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 48)
            self.assertTrue(all(row["synthetic"] == "True" for row in rows))
            with self.assertRaises(FileExistsError):
                examples.write_example(path)

    def test_real_cli_three_formats_and_no_output_on_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example"
            expected = examples.write_example(path)
            for format_, name in (("json", "comparison.json"), ("csv", "comparison.csv"), ("markdown", "comparison.md")):
                command = [sys.executable, str(Path(compare.__file__)), str(path / "synthetic.json"), "--format", format_]
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, (path / name).read_text())
            (path / "bad.json").write_text('{"schema": "wrong"}')
            result = subprocess.run([sys.executable, str(Path(compare.__file__)), str(path / "bad.json")], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("Invalid input:", result.stderr)
            self.assertTrue(expected["synthetic"])


if __name__ == "__main__":
    unittest.main()
