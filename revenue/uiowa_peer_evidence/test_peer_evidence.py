"""Reproducible synthetic regression tests; no network or private data."""
import copy
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import peer_evidence as pe

HERE = Path(__file__).resolve().parent


def fixture():
    return pe.loads((HERE / "example.json").read_bytes())


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.packet = fixture()
        self.packet["comparisons"] = [["M1", "M2"]]

    def report(self):
        return pe.compile_packet(self.packet)

    def pair(self):
        return self.report()["comparisons"][0]

    def reject(self, packet=None):
        with self.assertRaises(pe.InputError):
            pe.compile_packet(self.packet if packet is None else packet)

    def test_full_rehearsal_has_expected_six_comparisons(self):
        report = pe.compile_packet(fixture())
        self.assertEqual(Counter(c["status"] for c in report["comparisons"]), {
            "ALIGNED_METADATA_REVIEW_REQUIRED": 1, "NEEDS_CONTEXT": 2, "CONTEXT_DIFFERS": 3})
        self.assertEqual(len(report["metric_context"]), 4)
        self.assertEqual(len(report["warnings"]), 2)

    def test_aligned_metadata_is_not_a_benchmark_or_finding(self):
        report = self.report()
        self.assertEqual(self.pair()["status"], "ALIGNED_METADATA_REVIEW_REQUIRED")
        self.assertEqual(report["source_verification"], "NOT_PERFORMED")
        self.assertEqual(report["report_kind"], "PEER_CONTEXT_NOT_LOCAL_ASSESSMENT")
        self.assertEqual(report["mode"], "SYNTHETIC_REHEARSAL")
        for key in ("score", "ranking", "maturity", "percentile", "approval"):
            self.assertNotIn(key, report)

    def test_unknown_denominator_preserved(self):
        self.packet["metrics"][1]["denominator_count"] = None
        pair = self.pair()
        self.assertEqual(pair["status"], "NEEDS_CONTEXT")
        self.assertIn("M2.denominator_count", pair["missing"])
        self.assertIsNone(self.report()["metrics"][1]["denominator_count"])

    def test_zero_is_not_unknown_and_is_not_usable_denominator(self):
        self.packet["metrics"][1]["denominator_count"] = 0
        pair = self.pair()
        self.assertEqual(pair["status"], "NEEDS_CONTEXT")
        self.assertNotIn("M2.denominator_count", pair["missing"])
        self.assertIn("M2: zero denominator", pair["notes"])

    def test_unpaired_metric_context_is_not_lost(self):
        self.packet["comparisons"] = []
        report = self.report()
        self.assertEqual(report["comparisons"], [])
        context = {c["metric_id"]: c for c in report["metric_context"]}
        self.assertEqual(context["M3"]["status"], "NEEDS_CONTEXT")
        self.assertIn("denominator_count", context["M3"]["missing"])
        self.assertIn("not a measured outcome", " ".join(context["M4"]["notes"]))

    def test_each_semantic_dimension_can_differ(self):
        fields = ("definition", "unit", "statistic", "population", "collection_method",
                  "numerator_definition", "denominator_definition")
        for field in fields:
            with self.subTest(field=field):
                self.packet = fixture()
                self.packet["comparisons"] = [["M1", "M2"]]
                self.packet["metrics"][1][field] = "Different explicitly declared context"
                pair = self.pair()
                self.assertEqual(pair["status"], "CONTEXT_DIFFERS")
                self.assertIn(field, pair["different"])

    def test_period_difference_is_not_silently_annualized(self):
        self.packet["metrics"][1]["period_start"] = "2026-07-01"
        self.packet["metrics"][1]["period_end"] = "2026-07-31"
        self.assertEqual(self.pair()["different"], ["period_end", "period_start"])
        self.assertEqual(self.report()["metrics"][1]["value"], "0.12")

    def test_missing_and_different_both_survive(self):
        self.packet["metrics"][1]["unit"] = "percent"
        self.packet["metrics"][1]["sample_size"] = None
        pair = self.pair()
        self.assertEqual(pair["status"], "CONTEXT_DIFFERS")
        self.assertIn("unit", pair["different"])
        self.assertIn("M2.sample_size", pair["missing"])

    def test_empty_exclusions_and_unknown_exclusions_differ(self):
        for metric in self.packet["metrics"][:2]:
            metric["exclusions"] = []
        self.assertEqual(self.pair()["status"], "ALIGNED_METADATA_REVIEW_REQUIRED")
        self.packet["metrics"][1]["exclusions"] = None
        self.assertEqual(self.pair()["status"], "NEEDS_CONTEXT")
        self.assertIn("M2.exclusions", self.pair()["missing"])

    def test_sample_size_difference_retains_precision_advisory(self):
        self.packet["metrics"][1]["sample_size"] = 500
        pair = self.pair()
        self.assertEqual(pair["status"], "ALIGNED_METADATA_REVIEW_REQUIRED")
        self.assertIn("sample sizes differ", " ".join(pair["notes"]))

    def test_zero_sample_needs_context(self):
        self.packet["metrics"][1]["sample_size"] = 0
        self.assertEqual(self.pair()["status"], "NEEDS_CONTEXT")
        self.assertIn("M2: zero observed sample", self.pair()["notes"])

    def test_nonmeasurement_evidence_never_becomes_outcome(self):
        for kind in ("policy", "reported_practice", "framework", "proposal"):
            with self.subTest(kind=kind):
                self.packet["records"][1]["evidence_kind"] = kind
                self.assertEqual(self.pair()["status"], "NEEDS_CONTEXT")
                self.assertIn("M2: supporting record is not a measured outcome", self.pair()["notes"])

    def test_rate_requires_denominator_metadata(self):
        for metric in self.packet["metrics"][:2]:
            metric["kind"] = "rate"
        self.packet["metrics"][1]["denominator_definition"] = None
        self.assertIn("M2.denominator_definition", self.pair()["missing"])

    def test_nonratio_metric_does_not_require_denominator(self):
        for kind in ("count", "gauge", "duration"):
            with self.subTest(kind=kind):
                for metric in self.packet["metrics"][:2]:
                    metric.update(kind=kind, numerator_definition=None,
                                  denominator_definition=None, denominator_count=None)
                self.assertEqual(self.pair()["status"], "ALIGNED_METADATA_REVIEW_REQUIRED")

    def test_explicit_pair_reports_different_metric_keys_and_kinds(self):
        self.packet["metrics"][1].update(metric_key="other", kind="count")
        self.assertIn("metric_key", self.pair()["different"])
        self.assertIn("kind", self.pair()["different"])

    def test_automatic_pairing_never_crosses_metric_key(self):
        del self.packet["comparisons"]
        self.packet["metrics"][0]["metric_key"] = "unique"
        self.assertEqual(len(self.report()["comparisons"]), 3)
        self.assertTrue(all("M1" not in (r["left"], r["right"]) for r in self.report()["comparisons"]))

    def test_order_independent_digest_and_bundle(self):
        original = fixture()
        for metric in original["metrics"]:
            metric["exclusions"] = ["A", "B"]
            metric["source_refs"].append({"source_id": "S1", "locator": "Synthetic supplementary table"})
        original["comparisons"] = [["M1", "M2"], ["M3", "M4"]]
        reordered = copy.deepcopy(original)
        for name in ("sources", "records", "metrics", "comparisons"):
            reordered[name].reverse()
        for row in reordered["records"]:
            row["assessment_areas"].reverse()
        for row in reordered["metrics"]:
            row["exclusions"].reverse()
            row["source_refs"].reverse()
        for pair in reordered["comparisons"]:
            pair.reverse()
        self.assertEqual(pe.bundle(pe.compile_packet(original)), pe.bundle(pe.compile_packet(reordered)))

    def test_compile_does_not_mutate_or_alias_input(self):
        original = copy.deepcopy(self.packet)
        report = self.report()
        self.assertEqual(self.packet, original)
        report["sources"][0]["title"] = "changed returned report"
        self.assertEqual(self.packet, original)

    def test_semantic_change_changes_input_digest(self):
        before = self.report()["input_sha256"]
        self.packet["metrics"][0]["source_refs"][0]["locator"] = "Synthetic corrected table"
        self.assertNotEqual(before, self.report()["input_sha256"])

    def test_unknown_and_future_source_dates_are_explicit(self):
        self.packet["sources"][0]["published_on"] = "2026-09-20"
        self.assertIn("publication date follows access date", " ".join(self.report()["warnings"]))
        self.packet["sources"][0]["accessed_on"] = "2026-09-20"
        self.reject()

    def test_future_or_reversed_measurement_period_is_rejected(self):
        for start, end in (("2026-08-31", "2026-08-01"), ("2026-09-20", None),
                           (None, "2026-09-20"), ("2026-02-30", "2026-08-31")):
            with self.subTest(start=start, end=end):
                self.packet["metrics"][0].update(period_start=start, period_end=end)
                self.reject()

    def test_partial_unknown_period_is_preserved(self):
        self.packet["metrics"][0]["period_start"] = None
        self.assertIn("M1.period_start", self.pair()["missing"])
        self.assertIn("UNKNOWN / 2026-08-31", pe.render_markdown(self.report()))

    def test_duplicate_entity_ids_rejected(self):
        for name in ("sources", "records", "metrics"):
            with self.subTest(name=name):
                packet = fixture()
                packet[name].append(copy.deepcopy(packet[name][0]))
                self.reject(packet)

    def test_metric_direct_source_references_required_and_resolved(self):
        bad_refs = ([], [{"source_id": "absent", "locator": "Table 1"}],
                    [{"source_id": "S1", "locator": ""}],
                    [{"source_id": "S1", "locator": "Table 1"}] * 2)
        for refs in bad_refs:
            with self.subTest(refs=refs):
                self.packet["metrics"][0]["source_refs"] = refs
                self.reject()

    def test_unknown_record_reference_rejected(self):
        self.packet["metrics"][0]["record_id"] = "missing"
        self.reject()

    def test_required_and_unknown_keys_rejected(self):
        for mutation in ("missing", "extra"):
            with self.subTest(mutation=mutation):
                packet = fixture()
                if mutation == "missing":
                    del packet["metrics"][0]["sample_size"]
                else:
                    packet["assessment_score"] = 5
                self.reject(packet)

    def test_boolean_and_noninteger_counts_rejected(self):
        for value in (True, False, -1, 0.5, "10", 10**12 + 1):
            with self.subTest(value=value):
                self.packet["metrics"][0]["sample_size"] = value
                self.reject()

    def test_decimal_values_are_preserved_not_coerced(self):
        for value in ("0", "-2.300", "0.000000000000000001", None):
            with self.subTest(value=value):
                self.packet["metrics"][0]["value"] = value
                self.assertEqual(self.report()["metrics"][0]["value"], value)
        for value in (True, 1.2, "NaN", "Infinity", "1e9", "01", ".1", " 1 ", "1" * 65):
            with self.subTest(value=value):
                self.packet["metrics"][0]["value"] = value
                self.reject()

    def test_invalid_identifiers_areas_and_text_rejected(self):
        for value in ("", "has spaces", "x" * 81, None, 3):
            packet = fixture()
            packet["records"][0]["id"] = value
            self.reject(packet)
        for areas in ([], ["security", "security"], ["other"], [True]):
            packet = fixture()
            packet["records"][0]["assessment_areas"] = areas
            self.reject(packet)
        for value in ("", "\x00", "\ud800", "x" * 8001):
            packet = fixture()
            packet["records"][0]["statement"] = value
            self.reject(packet)

    def test_url_is_metadata_only_but_must_be_well_formed(self):
        for url in ("javascript:alert(1)", "https://user:pass@example.org/x",
                    "https:///x", "https://example.org:invalid/x", "https://example.org/a b"):
            with self.subTest(url=url):
                self.packet["sources"][0]["url"] = url
                self.reject()

    def test_invalid_comparison_requests_rejected(self):
        for pairs in ([["M1"]], [["M1", "M1"]], [["M1", "missing"]],
                      [["M1", "M2"], ["M2", "M1"]], None):
            with self.subTest(pairs=pairs):
                self.packet["comparisons"] = pairs
                self.reject()

    def test_pair_bound_can_be_resolved_by_explicit_selection(self):
        self.packet["metrics"] = [dict(copy.deepcopy(self.packet["metrics"][0]), id=f"X{i}") for i in range(65)]
        del self.packet["comparisons"]
        self.reject()
        self.packet["comparisons"] = [["X0", "X64"]]
        self.assertEqual(len(self.report()["comparisons"]), 1)

    def test_collection_and_pair_limits_rejected(self):
        self.packet["metrics"] = [dict(copy.deepcopy(self.packet["metrics"][0]), id=f"X{i}") for i in range(501)]
        self.reject()
        self.packet = fixture()
        self.packet["comparisons"] = [["M1", "M2"]] * 2001
        self.reject()

    def test_empty_research_packet_has_no_inferred_success(self):
        self.packet.update(sources=[], records=[], metrics=[], comparisons=[])
        report = self.report()
        self.assertEqual(report["metric_context"], [])
        self.assertTrue(all(value == {} for value in report["coverage"].values()))
        self.assertIn("does not establish comparability", pe.render_markdown(report))

    def test_public_mode_is_still_unverified_context(self):
        self.packet["mode"] = "PUBLIC_SOURCE_RESEARCH"
        report = self.report()
        self.assertEqual(report["source_verification"], "NOT_PERFORMED")
        self.assertIn("not a local assessment", pe.render_markdown(report))


