from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE / "examples"
sys.path.insert(0, str(HERE))

from matrix_runner import MATRIX_SCHEMA, run_matrix  # noqa: E402
from realized_fertilizer import (  # noqa: E402
    TRACE_SCHEMA,
    canonical_sha256,
    certify_realized_fertilizer,
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class GoldenExampleFixtureTests(unittest.TestCase):
    def test_checked_in_pair_certifies_complete_realized_cycle(self) -> None:
        control = load(EXAMPLES / "control.json")
        candidate = load(EXAMPLES / "fertilized.json")
        self.assertEqual(control["schema"], TRACE_SCHEMA)
        self.assertEqual(candidate["schema"], TRACE_SCHEMA)

        certificate = certify_realized_fertilizer(control, candidate)
        self.assertEqual(certificate["decision"], "CERTIFIED")
        self.assertEqual(certificate["reasons"], [])
        self.assertEqual(
            {
                field: certificate["deltas"][field]
                for field in (
                    "produced_units",
                    "harvested_units",
                    "deposited_units",
                    "sold_units",
                )
            },
            {
                "produced_units": 1,
                "harvested_units": 1,
                "deposited_units": 1,
                "sold_units": 1,
            },
        )
        self.assertEqual(certificate["deltas"]["cash"], 6)
        self.assertEqual(
            certificate["milestones"],
            {
                "fertilizer_tick": 1,
                "production_tick": 3,
                "harvest_tick": 5,
                "deposit_tick": 7,
                "sale_tick": 9,
            },
        )
        claimed = certificate.pop("certificate_sha256")
        self.assertEqual(claimed, canonical_sha256(certificate))

    def test_checked_in_matrix_admits_and_self_hashes(self) -> None:
        manifest = load(EXAMPLES / "matrix.json")
        self.assertEqual(manifest["schema"], MATRIX_SCHEMA)
        result = run_matrix(manifest, root=EXAMPLES)
        self.assertEqual(result["decision"], "ADMIT")
        self.assertEqual(result["pair_count"], 1)
        self.assertEqual(result["certified_count"], 1)
        self.assertEqual(result["rejected_count"], 0)
        self.assertEqual(result["pairs"][0]["id"], "seed-718-opponent-c")
        self.assertEqual(result["pairs"][0]["decision"], "CERTIFIED")
        claimed = result.pop("result_sha256")
        self.assertEqual(claimed, canonical_sha256(result))

    def test_certificate_cli_accepts_checked_in_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "certificate.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "realized_fertilizer.py"),
                    "--control",
                    str(EXAMPLES / "control.json"),
                    "--candidate",
                    str(EXAMPLES / "fertilized.json"),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(load(output)["decision"], "CERTIFIED")

    def test_matrix_cli_accepts_checked_in_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "matrix-result.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "matrix_runner.py"),
                    str(EXAMPLES / "matrix.json"),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(load(output)["decision"], "ADMIT")


if __name__ == "__main__":
    unittest.main()
