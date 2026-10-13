#!/usr/bin/env python3
"""Common-register transport and CSV parser regressions."""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("uiowa031_interchange_test_subject", HERE / "evidence_register_interchange.py")
if _spec is None or _spec.loader is None:
    raise ImportError("missing interchange module")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
v = m._validator


def table(columns, values):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows(values)
    return stream.getvalue()


class RegisterCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fixture = (HERE / "23-synthetic-evidence-register.csv").read_bytes().decode("utf-8")
        self.packet = m.from_csv(self.fixture)
        self.columns = self.packet["columns"]
        self.rows = self.packet["rows"]
        self.values = [self.rows[0][c] for c in self.columns]

    def csv_errors(self, text):
        return v.parse_csv(text)[2]

    def input(self, name, text):
        path = self.root / name
        path.write_bytes(text.encode("utf-8"))
        return path

    def cli(self, *args, optimized=False):
        command = [sys.executable]
        if optimized:
            command.append("-O")
        return subprocess.run(command + [str(HERE / "evidence_register_interchange.py"), *map(str, args)],
                              capture_output=True, text=True, timeout=15)


class ParserRegressionTests(RegisterCase):
    def test_exact_original_fixture_and_semantics(self):
        self.assertEqual(v.validate(HERE / "23-synthetic-evidence-register.csv"), [])
        self.assertEqual(len(self.rows), 7)
        self.assertEqual(self.rows[3]["confidence"], "UNRESOLVED")
        self.assertEqual(self.rows[-1]["evidence_state"], "NO_EVIDENCE_OBSERVED")

    def test_duplicate_required_header(self):
        self.assertTrue(any("duplicate" in e for e in self.csv_errors(table(self.columns + ["confidence"], [self.values + ["LOW"]]))))

    def test_duplicate_extension_header(self):
        self.assertTrue(self.csv_errors(table(self.columns + ["revision", "revision"], [self.values + ["a", "b"]])))

    def test_blank_header(self):
        self.assertTrue(self.csv_errors(table(self.columns + ["  "], [self.values + ["unlabelled"]])))

    def test_surplus_cells(self):
        self.assertTrue(any("expected" in e for e in self.csv_errors(table(self.columns, [self.values + ["lost"]]))))

    def test_short_record_reports_error_without_exception(self):
        self.assertTrue(any("expected" in e for e in self.csv_errors(table(self.columns, [self.values[:-1]]))))

    def test_unterminated_quote(self):
        header = table(self.columns, [])
        text = header + ",".join(self.values[:-1]) + ',"unterminated'
        self.assertTrue(any("CSV input error" in e for e in self.csv_errors(text)))

    def test_junk_after_closing_quote(self):
        header = table(self.columns, [])
        text = header + ",".join(self.values[:-1]) + ',"quote"junk\r\n'
        self.assertTrue(self.csv_errors(text))

    def test_missing_columns(self):
        self.assertTrue(any("missing required" in e for e in self.csv_errors("name\nvalue\n")))

    def test_empty_file_is_not_header(self):
        self.assertTrue(self.csv_errors(""))

    def test_header_only_remains_structurally_valid(self):
        self.assertEqual(v.parse_csv(table(self.columns, [])), (self.columns, [], []))

    def test_blank_lines_do_not_fabricate_rows(self):
        self.assertEqual(len(m.from_csv(self.fixture + "\r\n\r\n")["rows"]), 7)

    def test_invalid_utf8_is_diagnostic(self):
        path = self.root / "invalid.csv"
        path.write_bytes(b"\xff")
        self.assertTrue(v.validate(path))

    def test_missing_file_is_diagnostic(self):
        self.assertTrue(v.validate(self.root / "missing.csv"))

    def test_directory_input_is_diagnostic(self):
        self.assertTrue(v.validate(self.root))

    def test_nonstr_text_input(self):
        self.assertTrue(v.parse_csv(None)[2])

    def test_schema_types_are_not_coerced(self):
        for bad in (None, 2, True, [], {}):
            packet = copy.deepcopy(self.packet)
            packet["rows"][0]["claim"] = bad
            with self.subTest(bad=bad), self.assertRaises(m.RegisterError):
                m.validate_packet(packet)

    def test_nonscalar_unicode_fails_cleanly(self):
        packet = copy.deepcopy(self.packet)
        packet["rows"][0]["claim"] = "bad\ud800"
        with self.assertRaises(m.RegisterError):
            m.to_json(packet)

    def test_cli_count_uses_same_snapshot(self):
        with mock.patch.object(v, "load_register", return_value=(self.columns, self.rows, [])) as read, \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(v.main(["validator", "/not/a/real/file.csv"]), 0)
        read.assert_called_once()
        self.assertEqual(out.getvalue(), "OK rows=7 observations=7 findings=5\n")


