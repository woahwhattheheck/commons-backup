from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from revenue.lawrence_youth_ai_training import gate
from revenue.lawrence_youth_ai_training._test_support import *


class InputAndCliTests(unittest.TestCase):
    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(gate.QualificationInputError):
            gate.strict_json_loads(b'{"a":1,"a":2}', "duplicate")

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(gate.QualificationInputError):
            gate.strict_json_loads(b'{"a":NaN}', "nonfinite")

    def test_hostile_valid_json_limits_fail_closed(self):
        cases = {
            "over_limit_integer": b'{"n":' + (b"9" * 5000) + b"}",
            "deep_nesting": (b"[" * 10000) + b"0" + (b"]" * 10000),
            "surrogate_value": b'{"value":"\\ud800"}',
            "surrogate_key": b'{"\\ud800":"value"}',
        }
        for name, raw in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(gate.QualificationInputError):
                    gate.strict_json_loads(raw, name)

    def test_direct_canonicalization_rejects_surrogates_and_deep_data(self):
        with self.assertRaises(gate.QualificationInputError):
            gate.digest({"value": "\ud800"})
        with self.assertRaises(gate.QualificationInputError):
            gate.digest({"\ud800": "value"})
        value = 0
        for _ in range(2000):
            value = [value]
        with self.assertRaises(gate.QualificationInputError):
            gate.digest(value)

    def test_cli_hostile_json_exits_two_without_traceback_normal_and_optimized(self):
        cases = {
            "over_limit_integer": b'{"n":' + (b"9" * 5000) + b"}",
            "deep_nesting": (b"[" * 10000) + b"0" + (b"]" * 10000),
            "surrogate_value": b'{"value":"\\ud800"}',
            "surrogate_key": b'{"\\ud800":"value"}',
        }
        for optimized in (False, True):
            for name, raw in cases.items():
                with self.subTest(name=name, optimized=optimized):
                    with tempfile.TemporaryDirectory() as temp:
                        path = Path(temp) / "snapshot.json"
                        path.write_bytes(raw)
                        command = [sys.executable]
                        if optimized:
                            command.append("-O")
                        command.extend(
                            [
                                "-m",
                                "revenue.lawrence_youth_ai_training.cli",
                                "evaluate-current",
                                str(path),
                                "--expected-rfp-sha256",
                                SHA,
                            ]
                        )
                        proc = subprocess.run(
                            command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            check=False,
                        )
                    self.assertEqual(proc.returncode, 2)
                    payload = json.loads(proc.stdout)
                    self.assertFalse(payload["verified"])
                    self.assertIn("error", payload)
                    self.assertNotIn("Traceback", proc.stdout)
                    self.assertNotIn("Traceback", proc.stderr)

    def test_old_current_clock_flag_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "snapshot.json"
            path.write_text(json.dumps(snapshot()), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "revenue.lawrence_youth_ai_training.cli",
                    "evaluate-current",
                    str(path),
                    "--expected-rfp-sha256",
                    SHA,
                    "--evaluated-at",
                    NOW,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unrecognized arguments", proc.stderr)

    def test_cli_historical_is_explicitly_non_authorizing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "snapshot.json"
            path.write_text(json.dumps(snapshot()), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "revenue.lawrence_youth_ai_training.cli",
                    "evaluate-historical",
                    str(path),
                    "--expected-rfp-sha256",
                    SHA,
                    "--evaluated-at",
                    NOW,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        self.assertEqual(proc.returncode, 3)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["receipt"]["current_authority"])
        self.assertEqual(payload["receipt"]["decision"], gate.HOLD)
