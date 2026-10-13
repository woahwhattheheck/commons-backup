"""Offline delivery regressions; all files, organizations and evidence are fictional."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from revenue.nm_ocs_tprm import cli, qualification
from revenue.nm_ocs_tprm.tests.test_qualification import payload as qualification_input
from revenue.nm_ocs_tprm.tests.test_tprm import assessment

ROOT = Path(__file__).resolve().parents[3]
CLI = Path(__file__).resolve().parents[1] / "cli.py"
PYTHON = [sys.executable] + (["-O"] if sys.flags.optimize else [])


def run_cli(*args: str, direct: bool = False) -> subprocess.CompletedProcess[str]:
    target = [str(CLI)] if direct else ["-m", "revenue.nm_ocs_tprm.cli"]
    return subprocess.run(PYTHON + target + list(args), cwd=ROOT,
                          capture_output=True, text=True, timeout=30, check=False)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "input.json"

    def test_finite_float_remains_loadable(self):
        self.path.write_text('{"value":1.25e2}', encoding="utf-8")
        self.assertEqual(cli._strict_load(self.path), {"value": 125.0})

    def test_nonfinite_exponents_and_constants_rejected(self):
        for token in ("1e999", "-1e999", "NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                self.path.write_text('{"value":' + token + '}', encoding="utf-8")
                with self.assertRaises(ValueError):
                    cli._strict_load(self.path)

    def test_nested_duplicate_keys_rejected(self):
        self.path.write_text('{"x":{"id":1,"id":2}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            cli._strict_load(self.path)

    def test_invalid_utf8_rejected(self):
        self.path.write_bytes(b'{"x":"\xff"}')
        with self.assertRaises(ValueError):
            cli._strict_load(self.path)

    def test_exact_byte_boundary(self):
        self.path.write_bytes(b'{}  ')
        self.assertEqual(cli._strict_load(self.path, max_bytes=4), {})
        with self.assertRaisesRegex(ValueError, "too large"):
            cli._strict_load(self.path, max_bytes=3)

    def test_bound_type_is_exact(self):
        self.path.write_bytes(b'{}')
        for bound in (True, 0, -1, 1.5):
            with self.subTest(bound=bound):
                with self.assertRaises(ValueError):
                    cli._strict_load(self.path, max_bytes=bound)

    def test_missing_file_rejected(self):
        with self.assertRaises(ValueError):
            cli._strict_load(self.path)

    def test_directory_rejected(self):
        self.path.mkdir()
        with self.assertRaises(ValueError):
            cli._strict_load(self.path)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink creation unavailable")
    def test_symlink_and_dangling_symlink_rejected(self):
        target = Path(self.tmp.name) / "real.json"
        target.write_bytes(b'{}')
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            cli._strict_load(self.path)
        target.unlink()
        with self.assertRaises(ValueError):
            cli._strict_load(self.path)

    def test_replaced_regular_file_before_open_rejected(self):
        self.path.write_bytes(b'{"source":"first"}')
        replacement = Path(self.tmp.name) / "replacement.json"
        replacement.write_bytes(b'{"source":"second"}')
        real_open = os.open
        def replacing_open(path, flags, *args, **kwargs):
            os.replace(replacement, self.path)
            return real_open(path, flags, *args, **kwargs)
        with patch.object(cli.os, "open", side_effect=replacing_open):
            with self.assertRaisesRegex(ValueError, "changed"):
                cli._strict_load(self.path)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink creation unavailable")
    def test_raced_in_symlink_rejected(self):
        self.path.write_bytes(b'{"source":"first"}')
        other = Path(self.tmp.name) / "other.json"
        other.write_bytes(b'{"source":"second"}')
        real_open = os.open
        def replacing_open(path, flags, *args, **kwargs):
            self.path.unlink()
            self.path.symlink_to(other)
            return real_open(path, flags, *args, **kwargs)
        with patch.object(cli.os, "open", side_effect=replacing_open):
            with self.assertRaises(ValueError):
                cli._strict_load(self.path)

    def test_same_file_changed_during_read_rejected(self):
        self.path.write_bytes(b'{"source":"first"}')
        real_fstat = os.fstat
        calls = 0
        def editing_fstat(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.path.write_bytes(b'{"source":"changed-after-read"}')
            return real_fstat(fd)
        with patch.object(cli.os, "fstat", side_effect=editing_fstat):
            with self.assertRaisesRegex(ValueError, "changed"):
                cli._strict_load(self.path)

    def test_parser_recursion_becomes_value_error(self):
        self.path.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
        with self.assertRaises(ValueError):
            cli._strict_load(self.path)

    def test_depth_boundary_is_explicit(self):
        self.path.write_text("[" * 64 + "0" + "]" * 64, encoding="utf-8")
        self.assertIsInstance(cli._strict_load(self.path), list)
        self.path.write_text("[" * 65 + "0" + "]" * 65, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nesting"):
            cli._strict_load(self.path)

    def test_escaped_quotes_and_braces_are_not_nesting(self):
        value = {"quoted": '[{"' * 200, "slashes": "\\" * 100}
        self.path.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(cli._strict_load(self.path), value)

    def test_parser_recursion_exception_is_also_normalized(self):
        self.path.write_bytes(b'{}')
        with patch.object(cli.json, "loads", side_effect=RecursionError("parser")):
            with self.assertRaisesRegex(ValueError, "nesting"):
                cli._strict_load(self.path)


class WriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "result.json"

    def test_output_appearing_during_serialization_is_preserved(self):
        original_dumps = json.dumps
        sentinel = b"OTHER WORKER RESULT\n"
        def concurrent_writer(*args, **kwargs):
            self.path.write_bytes(sentinel)
            return original_dumps(*args, **kwargs)
        with patch.object(cli.json, "dumps", side_effect=concurrent_writer):
            with self.assertRaisesRegex(ValueError, "overwrite"):
                cli._write(self.path, {"our_result": True})
        self.assertEqual(self.path.read_bytes(), sentinel)

    def test_existing_output_preserved(self):
        self.path.write_bytes(b"original\n")
        with self.assertRaises(ValueError):
            cli._write(self.path, {"new": True})
        self.assertEqual(self.path.read_bytes(), b"original\n")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink creation unavailable")
    def test_dangling_output_symlink_preserved(self):
        target = Path(self.tmp.name) / "not-created.json"
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            cli._write(self.path, {})
        self.assertTrue(self.path.is_symlink())
        self.assertFalse(target.exists())

    def test_serialization_failure_creates_nothing(self):
        with self.assertRaises((TypeError, ValueError)):
            cli._write(self.path, {"bad": object()})
        self.assertFalse(self.path.exists())

    def test_packet_above_emission_limit_creates_nothing(self):
        with patch.object(cli, "MAX_PACKET_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "verification size limit"):
                cli._write(self.path, {"value": "large"})
        self.assertFalse(self.path.exists())

    def test_original_pretty_output_format_preserved(self):
        value = {"z": "fiction", "a": [None, True, "\u03bb"]}
        cli._write(self.path, value)
        expected = (json.dumps(value, sort_keys=True, indent=2,
                               ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        self.assertEqual(self.path.read_bytes(), expected)


class QualificationBoundaryTests(unittest.TestCase):
    def test_non_string_status_is_validation_error(self):
        for key in ("controlling_packet", "prime_eligibility", "legal_scope"):
            for invalid in ([], {}, None, 0, True):
                with self.subTest(key=key, invalid=invalid):
                    source = qualification_input()
                    source[key]["status"] = invalid
                    with self.assertRaises(qualification.ValidationError):
                        qualification.compile_qualification(source)

    def test_malformed_source_verifies_false(self):
        for key in ("controlling_packet", "prime_eligibility", "legal_scope"):
            packet = qualification.compile_qualification(qualification_input())
            packet["source"][key]["status"] = []
            self.assertIs(qualification.verify_receipt(packet), False)

    def test_nonserializable_and_cyclic_packets_verify_false(self):
        for value in (object(), float("nan"), "\ud800"):
            packet = qualification.compile_qualification(qualification_input())
            packet["extra"] = value
            self.assertIs(qualification.verify_receipt(packet), False)
        packet = qualification.compile_qualification(qualification_input())
        packet["extra"] = packet
        self.assertIs(qualification.verify_receipt(packet), False)

    def test_authority_cannot_be_changed_with_recomputed_receipt(self):
        packet = qualification.compile_qualification(qualification_input())
        packet["authority"]["submission_authorized"] = True
        body = {k: v for k, v in packet.items() if k != "receipt_sha256"}
        packet["receipt_sha256"] = hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False).encode()).hexdigest()
        self.assertIs(qualification.verify_receipt(packet), False)


class ShellFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.inp = self.folder / "input.json"
        self.out = self.folder / "output.json"

    def test_invalid_input_returns_two_without_traceback(self):
        self.inp.write_text('{"a":1e999}', encoding="utf-8")
        for direct in (False, True):
            with self.subTest(direct=direct):
                result = run_cli("assessment", str(self.inp), str(self.out), direct=direct)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(self.out.exists())

    def test_invalid_status_returns_two_without_traceback(self):
        source = assessment()
        source["controls"][0]["status"] = []
        self.inp.write_text(json.dumps(source), encoding="utf-8")
        result = run_cli("assessment", str(self.inp), str(self.out))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.out.exists())

    def test_missing_input_returns_two_without_traceback(self):
        result = run_cli("verify-assessment", str(self.inp))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_failed_build_preserves_existing_output(self):
        self.inp.write_bytes(b'{"schema":"invalid"}')
        self.out.write_bytes(b"keep-original\n")
        result = run_cli("assessment", str(self.inp), str(self.out))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.out.read_bytes(), b"keep-original\n")

    def test_two_real_writers_leave_one_verified_result(self):
        self.inp.write_text(json.dumps(assessment()), encoding="utf-8")
        command = PYTHON + [str(CLI), "assessment", str(self.inp), str(self.out)]
        processes = [subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, text=True) for _ in range(2)]
        try:
            details = [p.communicate(timeout=30) for p in processes]
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()
                    p.communicate()
        self.assertEqual(sorted(p.returncode for p in processes), [0, 2], details)
        checked = run_cli("verify-assessment", str(self.out), direct=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_large_emitted_portfolio_is_consumable(self):
        source = {"schema": "tjlabs.nm-ocs-tprm.portfolio.v1", "portfolio_id": "fiction-large",
                  "assessments": [assessment("fiction-tenant-" + str(i % 2),
                                             "fiction-vendor-" + str(i)) for i in range(1800)]}
        self.inp.write_text(json.dumps(source, separators=(",", ":")), encoding="utf-8")
        self.assertLess(self.inp.stat().st_size, 4_000_000)
        built = run_cli("portfolio", str(self.inp), str(self.out))
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertGreater(self.out.stat().st_size, 4_000_000)
        checked = run_cli("verify-portfolio", str(self.out), direct=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_source_limit_not_relaxed_by_packet_allowance(self):
        self.inp.write_bytes(b" " * 4_000_001)
        result = run_cli("portfolio", str(self.inp), str(self.out))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("input too large", result.stderr)
        self.assertFalse(self.out.exists())

    def test_programmatic_main_keeps_exception_contract(self):
        self.inp.write_text(json.dumps(assessment()), encoding="utf-8")
        self.out.write_bytes(b"existing")
        with self.assertRaises(ValueError):
            cli.main(["assessment", str(self.inp), str(self.out)])


if __name__ == "__main__":
    unittest.main()