class RoundTripTests(RegisterCase):
    def test_original_round_trip(self):
        self.assertEqual(m.from_csv(m.to_csv(m.from_json(m.to_json(self.packet)))), self.packet)

    def test_column_row_order_and_extensions_preserved(self):
        packet = copy.deepcopy(self.packet)
        packet["columns"] = ["source_version", "excerpt_locator"] + list(reversed(self.columns))
        packet["rows"].reverse()
        for index, row in enumerate(packet["rows"]):
            row.update(source_version="0007.0", excerpt_locator=f"Section A, paragraph {index}")
        self.assertEqual(m.from_csv(m.to_csv(m.from_json(m.to_json(packet)))), packet)

    def test_multiline_quotes_unicode_crlf_and_formula_text_exact(self):
        values = ['with,comma', 'a "quoted" word', 'line1\r\nline2', 'line1\nline2', 'line1\rline2',
                  '  not trimmed  ', 'é\U0001f642', '=SUM(A1:A2)', '001', '\u2028', '\t', '\0']
        for value in values:
            packet = copy.deepcopy(self.packet)
            packet["columns"].append("opaque_note")
            for row in packet["rows"]:
                row["opaque_note"] = value
            with self.subTest(value=repr(value)):
                self.assertEqual(m.from_csv(m.to_csv(m.from_json(m.to_json(packet)))), packet)

    def test_source_containers_not_mutated(self):
        before = copy.deepcopy(self.packet)
        copy_packet = m.validate_packet(self.packet)
        copy_packet["rows"][0]["claim"] = "changed clone"
        self.assertEqual(self.packet, before)

    def test_json_duplicate_envelope_key(self):
        text = m.to_json(self.packet).replace('"schema":', '"schema":"wrong", "schema":', 1)
        with self.assertRaisesRegex(m.RegisterError, "duplicate"):
            m.from_json(text)

    def test_json_duplicate_record_key(self):
        text = m.to_json(self.packet).replace('"claim":', '"claim":"discarded", "claim":', 1)
        with self.assertRaisesRegex(m.RegisterError, "duplicate"):
            m.from_json(text)

    def test_nonfinite_json_rejected(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant), self.assertRaises(m.RegisterError):
                m.from_json(m.to_json(self.packet).replace('"LOW"', constant, 1))

    def test_bad_json_syntax(self):
        with self.assertRaises(m.RegisterError):
            m.from_json("{")

    def test_missing_extra_envelope_fields_rejected(self):
        for mutation in (lambda p: p.pop("schema"), lambda p: p.update(unrecognized=True)):
            packet = copy.deepcopy(self.packet)
            mutation(packet)
            with self.assertRaises(m.RegisterError):
                m.validate_packet(packet)

    def test_extra_or_missing_record_key_rejected(self):
        for mutation in (lambda r: r.pop("claim"), lambda r: r.update(extra="not in columns")):
            packet = copy.deepcopy(self.packet)
            mutation(packet["rows"][0])
            with self.assertRaises(m.RegisterError):
                m.validate_packet(packet)

    def test_wrong_schema_rejected(self):
        self.packet["schema"] = "unrecognized/2"
        with self.assertRaises(m.RegisterError):
            m.validate_packet(self.packet)

    def test_deterministic_canonical_outputs(self):
        self.assertEqual(m.to_json(self.packet), m.to_json(m.from_json(m.to_json(self.packet))))
        self.assertEqual(m.to_csv(self.packet), m.to_csv(m.from_csv(m.to_csv(self.packet))))

    def test_empty_transport_not_fabricated_evidence(self):
        self.packet["rows"] = []
        self.assertEqual(m.from_json(m.to_json(self.packet))["rows"], [])

    def test_pinned_synthetic_missingness_and_disagreement(self):
        packet = m.from_csv(m.to_csv(m.from_json(m.to_json(self.packet))))
        self.assertEqual(packet["rows"][3:5], self.rows[3:5])
        self.assertEqual(packet["rows"][-1], self.rows[-1])
        self.assertEqual({r["content_digest"] for r in packet["rows"]}, {v.NOT_RETAINED_DIGEST})

    def test_import_does_not_pollute_searchpath_or_generic_modules(self):
        before_path = list(sys.path)
        before_modules = set(sys.modules)
        spec = importlib.util.spec_from_file_location("fresh_subject", HERE / "evidence_register_interchange.py")
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        self.assertEqual(sys.path, before_path)
        self.assertFalse({"validator", "validate_23_evidence_register", "schema", "model"} & (set(sys.modules) - before_modules))


