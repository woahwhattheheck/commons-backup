#!/usr/bin/env python3
"""Exact-byte loader regressions for the one canonical Forward-BUY decoder.

Run: python [-O] -B check_verified_loader.py [--decoder decoder.py] [--report out.json]
Only harmless synthetic modules are executed. Their expected pin is changed in
memory for each test, then restored. No synthetic result claims frozen R01 data.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PREDECESSOR = "9946e012fc8ca2d36dbe93cc6d0d128910a9d08d"
OLD = "    spec.loader.exec_module(mod)\n"
NEW = (
    "    # Execute the bytes authenticated above, not a second source read or a\n"
    "    # timestamp-valid cached bytecode file selected by the import loader.\n"
    '    exec(compile(raw, str(path), "exec"), mod.__dict__)\n'
)
DECODER = Path(__file__).with_name("decoder.py")
D = None


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load_decoder(path):
    spec = importlib.util.spec_from_file_location("fwd_census_loader_under_test", path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


class VerifiedLoader(unittest.TestCase):
    def load_fixture(self, path, raw):
        with patch.object(D, "EXPECTED_BLOB", blob(raw)):
            return D.load_exact(path)

    def test_plain_checked_source_retains_result_and_digest(self):
        raw = b"def load_tapes():\n    return [[{'market': []}]]\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.py"
            path.write_bytes(raw)
            tapes, digest = self.load_fixture(path, raw)
            self.assertEqual(tapes, [[{"market": []}]])
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
            self.assertEqual(path.read_bytes(), raw)

    def test_checked_source_keeps_module_file_context(self):
        raw = b"def load_tapes():\n    return (__file__, __name__)\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.py"
            path.write_bytes(raw)
            tapes, _ = self.load_fixture(path, raw)
            self.assertEqual(tapes, (str(path), "_frozen_r01_tapes"))

    def test_pep263_source_encoding_preserved(self):
        raw = b"# coding: latin-1\ndef load_tapes():\n    return ['caf\xe9']\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.py"
            path.write_bytes(raw)
            tapes, digest = self.load_fixture(path, raw)
            self.assertEqual(tapes, ["caf\u00e9"])
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_mismatched_source_cannot_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "executed"
            raw = ("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n").encode()
            path = Path(tmp) / "fixture.py"
            path.write_bytes(raw)
            with self.assertRaisesRegex(SystemExit, "SOURCE_MISMATCH"):
                D.load_exact(path)
            self.assertFalse(marker.exists())

    def test_mismatch_stops_before_import_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.py"
            path.write_bytes(b"def load_tapes(): return []\n")
            with patch.object(D.importlib.util, "spec_from_file_location") as spec:
                with self.assertRaisesRegex(SystemExit, "SOURCE_MISMATCH"):
                    D.load_exact(path)
                spec.assert_not_called()

    def test_same_timestamp_size_cache_cannot_replace_checked_bytes(self):
        cached = b"def load_tapes():\n    return ['cached']\n"
        checked = b"def load_tapes():\n    return ['source']\n"
        self.assertEqual(len(cached), len(checked))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.py"
            path.write_bytes(cached)
            timestamp = 1_700_000_000
            os.utime(path, (timestamp, timestamp))
            cache = Path(py_compile.compile(
                str(path), doraise=True, optimize=sys.flags.optimize,
                invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP))
            cache_bytes = cache.read_bytes()
            path.write_bytes(checked)
            os.utime(path, (timestamp, timestamp))
            tapes, digest = self.load_fixture(path, checked)
            self.assertEqual(tapes, ["source"])
            self.assertEqual(digest, hashlib.sha256(checked).hexdigest())
            self.assertEqual(cache.read_bytes(), cache_bytes)
            self.assertEqual(path.read_bytes(), checked)

    def test_source_replaced_after_hash_still_executes_checked_buffer(self):
        checked = b"def load_tapes():\n    return ['checked']\n"
        later = b"def load_tapes():\n    return ['reopened']\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.py"
            path.write_bytes(checked)
            original = D.importlib.util.spec_from_file_location
            def replace_then_spec(name, location):
                Path(location).write_bytes(later)
                return original(name, location)
            with patch.object(D.importlib.util, "spec_from_file_location", side_effect=replace_then_spec):
                tapes, digest = self.load_fixture(path, checked)
            self.assertEqual(tapes, ["checked"])
            self.assertEqual(digest, hashlib.sha256(checked).hexdigest())
            self.assertEqual(path.read_bytes(), later)  # replacement is test-owned

    def test_checked_source_exception_is_not_silently_suppressed(self):
        raw = b"raise RuntimeError('fixture failure')\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.py"
            path.write_bytes(raw)
            with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                self.load_fixture(path, raw)

    def test_only_loader_replacement_changes_peer_source(self):
        # Both the predecessor and the narrow successor must normalize to the
        # exact winning peer bytes. This forbids census/schema/policy changes.
        raw = DECODER.read_bytes()
        text = raw.decode("utf-8")
        if NEW in text:
            self.assertEqual(text.count(NEW), 1)
            raw = text.replace(NEW, OLD).encode("utf-8")
        self.assertEqual(blob(raw), PREDECESSOR)

    def test_existing_self_test_passes_normal_and_optimized(self):
        for flags in ([], ["-O"]):
            with self.subTest(flags=flags):
                proc = subprocess.run([sys.executable, *flags, "-B", str(DECODER), "--self-test"],
                                      capture_output=True, text=True, timeout=15, check=False)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("SELF_TEST_PASS checks=7", proc.stdout)


def main():
    global DECODER, D
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoder", type=Path, default=DECODER)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    DECODER = args.decoder.resolve()
    D = load_decoder(DECODER)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(VerifiedLoader))
    report = {
        "schema": "titan-v4-fwd-census-verified-loader/v1",
        "scope": "synthetic exact-byte loader regression; no gameplay",
        "decoder_blob": blob(DECODER.read_bytes()),
        "optimized": bool(sys.flags.optimize),
        "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "successful": result.wasSuccessful(),
        "failure_names": [str(test) for test, _ in result.failures],
        "error_names": [str(test) for test, _ in result.errors],
        "frozen_13x719_corpus": "NOT_RUN",
        "runtime_economics": "NOT_RUN",
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