class IngressAndExportTests(unittest.TestCase):
    def test_strict_json_rejects_duplicates_nonfinite_invalid_utf8(self):
        for raw in (b'{"x": 1, "x": 2}', b'{"x": NaN}', b'{"x": Infinity}',
                    b'\xff', b'{', b'[' * 1500, b' ' * (pe.MAX_BYTES + 1)):
            with self.subTest(prefix=raw[:30]):
                with self.assertRaises(pe.InputError):
                    pe.loads(raw)

    def test_csv_exports_references_and_preserves_unknowns(self):
        report = pe.compile_packet(fixture())
        output = pe.bundle(report)
        rows = list(csv.DictReader(io.StringIO(output["metrics.csv"])))
        self.assertEqual(rows[2]["denominator_count"], "")
        self.assertEqual(rows[2]["value"], "0.20")
        self.assertEqual(json.loads(rows[0]["source_refs"]), report["metrics"][0]["source_refs"])
        self.assertEqual(len(output), 7)

    def test_csv_cells_are_text_safe_without_changing_json(self):
        packet = fixture()
        packet["records"][0]["statement"] = "\t=1+1"
        report = pe.compile_packet(packet)
        output = pe.bundle(report)
        rows = list(csv.DictReader(io.StringIO(output["records.csv"])))
        self.assertEqual(rows[0]["statement"], "'\t=1+1")
        self.assertEqual(report["records"][0]["statement"], "\t=1+1")
        for value in ("+SUM(A1)", "-4", "@value", "\n=cmd"):
            data = pe.csv_text([{"field": value}], ["field"])
            self.assertTrue(list(csv.DictReader(io.StringIO(data)))[0]["field"].startswith("'"))

    def test_csv_newlines_quotes_and_commas_round_trip(self):
        value = 'quoted "text", on\ntwo lines'
        data = pe.csv_text([{"field": value}], ["field"])
        self.assertEqual(list(csv.DictReader(io.StringIO(data)))[0]["field"], value)

    def test_markdown_escapes_researcher_markup(self):
        packet = fixture()
        packet["records"][0]["statement"] = '<script>x</script> ![x](https://example.org) | injected\n# heading'
        rendered = pe.render_markdown(pe.compile_packet(packet))
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("![x]", rendered)
        self.assertNotIn("| injected", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_policy_note_is_visible_in_markdown_with_no_pairs(self):
        packet = fixture()
        packet["comparisons"] = []
        rendered = pe.render_markdown(pe.compile_packet(packet))
        self.assertIn("supporting record is not a measured outcome", rendered)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / "peer_evidence.py"), *map(str, args)],
                              capture_output=True, text=True, timeout=15)

    def test_cli_stdout_json(self):
        result = self.run_cli(HERE / "example.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), pe.compile_packet(fixture()))

    def test_cli_new_output_directory_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "output"
            result = self.run_cli(HERE / "example.json", "--out", out)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(pe.bundle(pe.compile_packet(fixture()))))
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            result = self.run_cli(HERE / "example.json", "--out", out)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_cli_invalid_packet_writes_no_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bad.json"
            source.write_text('{"x": 1, "x": 2}')
            out = Path(folder) / "output"
            result = self.run_cli(source, "--out", out)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(out.exists())
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)

    def test_cli_missing_file_and_oversized_input(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            result = self.run_cli(source)
            self.assertEqual(result.returncode, 2)
            source.write_bytes(b" " * (pe.MAX_BYTES + 1))
            result = self.run_cli(source)
            self.assertEqual(result.returncode, 2)
            self.assertIn("4 MB", result.stderr)


if __name__ == "__main__":
    unittest.main()