class PublicationTests(RegisterCase):
    def test_cli_conversion_works_normal_and_optimized(self):
        original = self.input("source.csv", self.fixture)
        for optimized in (False, True):
            target = self.root / f"target-{optimized}.json"
            result = self.cli("csv-to-json", original, target, optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            csv_target = self.root / f"roundtrip-{optimized}.csv"
            result = self.cli("json-to-csv", target, csv_target, optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(m.load_packet(csv_target, "csv"), self.packet)
        self.assertEqual((self.root / "target-False.json").read_bytes(), (self.root / "target-True.json").read_bytes())

    def test_existing_output_not_overwritten(self):
        output = self.input("already.txt", "keep me")
        with self.assertRaises(m.RegisterError):
            m.publish_new(output, "replacement")
        self.assertEqual(output.read_text(), "keep me")
        self.assertEqual(list(self.root.glob(".uiowa031-*")), [])

    def test_output_same_as_input_refused(self):
        source = self.input("source.csv", self.fixture)
        result = self.cli("csv-to-json", source, source)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(source.read_bytes().decode(), self.fixture)

    def test_output_hardlink_alias_refused(self):
        source = self.input("source.csv", self.fixture)
        alias = self.root / "alias"
        os.link(source, alias)
        self.assertEqual(self.cli("csv-to-json", source, alias).returncode, 1)
        self.assertEqual(source.read_bytes().decode(), self.fixture)

    def test_output_symlink_alias_refused(self):
        source = self.input("source.csv", self.fixture)
        alias = self.root / "alias"
        alias.symlink_to(source)
        self.assertEqual(self.cli("csv-to-json", source, alias).returncode, 1)
        self.assertEqual(source.read_bytes().decode(), self.fixture)

    def test_invalid_input_never_creates_output(self):
        source = self.input("bad.csv", "no,proper,header\nx,y,z\n")
        target = self.root / "absent.json"
        result = self.cli("csv-to-json", source, target)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(target.exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_read_error_is_cli_diagnostic(self):
        result = self.cli("csv-to-json", self.root / "absent.csv", self.root / "out.json")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_utf8_is_cli_diagnostic(self):
        source = self.root / "source.csv"
        source.write_bytes(b"\xff")
        result = self.cli("csv-to-json", source, self.root / "out.json")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_interrupted_write_never_publishes(self):
        output = self.root / "output"
        with mock.patch.object(m.os, "fsync", side_effect=OSError("simulated write failure")):
            with self.assertRaises(m.RegisterError):
                m.publish_new(output, "all bytes")
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".uiowa031-*")), [])

    def test_existing_parent_required(self):
        with self.assertRaises(m.RegisterError):
            m.publish_new(self.root / "absent-parent" / "out.json", "text")
        self.assertFalse((self.root / "absent-parent").exists())

    def test_no_dependency_on_current_working_directory(self):
        source = self.input("source.csv", self.fixture)
        proc = subprocess.run([sys.executable, str(HERE / "evidence_register_interchange.py"),
                               "csv-to-json", str(source), str(self.root / "out.json")],
                              cwd=self.root, capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
