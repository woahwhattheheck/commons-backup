from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from . import DealEconomicsError, canonical_json, parse_strict_json
from . import engine
from .test_authority import packet


ROOT = Path(__file__).resolve().parents[2]


def hostile_documents() -> dict[str, str]:
    return {
        "huge_integer": '{"x":' + ("9" * 5000) + "}",
        "lone_surrogate": '{"x":"\\ud800"}',
        "deep_nesting": ("[" * 2000) + "0" + ("]" * 2000),
    }


class StrictJsonBoundaryTests(unittest.TestCase):
    def test_engine_global_boundary_is_hardened_before_authority_import(self):
        self.assertIs(engine.parse_strict_json, parse_strict_json)
        self.assertIs(engine.canonical_json, canonical_json)

    def test_hostile_documents_normalize_to_domain_error(self):
        for name, document in hostile_documents().items():
            with self.subTest(name=name):
                with self.assertRaises(DealEconomicsError):
                    parse_strict_json(document)

    def test_canonical_json_rejects_lone_surrogate_and_resource_shape(self):
        with self.assertRaises(DealEconomicsError):
            canonical_json({"x": "\ud800"})

        value: object = 0
        for _ in range(2000):
            value = [value]
        with self.assertRaises(DealEconomicsError):
            canonical_json(value)


class RealCliStrictInputTests(unittest.TestCase):
    def _run(self, optimize: bool, *args: str) -> subprocess.CompletedProcess[str]:
        command = [sys.executable]
        if optimize:
            command.append("-O")
        command.extend(["-m", "revenue.service_deal_economics.cli", *args])
        return subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )

    def test_compile_and_verify_fail_closed_for_hostile_json_normal_and_optimized(self):
        valid_packet = json.dumps(packet(), sort_keys=True, separators=(",", ":"))
        for optimize in (False, True):
            for name, document in hostile_documents().items():
                with self.subTest(optimize=optimize, name=name, command="compile"):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        input_path = root / "hostile.json"
                        output_path = root / "report.json"
                        input_path.write_text(document, encoding="utf-8")
                        result = self._run(
                            optimize,
                            "compile",
                            str(input_path),
                            str(output_path),
                        )
                        self.assertEqual(result.returncode, 2, result)
                        self.assertEqual(result.stdout, "")
                        self.assertIn("ERROR:", result.stderr)
                        self.assertNotIn("Traceback", result.stderr)
                        self.assertFalse(output_path.exists())

                with self.subTest(optimize=optimize, name=name, command="verify"):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        input_path = root / "packet.json"
                        report_path = root / "hostile-report.json"
                        input_path.write_text(valid_packet, encoding="utf-8")
                        report_path.write_text(document, encoding="utf-8")
                        result = self._run(
                            optimize,
                            "verify",
                            str(input_path),
                            str(report_path),
                        )
                        self.assertEqual(result.returncode, 2, result)
                        self.assertEqual(result.stdout, "")
                        self.assertIn("ERROR:", result.stderr)
                        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
