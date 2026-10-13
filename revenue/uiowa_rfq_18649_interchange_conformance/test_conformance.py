from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import conformance as c


class ReferenceTests(unittest.TestCase):
    def test_bool_int_float_are_distinct(self):
        for a, b in ((True, 1), (1, 1.0), (False, 0), (0.0, -0.0)):
            self.assertFalse(c.same_json(a, b))

    def test_object_order_is_not_identity(self):
        self.assertTrue(c.same_json({"a": 1, "b": []}, {"b": [], "a": 1}))

    def test_unicode_is_not_normalized(self):
        self.assertFalse(c.same_json("é", "e\u0301"))

    def test_strict_json_rejects_duplicates_nonfinite(self):
        for raw in (b'{"a":1,"a":2}', b'NaN', b'Infinity', b'1e999'):
            with self.subTest(raw=raw), self.assertRaises(c.CheckError):
                c.strict_json(raw)

    def test_precision_loss_rejected_before_recovery(self):
        for raw in (b'{"n":0.123456789012345678901}', b'1e-400', b'9007199254740993.0'):
            with self.subTest(raw=raw), self.assertRaises(c.CheckError):
                c.strict_json(raw)

    def test_supported_decimal_tokens(self):
        self.assertTrue(c.same_json(c.strict_json(b'[0.1,1e1,-0.0]'), [0.1,10.0,-0.0]))

    def test_invalid_unicode(self):
        with self.assertRaises(c.CheckError):
            c.strict_json(b'"\\ud800"')

    def test_non_string_key(self):
        with self.assertRaises(c.CheckError):
            c.semantic_text({1: "value"})

    def test_empty_null_absent(self):
        self.assertFalse(c.same_json({}, {"n": None}))
        self.assertFalse(c.same_json({"n": ""}, {"n": None}))

    def test_legacy_encoding_keeps_exact_text(self):
        self.assertEqual(c.expected_legacy_rows({"01": -0.0, "~a/b": "\r\n"}),
                         [c.LEGACY_HEADER, ["/01", "float", "-0.0", "present"],
                          ["/~0a~1b", "string", "\r\n", "present"]])

    def test_legacy_reference_ambiguity_remains(self):
        self.assertEqual(c.expected_legacy_rows(["v"]), c.expected_legacy_rows({"0": "v"}))
        self.assertFalse(c.same_json(["v"], {"0": "v"}))

    def test_legacy_scalars_and_containers(self):
        rows = c.expected_legacy_rows({"n": None, "b": False, "e": "", "o": {}, "a": []})
        self.assertEqual([r[1:] for r in rows[1:]], [
            ["null", "", "null"], ["bool", "false", "present"], ["string", "", "empty"],
            ["object", "", "empty"], ["array", "", "empty"]])

    def test_bad_codec_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.py"
            path.write_text("x = 1\n")
            with self.assertRaises(c.CheckError):
                c.load_codec(path)

    def test_input_size_bound(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "input"
            path.write_bytes(b"x" * (c.MAX_BYTES + 1))
            with self.assertRaises(c.CheckError):
                c.bounded_bytes(path)


class CanonicalIntegrationTests(unittest.TestCase):
    """Required codec path makes absent integration evidence an error, not a skip."""
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("UIOWA_CANONICAL_CODEC")
        if not path:
            raise RuntimeError("Set UIOWA_CANONICAL_CODEC to the trusted canonical transport.py")
        cls.codec, cls.identity = c.load_codec(Path(path))
        cls.fixture = c.strict_json(Path(__file__).with_name("synthetic.json").read_bytes())

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.original = self.root / "original.json"
        self.legacy = self.root / "legacy.csv"
        self.output = self.root / "recovered.csv"
        self.original.write_text(json.dumps(self.fixture, ensure_ascii=False), encoding="utf-8")
        with self.legacy.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(c.expected_legacy_rows(self.fixture))

    def recover(self):
        return c.recover(self.codec, self.identity, self.original, self.legacy, self.output)

    def test_full_audit(self):
        report = c.audit(self.codec, self.identity, self.fixture)
        self.assertEqual(report["counts"], {"passed": 34, "failed": 0, "total": 34}, report)

    def test_source_confirmed_recovery(self):
        receipt = self.recover()
        self.assertTrue(c.same_json(self.fixture, self.codec.read_csv(self.output)))
        self.assertEqual(receipt["new_csv_sha256"], c.digest(self.output.read_bytes()))
        self.assertEqual(receipt["original_json_sha256"], c.digest(self.original.read_bytes()))
        self.assertEqual(receipt["legacy_csv_sha256"], c.digest(self.legacy.read_bytes()))

    def test_no_overwrite(self):
        self.output.write_bytes(b"preserve me")
        with self.assertRaises(FileExistsError):
            self.recover()
        self.assertEqual(self.output.read_bytes(), b"preserve me")

    def test_lossy_decimal_original_creates_no_output(self):
        self.original.write_text('{"n":0.123456789012345678901}')
        with self.assertRaises(c.CheckError):
            self.recover()
        self.assertFalse(self.output.exists())

    def test_wrong_reference_creates_no_output(self):
        self.original.write_text('{"unrelated":"data"}')
        with self.assertRaises(c.CheckError):
            self.recover()
        self.assertFalse(self.output.exists())

    def test_duplicate_original_key_creates_no_output(self):
        self.original.write_text('{"a":1,"a":2}')
        with self.assertRaises(c.CheckError):
            self.recover()
        self.assertFalse(self.output.exists())

    def test_header_ragged_duplicate_extra_and_reordered_rows(self):
        table = c.expected_legacy_rows(self.fixture)
        mutations = [table[1:], [table[0] + ["extra"]] + table[1:],
                     table + [table[-1]], table[:-1],
                     [table[0], table[2], table[1]] + table[3:],
                     [table[0], table[1][:-1]] + table[2:]]
        for mutation in mutations:
            with self.subTest(rows=len(mutation)):
                with self.legacy.open("w", newline="", encoding="utf-8") as stream:
                    csv.writer(stream).writerows(mutation)
                with self.assertRaises(c.CheckError):
                    self.recover()
                self.assertFalse(self.output.exists())

    def test_recovery_requires_canonical_format(self):
        with self.assertRaises(c.CheckError):
            c.recover(SimpleNamespace(), {}, self.original, self.legacy, self.output)
        self.assertFalse(self.output.exists())

    def test_inputs_unchanged(self):
        originals = (self.original.read_bytes(), self.legacy.read_bytes())
        self.recover()
        self.assertEqual(originals, (self.original.read_bytes(), self.legacy.read_bytes()))

    def test_wrong_reference_can_match_ambiguous_legacy(self):
        # The operator's supplied original is indispensable, NOT authenticated.
        self.original.write_text('{"0":"v"}')
        with self.legacy.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(c.expected_legacy_rows(["v"]))
        receipt = self.recover()
        self.assertEqual(self.codec.read_csv(self.output), {"0": "v"})
        self.assertIn("cannot establish", receipt["limitation"])


if __name__ == "__main__":
    unittest.main()
