# SPDX-License-Identifier: Apache-2.0
"""Independent source-boundary/CLI controls; no gameplay or runtime import.

Run with --runtime path/to/titan_runtime.py. --repair defaults to the peer's
same-directory transformer. --allow-mutant is only for deliberate negative
controls and disables the transformer blob pin, not runtime/method assertions.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import itertools
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

INPUT_BLOB = "b952c9c228ecbde592bf3d2df01638677abb0d24"
REPAIR_BLOB = "a5c2c131fd83d83d6be822556abce5723b464a50"
INPUT_METHOD = "b3bf094820b77a7b871b017c78fdfa18ef3663c94970c96c2eb572e5c693ff01"
OUTPUT_METHOD = "2aef22adfe3dd46782b71f9c6fefb4f4c38b2d8a8671766ea8e395b1adebeab6"


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def method_slice(data):
    # Independent location: this deliberately does not call the peer's locator.
    tree = ast.parse(data.decode("utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TitanAgent")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_seed_selected")
    lines = data.split(b"\n")
    first = sum(len(line) + 1 for line in lines[:fn.lineno - 1])
    last = sum(len(line) + 1 for line in lines[:fn.end_lineno])
    return first, last


class SourceIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = RUNTIME.read_bytes()
        if git_blob(cls.source) != INPUT_BLOB:
            raise ValueError("whole runtime source drift: rebind this receipt explicitly")
        raw = REPAIR.read_bytes()
        if not ALLOW_MUTANT and git_blob(raw) != REPAIR_BLOB:
            raise ValueError("owner transformer source drift: re-review required")
        spec = importlib.util.spec_from_file_location("seed_prefix_source_under_test", REPAIR)
        cls.peer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.peer)
        cls.start, cls.end = method_slice(cls.source)
        cls.method = cls.source[cls.start:cls.end]
        cls.shell = b"class TitanAgent:\n" + cls.method
        cls.repaired = cls.peer.repair(cls.source)

    def refuse(self, source):
        with self.assertRaises((ValueError, SyntaxError, UnicodeError)):
            self.peer.repair(source)

    def test_01_source_and_reviewed_method_hashes(self):
        self.assertEqual(git_blob(self.source), INPUT_BLOB)
        self.assertEqual(hashlib.sha256(self.method).hexdigest(), INPUT_METHOD)
        lo, hi = method_slice(self.repaired)
        self.assertEqual(hashlib.sha256(self.repaired[lo:hi]).hexdigest(), OUTPUT_METHOD)
        self.assertNotEqual(self.repaired, self.source)

    def test_02_exact_repeat_is_byte_identical(self):
        self.assertEqual(self.peer.repair(self.repaired), self.repaired)
        self.assertEqual(self.peer.repair(self.peer.repair(self.repaired)), self.repaired)

    def test_03_all_bytes_outside_method_preserved(self):
        lo, hi = method_slice(self.repaired)
        self.assertEqual(self.repaired[:lo], self.source[:self.start])
        self.assertEqual(self.repaired[hi:], self.source[self.end:])
        self.assertEqual(self.peer.extract_method(self.source), self.method)
        self.assertEqual(self.peer.method_bounds(self.source), (self.start, self.end))

    def test_04_unrelated_unicode_prefix_and_suffix_preserved(self):
        for label in ("plain", "café", "λ農🌾", "零\tµ"):
            with self.subTest(label=label):
                prefix = ("# " + label + "\n").encode()
                suffix = ("\n# " + label + "\nSENTINEL = 19\n").encode()
                result = self.peer.repair(prefix + self.shell + suffix)
                expected = prefix + self.peer.repair(self.shell) + suffix
                self.assertEqual(result, expected)
                self.assertEqual(self.peer.repair(result), result)

    def test_05_full_method_text_in_string_is_not_patched(self):
        prefix = b"DOC = " + repr(self.method.decode()).encode() + b"\n"
        self.assertEqual(self.peer.repair(prefix + self.shell), prefix + self.peer.repair(self.shell))

    def test_06_unrelated_class_is_not_patched(self):
        extra = b"class NotTitanAgent:\n" + self.method + b"\n"
        self.assertEqual(self.peer.repair(extra + self.shell), extra + self.peer.repair(self.shell))
        self.assertEqual(self.peer.repair(self.shell + b"\n" + extra),
                         self.peer.repair(self.shell) + b"\n" + extra)

    def test_07_missing_or_nested_class_refused(self):
        self.refuse(b"class SomethingElse:\n" + self.method)
        nested = b"if True:\n" + b"".join(b"    " + line for line in self.shell.splitlines(True))
        self.refuse(nested)

    def test_08_duplicate_top_level_class_refused(self):
        self.refuse(self.shell + b"\n" + self.shell)

    def test_09_duplicate_direct_method_refused(self):
        self.refuse(self.shell + self.method)

    def test_10_async_and_decorated_method_refused(self):
        self.refuse(self.shell.replace(b"    def _seed_selected", b"    async def _seed_selected", 1))
        self.refuse(self.shell.replace(b"    def _seed_selected", b"    @staticmethod\n    def _seed_selected", 1))

    def test_11_method_whitespace_comment_and_semantic_drift_refused(self):
        variations = [
            self.method.replace(b"return result", b"return selected"),
            self.method.replace(b"i+1:", b"i+2:"),
            self.method.replace(b"cfg.get(", b"cfg .get("),
            self.method.replace(b"        edits =", b"        # not reviewed\n        edits ="),
            self.method.replace(b"'BUY_ANIMAL'", b"'BUY_PRODUCT'"),
            self.method.replace(b"private['seeds']", b"obs['private']['seeds']"),
        ]
        for index, method in enumerate(variations):
            with self.subTest(index=index):
                self.assertNotEqual(method, self.method)
                self.refuse(b"class TitanAgent:\n" + method)

    def test_12_each_partial_repair_refused(self):
        changes = self.peer.CHANGES
        self.assertEqual(len(changes), 4)
        for bits in itertools.product((False, True), repeat=4):
            if all(bits) or not any(bits):
                continue
            with self.subTest(bits=bits):
                data = self.method.decode()
                for chosen, (old, new) in zip(bits, changes):
                    if chosen:
                        data = data.replace(old, new, 1)
                self.refuse(b"class TitanAgent:\n" + data.encode())

    def test_13_forged_idempotent_output_refused(self):
        forged = self.repaired.replace(b"return result", b"return selected", 1)
        self.assertNotEqual(forged, self.repaired)
        self.refuse(forged)

    def test_14_method_newlines_are_authenticated_not_normalized(self):
        self.refuse(self.shell.replace(b"\n", b"\r\n"))
        self.refuse(self.shell.rstrip(b"\n"))

    def test_15_crlf_outside_reviewed_method_preserved(self):
        prefix = b"# unrelated\r\n"
        suffix = b"\r\nTAIL = 7\r\n"
        self.assertEqual(self.peer.repair(prefix + self.shell + suffix),
                         prefix + self.peer.repair(self.shell) + suffix)

    def test_16_invalid_utf8_and_syntax_refused(self):
        self.refuse(b"\xff" + self.shell)
        self.refuse(self.shell + b"\ndef syntax_broken(:\n")

    def test_17_source_is_parsed_not_executed(self):
        prefix = b"raise RuntimeError('must never execute runtime')\n"
        self.assertEqual(self.peer.repair(prefix + self.shell), prefix + self.peer.repair(self.shell))

    def cli(self, source, output):
        options = ["-O"] if sys.flags.optimize else []
        return subprocess.run([sys.executable, *options, str(REPAIR), str(source), str(output)],
                              capture_output=True, text=True, timeout=10)

    def test_18_cli_creates_exact_scratch_output(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / "source.py", Path(td) / "output.py"
            source.write_bytes(self.source)
            result = self.cli(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), self.repaired)
            self.assertEqual(source.read_bytes(), self.source)
            self.assertEqual(result.stdout.strip(), hashlib.sha256(self.repaired).hexdigest())

    def test_19_cli_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / "source.py", Path(td) / "output.py"
            source.write_bytes(self.source)
            output.write_bytes(b"KEEP EXISTING BYTES\n")
            result = self.cli(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), b"KEEP EXISTING BYTES\n")
            self.assertEqual(source.read_bytes(), self.source)

    def test_20_cli_refuses_same_source_path(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source.py"
            source.write_bytes(self.source)
            result = self.cli(source, source)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_bytes(), self.source)

    def test_21_cli_refuses_symlink_to_source(self):
        with tempfile.TemporaryDirectory() as td:
            source, alias = Path(td) / "source.py", Path(td) / "alias.py"
            source.write_bytes(self.source)
            alias.symlink_to(source)
            result = self.cli(source, alias)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_bytes(), self.source)
            self.assertTrue(alias.is_symlink())

    def test_22_cli_drift_refusal_leaves_no_partial_output(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / "source.py", Path(td) / "output.py"
            source.write_bytes(self.source.replace(b"return result", b"return selected", 1))
            result = self.cli(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


def main():
    global RUNTIME, REPAIR, ALLOW_MUTANT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--repair", type=Path,
                        default=Path(__file__).with_name("repair_seed_funding_prefix.py"))
    parser.add_argument("--allow-mutant", action="store_true")
    args = parser.parse_args()
    RUNTIME, REPAIR, ALLOW_MUTANT = args.runtime.resolve(), args.repair.resolve(), args.allow_mutant
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SourceIntegrity))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
