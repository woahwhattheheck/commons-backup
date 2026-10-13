"""CLI ingress regressions; import the one sibling reporter, never copy its math."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "strict_ingress_reporter", HERE / "v31_delta_distribution_report.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load sibling reporter")
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)

VALID = {
    "opponent": "official", "seed": 7, "seat": 1,
    "baseline": {"scores": [90, 100]},
    "candidate": {"scores": [90, 120]},
}


class StrictJsonIngressTests(unittest.TestCase):
    def assert_bad_data(self, raw: bytes) -> None:
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / "input.json", Path(td) / "output.json"
            source.write_bytes(raw)
            output.write_bytes(b"keep existing report\n")
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = reporter.main([str(source), "--output", str(output)])
            self.assertEqual(status, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertTrue(stderr.getvalue().startswith("DATA ERROR:"))
            self.assertEqual(output.read_bytes(), b"keep existing report\n")

    def test_duplicate_candidate_score_cannot_choose_positive_last_value(self):
        self.assert_bad_data(b'[{"opponent":"a","seed":1,"seat":0,"baseline":{"own":100,"rival":90},"candidate":{"own":1,"own":120,"rival":90}}]')

    def test_duplicate_root_cannot_select_positive_cells(self):
        positive = json.dumps([VALID])
        self.assert_bad_data(('{"cells":[],"cells":' + positive + '}').encode())

    def test_duplicate_key_with_equal_values_is_still_ambiguous(self):
        self.assert_bad_data(json.dumps([VALID]).replace('"seed": 7', '"seed": 7, "seed": 7').encode())

    def test_escaped_key_spelling_is_checked_after_decoding(self):
        raw = json.dumps([VALID]).replace('"seat": 1', '"seat": 1, "\\u0073eat": 1')
        self.assert_bad_data(raw.encode())

    def test_duplicate_unknown_metadata_is_not_silently_discarded(self):
        raw = '{"metadata":{"owner":"first","owner":"second"},"cells":' + json.dumps([VALID]) + '}'
        self.assert_bad_data(raw.encode())

    def test_nonfinite_constants_in_unused_metadata_are_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                self.assert_bad_data(('{"metadata":' + token + ',"cells":' + json.dumps([VALID]) + '}').encode())

    def test_finite_syntax_with_overflowing_float_is_rejected(self):
        for token in ("1e9999", "-1e9999"):
            with self.subTest(token=token):
                self.assert_bad_data(('{"metadata":' + token + ',"cells":' + json.dumps([VALID]) + '}').encode())

    def test_invalid_utf8_is_a_data_error_not_a_traceback(self):
        self.assert_bad_data(b'[{"opponent":"\xff"}]')

    def test_integer_parser_limit_is_a_data_error(self):
        if not hasattr(sys, "get_int_max_str_digits"):
            self.skipTest("interpreter does not expose an integer parser limit")
        original = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(640)
            self.assert_bad_data(b'[{"seed":' + b'9' * 641 + b'}]')
        finally:
            sys.set_int_max_str_digits(original)

    def test_parser_recursion_limit_is_a_data_error(self):
        depth = sys.getrecursionlimit() + 100
        self.assert_bad_data(b'[' * depth + b'0' + b']' * depth)

    def test_bad_syntax_remains_a_data_error(self):
        self.assert_bad_data(b'{broken')

    def test_valid_unicode_and_numeric_evidence_is_unchanged(self):
        row = dict(VALID, opponent="caf\u00e9", activations={"feed": 2})
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "input.json"
            source.write_text(json.dumps([row], ensure_ascii=False), encoding="utf-8")
            loaded = reporter._read_json(source)
            self.assertEqual(loaded, [row])
            self.assertEqual(reporter.analyze(loaded), reporter.analyze([row]))
            self.assertEqual(reporter.analyze(loaded)["delta_m"]["mean"], 20.0)

    def test_valid_cli_measurement_and_policy_exit_codes_remain_distinct(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "input.json"
            source.write_text(json.dumps([VALID]), encoding="utf-8")
            for args, expected in (([], 0), (["--min-mean-delta", "21"], 1)):
                with self.subTest(args=args), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(reporter.main([str(source), *args]), expected)

    def test_duplicate_objects_in_distinct_cells_are_not_duplicate_members(self):
        rows = [VALID, dict(VALID, seed=8)]
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "input.json"
            source.write_text(json.dumps(rows), encoding="utf-8")
            self.assertEqual(reporter._read_json(source), rows)
            self.assertEqual(reporter.analyze(rows)["cells"], 2)


if __name__ == "__main__":
    unittest.main()
