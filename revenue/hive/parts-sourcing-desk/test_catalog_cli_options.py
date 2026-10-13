"""Real CLI regressions for supplier mapping/default configuration intake.

Only synthetic supplier records and temporary files are used. No network,
application database, supplier contact or purchase operation is involved.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(os.environ.get("CATALOG_FILE_SCRIPT", Path(__file__).with_name("catalog_file.py")))


class CatalogCLIOptionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "catalog.csv"
        self.raw = b"PART,supplier\n0007,Existing supplier\n"
        self.source.write_bytes(self.raw)
        self.output = self.root / "preview.json"

    def run_cli(self, *, mapping=None, defaults=None, output=False):
        command = [sys.executable, "-B", str(SCRIPT), str(self.source)]
        for flag, content in (("mapping", mapping), ("defaults", defaults)):
            if content is not None:
                path = self.root / (flag + ".json")
                path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
                command.extend(["--" + flag, str(path)])
        if output:
            command.extend(["--output", str(self.output)])
        return subprocess.run(command, text=True, capture_output=True, timeout=10)

    def success(self, result, *, output=False):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        doc = json.loads(self.output.read_text() if output else result.stdout)
        self.assertFalse(doc["applied"])
        self.assertEqual(doc["supplier_contact"], "not_performed")
        self.assertEqual(doc["compatibility"], "not_inferred")
        self.assertEqual(doc["source"]["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(self.source.read_bytes(), self.raw)
        return doc["rows"][0]["fields"]

    def rejected(self, result, *, file, diagnostic):
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn(file, result.stderr)
        self.assertIn(diagnostic, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_duplicate_mapping_does_not_silently_retarget_part(self):
        self.rejected(self.run_cli(mapping='{"PART":"supplier_sku","PART":"part_number"}', output=True),
                      file="mapping.json", diagnostic="duplicate")

    def test_duplicate_default_does_not_silently_change_supplier(self):
        self.rejected(self.run_cli(defaults='{"currency":"USD","currency":"EUR"}', output=True),
                      file="defaults.json", diagnostic="duplicate")

    def test_nested_duplicate_defaults_are_not_discarded(self):
        self.rejected(self.run_cli(defaults='{"note":{"catalog":"A","catalog":"B"}}', output=True),
                      file="defaults.json", diagnostic="duplicate")

    def test_escaped_equivalent_keys_count_as_duplicates(self):
        self.rejected(self.run_cli(mapping=r'{"PART":"sku","\u0050ART":"part"}', output=True),
                      file="mapping.json", diagnostic="duplicate")

    def test_utf8_bom_defaults_are_read(self):
        fields = self.success(self.run_cli(defaults='\ufeff{"currency":"USD","note":"café"}'))
        self.assertEqual(fields["currency"], "USD")
        self.assertEqual(fields["note"], "café")

    def test_utf8_bom_mapping_is_read(self):
        fields = self.success(self.run_cli(mapping='\ufeff{"PART":"part_number"}'))
        self.assertEqual(fields["part_number"], "0007")
        self.assertNotIn("PART", fields)

    def test_decimal_defaults_retain_precision_and_scale(self):
        fields = self.success(self.run_cli(defaults='{"price":12.300000000000000000000001,"shipping":7.50}'))
        self.assertEqual(fields["price"], "12.300000000000000000000001")
        self.assertEqual(fields["shipping"], "7.50")

    def test_decimal_values_in_nested_defaults_retain_precision(self):
        fields = self.success(self.run_cli(defaults='{"metadata":{"values":[0.10,12.300000000000000000000001]}}'))
        self.assertEqual(fields["metadata"]["values"], ["0.10", "12.300000000000000000000001"])

    def test_finite_exponents_do_not_overflow_through_binary_float(self):
        fields = self.success(self.run_cli(defaults='{"large":1e400,"tiny":1e-400}'))
        self.assertEqual(fields["large"], "1E+400")
        self.assertEqual(fields["tiny"], "1E-400")

    def test_negative_zero_decimal_retains_sign_and_scale(self):
        fields = self.success(self.run_cli(defaults='{"adjustment":-0.00}'))
        self.assertEqual(fields["adjustment"], "-0.00")

    def test_integer_boolean_null_and_string_defaults_keep_types(self):
        fields = self.success(self.run_cli(defaults='{"qty":123456789012345678901234567890,"flag":true,"note":null,"sku":"0008"}'))
        self.assertEqual(fields["qty"], 123456789012345678901234567890)
        self.assertIs(type(fields["qty"]), int)
        self.assertIs(fields["flag"], True)
        self.assertIsNone(fields["note"])
        self.assertEqual(fields["sku"], "0008")

    def test_valid_rename_and_defaults_preserve_existing_supplier(self):
        fields = self.success(self.run_cli(mapping='{"PART":"part_number"}',
                                          defaults='{"supplier":"Fallback","currency":"USD"}', output=True), output=True)
        self.assertEqual(fields, {"part_number": "0007", "supplier": "Existing supplier", "currency": "USD"})

    def test_blank_supplier_accepts_default(self):
        self.raw = b"PART,supplier\n0007,\n"
        self.source.write_bytes(self.raw)
        fields = self.success(self.run_cli(defaults='{"supplier":"Explicit fallback"}'))
        self.assertEqual(fields["supplier"], "Explicit fallback")

    def test_nonfinite_defaults_name_the_configuration_file(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                self.rejected(self.run_cli(defaults='{"unused":' + value + '}', output=True),
                              file="defaults.json", diagnostic="non-finite")

    def test_nonfinite_existing_default_is_not_silently_ignored(self):
        self.rejected(self.run_cli(defaults='{"supplier":NaN}', output=True),
                      file="defaults.json", diagnostic="non-finite")

    def test_malformed_json_has_filename_and_line(self):
        self.rejected(self.run_cli(defaults='{\n"currency":}', output=True),
                      file="defaults.json", diagnostic="line 2, column")

    def test_bad_utf8_has_filename_and_no_traceback(self):
        self.rejected(self.run_cli(defaults=b'{"currency":"\xff"}', output=True),
                      file="defaults.json", diagnostic="UTF-8")

    def test_mapping_must_remain_string_to_string(self):
        for value in ("1.25", "12", "true", "null", "{}", "[]"):
            with self.subTest(value=value):
                result = self.run_cli(mapping='{"PART":' + value + '}', output=True)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("mapping must pair", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(self.output.exists())

    def test_configuration_requires_an_object(self):
        for value in ("[]", "null", "12", '"text"'):
            for option in ("mapping", "defaults"):
                with self.subTest(value=value, option=option):
                    self.rejected(self.run_cli(**{option: value}, output=True),
                                  file=option + ".json", diagnostic="JSON object")

    def test_empty_configuration_objects_are_valid(self):
        self.assertEqual(self.success(self.run_cli(mapping="{}", defaults="{}")),
                         {"PART": "0007", "supplier": "Existing supplier"})

    def test_existing_output_remains_byte_exact(self):
        original = b"original output\n"
        self.output.write_bytes(original)
        result = self.run_cli(defaults='{"currency":"USD"}', output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(result.stdout, "")

    def test_unrepresentable_decimal_returns_configuration_diagnostic(self):
        self.rejected(self.run_cli(defaults='{"metric":1e9999999999999999999999999999999}', output=True),
                      file="defaults.json", diagnostic="decimal range")

    def test_decimal_defaults_match_catalog_json_normalization(self):
        from importlib.util import module_from_spec, spec_from_file_location
        spec = spec_from_file_location("catalog_file_under_test", SCRIPT)
        module = module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            expected = module.parse_bytes(b'[{"price":12.30,"nested":[0.10]}]', 'x.json').records[0]["fields"]
        finally:
            sys.modules.pop(spec.name, None)
        fields = self.success(self.run_cli(defaults='{"price":12.30,"nested":[0.10]}'))
        self.assertEqual({key: fields[key] for key in expected}, expected)


if __name__ == "__main__":
    unittest.main()
