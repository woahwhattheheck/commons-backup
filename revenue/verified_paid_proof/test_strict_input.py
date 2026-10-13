from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from revenue.verified_paid_proof.compiler import compile_proof
from revenue.verified_paid_proof.core import (
    MAX_JSON_INTEGER_DIGITS,
    ProofError,
    _canonical_json,
    _int,
    strict_json_loads,
)
from revenue.verified_paid_proof.test_verified_paid_proof import base_record, grant_all

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def hostile_payloads() -> dict[str, str]:
    record = json.dumps(base_record(), ensure_ascii=True)
    surrogate_record = record.replace(
        '"Synthetic Buyer"',
        '"\\ud800"',
        1,
    )
    return {
        "integer_digit_limit": '{"schema_version":' + ("9" * 5000) + "}",
        "deep_valid_nesting": ('{"x":' * 10000) + "0" + ("}" * 10000),
        "escaped_lone_surrogate": surrogate_record,
        "escaped_lone_surrogate_key": '{"\\ud800":1}',
    }


class StrictInputBoundaryTests(unittest.TestCase):
    def test_library_translates_hostile_json_to_prooferror(self):
        for name, payload in hostile_payloads().items():
            with self.subTest(name=name):
                with self.assertRaises(ProofError):
                    strict_json_loads(payload)

    def test_direct_dictionary_rejects_lone_surrogate(self):
        record = base_record()
        record["customer"]["display_name"] = "\ud800"
        with self.assertRaises(ProofError):
            compile_proof(record)

    def test_direct_dictionary_rejects_oversized_python_integer(self):
        record = grant_all(base_record())
        record["payment"]["amount_minor"] = 10**4999
        with self.assertRaises(ProofError) as ctx:
            compile_proof(record)
        self.assertIsInstance(ctx.exception, ProofError)
        self.assertNotIn("Exceeds the limit", str(ctx.exception))

        boundary = 10 ** (MAX_JSON_INTEGER_DIGITS - 1)
        self.assertEqual(_int(boundary, "payment.amount_minor", minimum=0), boundary)
        with self.assertRaises(ProofError):
            _int(10**MAX_JSON_INTEGER_DIGITS, "payment.amount_minor", minimum=0)

    def test_canonical_json_rejects_nonfinite_and_non_utf8_values(self):
        for value in (
            {"value": float("nan")},
            {"value": "\ud800"},
        ):
            with self.subTest(value_type=type(value["value"]).__name__):
                with self.assertRaises(ProofError):
                    _canonical_json(value)

    def test_real_cli_fails_closed_without_traceback_in_both_modes(self):
        for optimized in (False, True):
            for name, payload in hostile_payloads().items():
                with self.subTest(optimized=optimized, name=name):
                    with tempfile.TemporaryDirectory() as tmp:
                        input_path = Path(tmp) / "hostile.json"
                        input_path.write_text(payload, encoding="utf-8")
                        command = [sys.executable]
                        if optimized:
                            command.append("-O")
                        command.extend(
                            [
                                "-m",
                                "revenue.verified_paid_proof.verified_paid_proof",
                                str(input_path),
                                "--json",
                            ]
                        )
                        result = subprocess.run(
                            command,
                            check=False,
                            capture_output=True,
                            text=True,
                            cwd=ROOT,
                        )
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertTrue(result.stderr.startswith("ERROR: "))
                    self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
