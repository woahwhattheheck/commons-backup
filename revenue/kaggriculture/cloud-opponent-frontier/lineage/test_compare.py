"""Regression coverage for the non-executing lineage tool."""
import ast
import base64
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zlib

import compare


def action(op="PASS", market=None):
    return {"farmer": [op], "hands": [], "market": market or []}


def packed(value, encoding="b85"):
    blob = getattr(base64, encoding + "encode")(zlib.compress(json.dumps(value).encode())).decode()
    return f'json.loads(zlib.decompress(base64.{encoding}decode({blob!r})).decode())'


class DecoderTests(unittest.TestCase):
    def test_supported_encodings_are_nonexecuting_and_equal(self):
        route = [action(), action("WATER")]
        for encoding in ("b64", "b85"):
            expression = ast.parse(packed(route, encoding), mode="eval").body
            self.assertEqual(compare.data_value(expression, {}), route)

    def test_import_and_unknown_call_are_never_executed(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "should-not-exist"
            text = f"from pathlib import Path\nPath({str(marker)!r}).write_text('BAD')\nDATA=json.loads(unknown())\n"
            profile, routes, _ = compare.python_profile(text)
            self.assertFalse(marker.exists())
            self.assertFalse(routes)
            self.assertEqual(profile["diagnostics"][0]["error"], "ValueError")

    def test_compressed_size_truncation_and_trailing_data(self):
        blob = zlib.compress(b"x" * 1000)
        with mock.patch.object(compare, "MAX_DECODED", 10):
            with self.assertRaises(ValueError):
                compare.inflate(blob)
        for bad in (blob[:-1], blob + b"garbage", blob + blob):
            with self.assertRaises(ValueError):
                compare.inflate(bad)

    def test_arlene_tails_reconstruct_from_named_parent(self):
        full = [action(), action("WATER"), action("FEED")]
        data = {"main": "base", "full": full, "tails": [
            {"h": "first", "parent": "base", "at": 1, "suffix": [action("DIG"), action("CARE")]},
            {"h": "second", "parent": "first", "at": 2, "suffix": [action("HARVEST")]},
        ]}
        result = compare.routes_from_data(data)
        self.assertEqual(result["data/second"], [action(), action("DIG"), action("HARVEST")])
        self.assertEqual(data["full"], full)
        data["tails"][0]["parent"] = "missing"
        with self.assertRaises(ValueError):
            compare.routes_from_data(data)

    def test_lazy_blob_and_all_tail_variants_are_found_once(self):
        route = [action(), action("WATER")]
        data = {"main": "base", "full": route, "tails": [{"h": "tail", "parent": "base", "at": 1, "suffix": [action("DIG")]}]}
        blob = base64.b64encode(zlib.compress(json.dumps(data).encode())).decode()
        source = f"_BLOB = {blob!r}\ndef routes():\n    return json.loads(zlib.decompress(base64.b64decode(_BLOB)).decode())\n"
        profile, routes, _ = compare.python_profile(source)
        self.assertEqual(len(routes), 2)
        self.assertFalse(profile["diagnostics"])

    def test_duplicate_tail_is_an_error_not_overwrite(self):
        with self.assertRaises(ValueError):
            compare.routes_from_data({"main": "base", "full": [action()], "tails": [
                {"h": "base", "parent": "base", "at": 0, "suffix": [action("DIG")]}
            ]})

    def test_ast_ignores_docs_but_not_identifiers_or_logic(self):
        a = compare.python_profile('"""a"""\n# note\ndef f():\n    "doc"\n    return 1\n')[0]
        b = compare.python_profile('def f():\n return 1\n')[0]
        c = compare.python_profile('def f():\n return 2\n')[0]
        self.assertEqual(a["ast_sha256"], b["ast_sha256"])
        self.assertNotEqual(a["ast_sha256"], c["ast_sha256"])


class NativeTests(unittest.TestCase):
    symbols = {"_UNIT_OPS": ("PASS", "PLANT", "PICKUP"),
               "_MARKET_OPS": ("PASS", "HIRE", "SELL"), "_ITEMS": ("WHEAT", "CARROT")}

    def test_native_actions_match_wrapper_shapes(self):
        text = 'constexpr int kTurns = 2; constexpr int kRoutes = 1; const char* kEncodedTapes[kRoutes][kTurns] = {{"1 1 1 1 1 1 0 99", "2 2 0 0 0 2 0 3 0 0 0 2 1 4"}};'
        result = compare.native_tapes(text, self.symbols)["native/0"]
        self.assertEqual(result[0], {"farmer": ["PLANT", "CARROT"], "hands": [], "market": [["HIRE"]]})
        self.assertEqual(result[1], {"farmer": ["PASS"], "hands": [["PICKUP", "WHEAT", 3]], "market": [["SELL", "CARROT", 4]]})

    def test_invalid_counts_or_opcodes_are_reported(self):
        for encoded in ('1 0 0 0', '1 0 90 0 0', '1 0 0 0 0 99'):
            text = 'int kTurns = 1; int kRoutes = 1; const char* kEncodedTapes[kRoutes][kTurns] = {{"' + encoded + '"}};'
            with self.assertRaises(ValueError):
                compare.native_tapes(text, self.symbols)


class ReportTests(unittest.TestCase):
    def test_unequal_lengths_are_not_full_identity(self):
        result = compare.route_overlap([action(), action("DIG")], [action()])
        self.assertEqual(result["equal_actions"], 1)
        self.assertFalse(result["identical_full_route"])
        self.assertEqual(result["candidate_only_turns"], 1)

    def test_order_and_extra_fields_remain_material(self):
        a = action(market=[["SELL", "WHEAT", 1], ["SELL", "CARROT", 2]])
        b = action(market=list(reversed(a["market"])))
        self.assertEqual(compare.route_overlap([a], [b])["equal_actions"], 0)
        c = {**a, "extra": True}
        self.assertEqual(compare.route_overlap([a], [c])["equal_actions"], 0)

    def test_relative_paths_missing_reference_and_evidence_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            code = '_ACTIONS = ' + packed([action(), action("WATER")]) + '\n'
            (root / "a.py").write_text(code)
            (root / "renamed.py").write_text(code)
            (root / "metadata.json").write_text('{"author":"fixture", "license":null}')
            manifest = {"candidate": {"id": "candidate", "files": ["a.py"], "evidence": ["metadata.json"], "provenance": {"author": "fixture", "license": None}},
                        "references": [{"id": "copy", "files": ["renamed.py"]}, {"id": "absent", "missing": "not provided"}]}
            report = compare.compare_manifest(manifest, root)
            self.assertTrue(report["comparisons"][0]["identical_code_file_multiset"])
            self.assertTrue(report["comparisons"][0]["route_pairs"][0]["identical_full_route"])
            self.assertNotIn("route_pairs", report["comparisons"][1])
            self.assertEqual(report["references"][1]["status"], "missing")
            self.assertIsNone(report["candidate"]["provenance"]["license"])
            self.assertEqual(report["candidate"]["evidence"][0]["sha256"], compare.digest((root/"metadata.json").read_bytes()))
            (root / "inputs.json").write_text(json.dumps(manifest))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compare.main(["--manifest", str(root/"inputs.json"), "--output", str(root/"report.json")]), 0)
            self.assertEqual(json.loads((root/"report.json").read_text()), report)

    def test_cli_failure_does_not_overwrite_prior_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "in.json").write_text("{}")
            (root / "out.json").write_text("old")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(compare.main(["--manifest", str(root/"in.json"), "--output", str(root/"out.json")]), 2)
            self.assertEqual((root/"out.json").read_text(), "old")

    def test_duplicate_bundle_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            compare.compare_manifest({"candidate": {"id": "same"}, "references": [{"id": "same"}]})


if __name__ == "__main__":
    unittest.main()
