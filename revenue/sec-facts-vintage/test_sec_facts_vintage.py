"""Executable contract and regression tests; synthetic data only."""
from __future__ import annotations
import copy
import csv
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import sec_facts_vintage as v

HERE = Path(__file__).resolve().parent


def observation(value=100, filed="2024-05-01", accession="0000123456-24-000001", **extra):
    row = {"start": "2024-01-01", "end": "2024-03-31", "val": value,
           "accn": accession, "fy": 2024, "fp": "Q1", "form": "10-Q", "filed": filed,
           "frame": "CY2024Q1"}
    row.update(extra)
    return row


def source(rows=None):
    return {"cik": 123456, "entityName": "SYNTHETIC EXAMPLE — NOT A REAL ISSUER",
            "facts": {"us-gaap": {"Revenue": {"label": "Synthetic revenue", "description": "Synthetic test only",
                                             "units": {"USD": rows if rows is not None else [observation()]}}}}}


def plan():
    return {"schema": "sec-facts-vintage-plan/v1", "cik": "0000123456", "filed_on_or_before": "2024-12-31",
            "forms": ["10-Q", "10-Q/A", "10-K", "10-K/A"],
            "queries": [{"id": "revenue-q1", "taxonomy": "us-gaap", "concept": "Revenue", "unit": "USD",
                         "start": "2024-01-01", "end": "2024-03-31"}]}


def dump(obj):
    return json.dumps(obj, ensure_ascii=False).encode()


class SelectionTests(unittest.TestCase):
    def result(self, rows=None, p=None, s=None):
        return v.compile_report(dump(source(rows) if s is None else s), dump(plan() if p is None else p))["results"][0]

    def test_single_vintage(self):
        r = self.result()
        self.assertEqual((r["status"], r["first_value"], r["latest_value"], r["change"]),
                         ("SINGLE_VINTAGE", "100", "100", "0"))

    def test_changed_value_keeps_both_accessions(self):
        r = self.result([observation(), observation(115, "2024-08-01", "0000123456-24-000002")])
        self.assertEqual((r["status"], r["change"]), ("CHANGED", "15"))
        self.assertEqual(len(r["vintages"]), 2)
        self.assertEqual(r["vintages"][0]["observations"][0]["accession"], "0000123456-24-000001")

    def test_unchanged_repeated_filing(self):
        r = self.result([observation(), observation(100, "2024-08-01", "0000123456-24-000002")])
        self.assertEqual(r["status"], "UNCHANGED")

    def test_amendment_is_explicit_form(self):
        rows = [observation(), observation(90, "2024-06-01", "0000123456-24-000002", form="10-Q/A")]
        self.assertEqual(self.result(rows)["latest_value"], "90")
        p = plan(); p["forms"] = ["10-Q"]
        self.assertEqual(self.result(rows, p)["latest_value"], "100")

    def test_cutoff_is_inclusive(self):
        p = plan(); p["filed_on_or_before"] = "2024-05-01"
        self.assertEqual(self.result(p=p)["latest_value"], "100")
        p["filed_on_or_before"] = "2024-04-30"
        self.assertEqual(self.result(p=p)["status"], "NO_ELIGIBLE_FACT")

    def test_later_values_do_not_enter_earlier_query_output(self):
        p = plan(); p["filed_on_or_before"] = "2024-06-01"
        self.assertEqual(self.result(p=p), self.result([observation(), observation(999, "2024-08-01", "0000123456-24-000009")], p))

    def test_fy_fp_frame_are_not_period_selectors(self):
        # Both rows report FY/Q1 labels but the YTD and exact quarter differ.
        wrong = observation(900, start="2023-10-01", fy=2024, fp="Q1", frame="CY2024Q1")
        right = observation(100, fy=2025, fp="FY", frame="CY2025")
        self.assertEqual(self.result([wrong, right])["latest_value"], "100")

    def test_non_calendar_period(self):
        p = plan(); p["queries"][0].update(start="2023-12-31", end="2024-03-30")
        self.assertEqual(self.result([observation(start="2023-12-31", end="2024-03-30")], p)["latest_value"], "100")

    def test_instant_is_not_one_day_duration(self):
        instant = observation(); del instant["start"]
        p = plan(); p["queries"][0]["start"] = None
        self.assertEqual(self.result([instant, observation(999, start="2024-03-31")], p)["latest_value"], "100")

    def test_exact_unit_no_conversion(self):
        p = plan(); p["queries"][0]["unit"] = "CAD"
        r = self.result(p=p)
        self.assertEqual((r["absence_reason"], r["latest_value"]), ("UNIT_ABSENT", None))

    def test_taxonomy_no_fallback(self):
        p = plan(); p["queries"][0]["taxonomy"] = "ifrs-full"
        self.assertEqual(self.result(p=p)["absence_reason"], "TAXONOMY_ABSENT")

    def test_concept_no_name_guess(self):
        p = plan(); p["queries"][0]["concept"] = "Revenues"
        self.assertEqual(self.result(p=p)["absence_reason"], "CONCEPT_ABSENT")

    def test_missing_is_not_zero(self):
        r = self.result([])
        self.assertIsNone(r["first_value"])
        self.assertIsNone(r["latest_value"])
        self.assertIsNone(r["change"])

    def test_zero_is_observed_value(self):
        self.assertEqual(self.result([observation(0)])["latest_value"], "0")

    def test_same_date_different_values_is_ambiguous(self):
        r = self.result([observation(), observation(101, accession="0000123456-24-999999")])
        self.assertEqual(r["status"], "AMBIGUOUS_LATEST")
        self.assertIsNone(r["latest_value"])
        self.assertIsNone(r["change"])

    def test_same_date_equal_values_retains_multiple_sources(self):
        r = self.result([observation(), observation(accession="0000123456-24-000002")])
        self.assertEqual((r["latest_value"], r["unique_observations"]), ("100", 2))

    def test_ambiguous_baseline_does_not_invent_change(self):
        r = self.result([observation(), observation(101, accession="0000123456-24-000002"),
                         observation(120, "2024-08-01", "0000123456-24-000003")])
        self.assertEqual((r["status"], r["latest_value"]), ("AMBIGUOUS_BASELINE", "120"))
        self.assertIsNone(r["first_value"])
        self.assertIsNone(r["change"])

    def test_same_accession_conflicting_values_holds(self):
        r = self.result([observation(), observation(101)])
        self.assertEqual(r["status"], "SOURCE_CONFLICT")
        self.assertIsNone(r["latest_value"])

    def test_same_accession_conflicting_filing_date_holds(self):
        self.assertEqual(self.result([observation(), observation(filed="2024-05-02")])["status"], "SOURCE_CONFLICT")

    def test_same_accession_conflicting_form_holds(self):
        self.assertEqual(self.result([observation(), observation(form="10-K")])["status"], "SOURCE_CONFLICT")

    def test_exact_replay_collapses(self):
        r = self.result([observation(), observation()])
        self.assertEqual((r["unique_observations"], r["exact_replays_collapsed"]), (1, 1))

    def test_metadata_variants_do_not_create_value_ambiguity(self):
        other = observation(); del other["frame"]
        r = self.result([observation(), other])
        self.assertEqual((r["latest_value"], r["unique_observations"]), ("100", 2))

    def test_pre_close_filing_held(self):
        r = self.result([observation(filed="2024-03-30")])
        self.assertEqual(r["status"], "SOURCE_CONFLICT")
        self.assertEqual(len(r["pre_period_close_accessions"]), 1)

    def test_order_invariance_of_selected_results(self):
        rows = [observation(), observation(105, "2024-08-01", "0000123456-24-000002"), observation()]
        self.assertEqual(self.result(rows), self.result(rows[::-1]))

    def test_numeric_sort_not_lexicographic(self):
        r = self.result([observation(9), observation(100, accession="0000123456-24-000002")])
        self.assertEqual(r["vintages"][0]["values"], ["9", "100"])

    def test_exact_fractional_and_large_value(self):
        raw = dump(source([observation(1), observation(2, "2024-08-01", "0000123456-24-000002")]))
        raw = raw.replace(b'"val": 1,', b'"val": 9007199254740993.123456789,').replace(b'"val": 2,', b'"val": 9007199254740993.123456790,')
        r = v.compile_report(raw, dump(plan()))["results"][0]
        self.assertEqual(r["latest_value"], "9007199254740993.12345679")
        self.assertEqual(r["change"], "0.000000001")

    def test_negative_difference(self):
        self.assertEqual(self.result([observation(100), observation(-30, "2024-08-01", "0000123456-24-000002")])["change"], "-130")

    def test_delta_can_have_more_digits_than_input(self):
        n = 10**96 - 1
        self.assertEqual(self.result([observation(-n), observation(n, "2024-08-01", "0000123456-24-000002")])["change"], str(2*n))

    def test_decimal_context_cannot_round_comparison(self):
        from decimal import localcontext
        rows = [observation(10**40), observation(10**40+1, "2024-08-01", "0000123456-24-000002")]
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(self.result(rows)["change"], "1")

    def test_explicit_temporal_and_origin_limits(self):
        r = v.compile_report(dump(source()), dump(plan()))
        self.assertEqual(r["temporal_basis"], "FILED_DATE_INCLUSIVE_NOT_INTRADAY_AVAILABILITY")
        self.assertEqual(r["evidence_basis"], "UNAUTHENTICATED_RETAINED_INPUT")


class ValidationTests(unittest.TestCase):
    def reject_plan(self, p):
        with self.assertRaises(v.InputError):
            v.compile_report(dump(source()), dump(p))

    def test_wrong_cik(self):
        p = plan(); p["cik"] = "0000000001"; self.reject_plan(p)

    def test_boolean_cik(self):
        p = plan(); p["cik"] = True; self.reject_plan(p)

    def test_integer_cik_normalized(self):
        p = plan(); p["cik"] = 123456
        self.assertEqual(v.compile_report(dump(source()), dump(p))["cik"], "0000123456")

    def test_zero_cik(self):
        p = plan(); p["cik"] = 0; self.reject_plan(p)

    def test_extra_plan_field(self):
        p = plan(); p["current"] = True; self.reject_plan(p)

    def test_extra_query_field(self):
        p = plan(); p["queries"][0]["fallback"] = "Revenues"; self.reject_plan(p)

    def test_missing_start_is_not_guessed(self):
        p = plan(); del p["queries"][0]["start"]; self.reject_plan(p)

    def test_invalid_cutoff_date(self):
        p = plan(); p["filed_on_or_before"] = "2024-02-30"; self.reject_plan(p)

    def test_date_format_not_locale_or_datetime(self):
        for value in ("2024-2-01", "02/01/2024", "2024-02-01T00:00:00Z", 20240201):
            with self.subTest(value=value):
                p = plan(); p["filed_on_or_before"] = value; self.reject_plan(p)

    def test_reversed_period(self):
        p = plan(); p["queries"][0]["start"] = "2024-04-01"; self.reject_plan(p)

    def test_duplicate_id(self):
        p = plan(); p["queries"].append(copy.deepcopy(p["queries"][0])); self.reject_plan(p)

    def test_duplicate_scope_relabel(self):
        p = plan(); other = copy.deepcopy(p["queries"][0]); other["id"] = "another"; p["queries"].append(other); self.reject_plan(p)

    def test_no_implicit_all_forms(self):
        p = plan(); p["forms"] = []; self.reject_plan(p)

    def test_duplicate_forms(self):
        p = plan(); p["forms"].append("10-Q"); self.reject_plan(p)

    def test_duplicate_nested_json_key(self):
        with self.assertRaises(v.InputError):
            v.loads(b'{"x":{"a":1,"a":2}}', 1000)

    def test_nonfinite_json(self):
        for raw in (b'{"n":NaN}', b'{"n":Infinity}', b'{"n":-Infinity}', b'{"n":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(v.InputError):
                v.loads(raw, 1000)

    def test_giant_integer_stable_error(self):
        with self.assertRaisesRegex(v.InputError, "numeric token"):
            v.loads(b'{"n":'+b'9'*5000+b'}', 10000)

    def test_invalid_utf8_and_surrogate(self):
        for raw in (b'"\xff"', b'"\\ud800"', b'{"\\ud800": 1}'):
            with self.subTest(raw=raw), self.assertRaises(v.InputError):
                v.loads(raw, 1000)

    def test_depth_limit(self):
        with self.assertRaises(v.InputError):
            v.loads(b'['*40+b'0'+b']'*40, 1000)

    def test_empty_and_oversize(self):
        for raw, limit in ((b'', 10), (b'{}', 1)):
            with self.subTest(raw=raw), self.assertRaises(v.InputError):
                v.loads(raw, limit)

    def test_invalid_numeric_fact_types(self):
        for value in (True, None, "100"):
            with self.subTest(value=value), self.assertRaises(v.InputError):
                v.compile_report(dump(source([observation(value)])), dump(plan()))

    def test_negative_zero_normalized(self):
        raw = dump(source()).replace(b'"val": 100,', b'"val": -0.000,')
        self.assertEqual(v.compile_report(raw, dump(plan()))["results"][0]["latest_value"], "0")

    def test_accession_shape(self):
        with self.assertRaises(v.InputError):
            v.compile_report(dump(source([observation(accn="not-an-accession")])), dump(plan()))

    def test_fy_boolean(self):
        with self.assertRaises(v.InputError):
            v.compile_report(dump(source([observation(fy=True)])), dump(plan()))

    def test_unknown_observation_fields(self):
        with self.assertRaises(v.InputError):
            v.compile_report(dump(source([observation(dimensions={})])), dump(plan()))

    def test_malformed_unmatched_period_not_hidden(self):
        with self.assertRaises(v.InputError):
            v.compile_report(dump(source([observation(end="invalid")])), dump(plan()))

    def test_null_taxonomy_is_not_absence(self):
        s = source(); s["facts"]["us-gaap"] = None
        with self.assertRaises(v.InputError):
            v.compile_report(dump(s), dump(plan()))

    def test_null_unit_is_not_absence(self):
        s = source(); s["facts"]["us-gaap"]["Revenue"]["units"]["USD"] = None
        with self.assertRaises(v.InputError):
            v.compile_report(dump(s), dump(plan()))

    def test_query_source_history_limit(self):
        with patch.object(v, "MAX_RECORDS", 1), self.assertRaises(v.InputError):
            v.compile_report(dump(source([observation(), observation()])), dump(plan()))

    def test_inventory_shows_units_without_guessing_mapping(self):
        inv = v.inventory(dump(source()))
        self.assertEqual(inv["concepts"], [{"taxonomy":"us-gaap", "concept":"Revenue", "units_observation_counts":{"USD":1}}])

    def test_same_unit_is_parsed_once_for_multiple_periods(self):
        p = plan(); other = copy.deepcopy(p["queries"][0]); other.update(id="q2", start="2024-04-01", end="2024-06-30"); p["queries"].append(other)
        with patch.object(v, "_observation", wraps=v._observation) as parse:
            v.compile_report(dump(source()), dump(p))
            self.assertEqual(parse.call_count, 1)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.source = dump(source())
        self.plan = dump(plan())
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root / "bundle"

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        members = v.build_bundle(self.source, self.plan)
        v.write_bundle(self.out, members)
        return members

    def test_reproducible_bundle_bytes(self):
        self.assertEqual(v.build_bundle(self.source, self.plan), v.build_bundle(self.source, self.plan))

    def test_full_roundtrip(self):
        self.create(); v.verify_bundle(self.out, self.source, self.plan)

    def test_each_member_tamper_is_rejected(self):
        members = self.create()
        for name, original in members.items():
            with self.subTest(name=name):
                (self.out/name).write_bytes(original+b' ')
                with self.assertRaises(v.InputError):
                    v.verify_bundle(self.out, self.source, self.plan)
                (self.out/name).write_bytes(original)

    def test_resealed_report_still_fails_semantic_recompile(self):
        self.create()
        report = json.loads((self.out/"report.json").read_bytes()); report["results"][0]["latest_value"] = "999999"
        altered = v.canonical(report); (self.out/"report.json").write_bytes(altered)
        manifest = json.loads((self.out/"manifest.json").read_bytes()); manifest["members"]["report.json"] = v.digest(altered)
        (self.out/"manifest.json").write_bytes(v.canonical(manifest))
        with self.assertRaises(v.InputError):
            v.verify_bundle(self.out, self.source, self.plan)

    def test_source_transplant(self):
        self.create()
        with self.assertRaises(v.InputError):
            v.verify_bundle(self.out, dump(source([observation(101)])), self.plan)

    def test_plan_transplant(self):
        self.create(); p = plan(); p["filed_on_or_before"] = "2024-11-30"
        with self.assertRaises(v.InputError):
            v.verify_bundle(self.out, self.source, dump(p))

    def test_missing_member(self):
        self.create(); (self.out/"manifest.json").unlink()
        with self.assertRaises(v.InputError):
            v.verify_bundle(self.out, self.source, self.plan)

    def test_extra_member(self):
        self.create(); (self.out/"extra").write_text("x")
        with self.assertRaises(v.InputError):
            v.verify_bundle(self.out, self.source, self.plan)

    def test_output_does_not_overwrite(self):
        members = self.create()
        with self.assertRaises(FileExistsError):
            v.write_bundle(self.out, members)
        v.verify_bundle(self.out, self.source, self.plan)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_input_refused(self):
        original = self.root/"original"; original.write_bytes(self.source)
        link = self.root/"link"; link.symlink_to(original)
        with self.assertRaises(v.InputError):
            v.read_regular(link, v.MAX_SOURCE_BYTES)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_output_refused(self):
        original = self.root/"original"; original.mkdir(); self.out.symlink_to(original, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            v.write_bundle(self.out, v.build_bundle(self.source, self.plan))
        self.assertEqual(list(original.iterdir()), [])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_bundle_refused(self):
        self.create(); link = self.root/"link"; link.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(v.InputError):
            v.verify_bundle(link, self.source, self.plan)

    def test_html_escapes_issuer_text(self):
        s = source(); s["entityName"] = '<script>alert("bad")</script>'
        h = v.build_bundle(dump(s), self.plan)["review.html"].decode()
        self.assertNotIn('<script>', h)
        self.assertIn('&lt;script&gt;', h)
        self.assertIn("default-src 'none'", h)

    def test_csv_text_is_formula_safe(self):
        for value in ('=1+1', '+CMD', '-CMD', '@SUM(1)', '  =1+1'):
            with self.subTest(value=value):
                s = source(); s["entityName"] = value
                rows = list(csv.reader(io.StringIO(v.build_bundle(dump(s), self.plan)["review.csv"].decode())))
                self.assertTrue(rows[1][2].startswith("'"))

    def test_negative_numeric_csv_not_text_escaped(self):
        rows = list(csv.reader(io.StringIO(v.build_bundle(dump(source([observation(-2)])), self.plan)["review.csv"].decode())))
        self.assertEqual(rows[1][12], '-2')

    def test_missing_numeric_csv_is_blank(self):
        rows = list(csv.reader(io.StringIO(v.build_bundle(dump(source([])), self.plan)["review.csv"].decode())))
        self.assertEqual(rows[1][11:14], ['', '', ''])

    def test_source_digest_binds_bytes_not_just_values(self):
        a = v.compile_report(self.source, self.plan)
        b = v.compile_report(self.source+b'\n', self.plan)
        self.assertEqual(a["results"], b["results"])
        self.assertNotEqual(a["source_sha256"], b["source_sha256"])

    def test_normal_and_optimized_cli_identical(self):
        source_file = self.root/"source.json"; source_file.write_bytes(self.source)
        plan_file = self.root/"plan.json"; plan_file.write_bytes(self.plan)
        for optimized in (False, True):
            out = self.root/("optimized" if optimized else "normal")
            cmd = [sys.executable]+(["-O"] if optimized else [])+[str(HERE/"sec_facts_vintage.py")]
            run = subprocess.run(cmd+["compile", "--source", str(source_file), "--plan", str(plan_file), "--bundle", str(out)], capture_output=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            check = subprocess.run(cmd+["verify", "--source", str(source_file), "--plan", str(plan_file), "--bundle", str(out)], capture_output=True, timeout=20)
            self.assertEqual(check.returncode, 0, check.stderr.decode())
        for name in v.BUNDLE_NAMES:
            self.assertEqual((self.root/"normal"/name).read_bytes(), (self.root/"optimized"/name).read_bytes())

    def test_cli_missing_fact_exit_three_after_report(self):
        src = self.root/"s.json"; src.write_bytes(dump(source([])))
        p = self.root/"p.json"; p.write_bytes(self.plan)
        run = subprocess.run([sys.executable, str(HERE/"sec_facts_vintage.py"), "compile", "--source", str(src), "--plan", str(p), "--bundle", str(self.out), "--require-unambiguous"], capture_output=True, timeout=20)
        self.assertEqual(run.returncode, 3)
        self.assertTrue((self.out/"manifest.json").is_file())

    def test_cli_bad_input_exit_two_no_traceback(self):
        src = self.root/"s.json"; src.write_bytes(b'{"n":'+b'9'*5000+b'}')
        run = subprocess.run([sys.executable, str(HERE/"sec_facts_vintage.py"), "inventory", "--source", str(src)], capture_output=True, timeout=20)
        self.assertEqual(run.returncode, 2)
        self.assertNotIn(b'Traceback', run.stderr)

    def test_interrupted_write_is_not_marked_complete_or_deleted(self):
        members = v.build_bundle(self.source, self.plan)
        with patch.object(v.os, "fsync", side_effect=OSError("synthetic write failure")), self.assertRaises(OSError):
            v.write_bundle(self.out, members)
        self.assertTrue(self.out.is_dir())
        self.assertFalse((self.out/"manifest.json").exists())
        with self.assertRaises(v.InputError):
            v.verify_bundle(self.out, self.source, self.plan)


if __name__ == "__main__":
    unittest.main()
