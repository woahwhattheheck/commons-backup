from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from matrix_runner import MATRIX_RESULT_SCHEMA, MATRIX_SCHEMA, run_matrix  # noqa: E402
from realized_fertilizer import canonical_sha256  # noqa: E402
from test_realized_fertilizer import candidate_trace, control_trace  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def pair_files(root: Path, pair_id: str, seed: int) -> dict[str, str]:
    control = control_trace()
    candidate = candidate_trace()
    control["identity"]["seed"] = seed  # type: ignore[index]
    candidate["identity"]["seed"] = seed  # type: ignore[index]
    control_name = f"traces/{pair_id}.control.json"
    candidate_name = f"traces/{pair_id}.fertilized.json"
    write_json(root / control_name, control)
    write_json(root / candidate_name, candidate)
    return {"id": pair_id, "control": control_name, "fertilized": candidate_name}


class MatrixRunnerTests(unittest.TestCase):
    def test_admits_when_every_distinct_pair_certifies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "schema": MATRIX_SCHEMA,
                "pairs": [
                    pair_files(root, "seed-718", 718),
                    pair_files(root, "seed-719", 719),
                ],
            }
            result = run_matrix(manifest, root=root)
            self.assertEqual(result["schema"], MATRIX_RESULT_SCHEMA)
            self.assertEqual(result["decision"], "ADMIT")
            self.assertEqual(result["pair_count"], 2)
            self.assertEqual(result["certified_count"], 2)
            self.assertEqual(result["rejected_count"], 0)

    def test_rejects_whole_matrix_when_one_pair_does_not_realize_sale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = pair_files(root, "seed-718", 718)
            second = pair_files(root, "seed-719", 719)
            candidate = json.loads((root / second["fertilized"]).read_text())
            for row in candidate["snapshots"]:
                if row["tick"] >= 9:
                    row["sold_units"] = 1
                    row["cash"] = 56
            write_json(root / second["fertilized"], candidate)
            result = run_matrix(
                {"schema": MATRIX_SCHEMA, "pairs": [first, second]}, root=root
            )
            self.assertEqual(result["decision"], "REJECT")
            self.assertEqual(result["certified_count"], 1)
            self.assertIn("pair-rejected:seed-719", result["reasons"])

    def test_missing_trace_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pair = pair_files(root, "seed-718", 718)
            (root / pair["fertilized"]).unlink()
            result = run_matrix({"schema": MATRIX_SCHEMA, "pairs": [pair]}, root=root)
            self.assertEqual(result["decision"], "REJECT")
            self.assertTrue(
                result["pairs"][0]["reasons"][0].startswith("trace-read-error:")
            )

    def test_parent_traversal_is_rejected(self) -> None:
        manifest = {
            "schema": MATRIX_SCHEMA,
            "pairs": [
                {
                    "id": "bad",
                    "control": "../control.json",
                    "fertilized": "candidate.json",
                }
            ],
        }
        result = run_matrix(manifest, root=Path("/tmp"))
        self.assertEqual(result["decision"], "REJECT")
        self.assertTrue(result["reasons"][0].startswith("invalid-manifest:"))

    def test_duplicate_pair_id_is_rejected(self) -> None:
        manifest = {
            "schema": MATRIX_SCHEMA,
            "pairs": [
                {"id": "same", "control": "a.json", "fertilized": "b.json"},
                {"id": "same", "control": "c.json", "fertilized": "d.json"},
            ],
        }
        result = run_matrix(manifest, root=Path("/tmp"))
        self.assertIn("duplicate pair id", result["reasons"][0])

    def test_trace_path_reuse_is_rejected(self) -> None:
        manifest = {
            "schema": MATRIX_SCHEMA,
            "pairs": [
                {"id": "one", "control": "a.json", "fertilized": "b.json"},
                {"id": "two", "control": "a.json", "fertilized": "c.json"},
            ],
        }
        result = run_matrix(manifest, root=Path("/tmp"))
        self.assertIn("trace file reused", result["reasons"][0])

    def test_duplicate_comparison_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = pair_files(root, "one", 718)
            second = pair_files(root, "two", 718)
            result = run_matrix(
                {"schema": MATRIX_SCHEMA, "pairs": [first, second]}, root=root
            )
            self.assertEqual(result["decision"], "REJECT")
            self.assertIn(
                "duplicate-comparison-identity", result["pairs"][1]["reasons"]
            )

    def test_result_hash_is_deterministic_and_self_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "schema": MATRIX_SCHEMA,
                "pairs": [pair_files(root, "seed-718", 718)],
            }
            first = run_matrix(manifest, root=root)
            second = run_matrix(copy.deepcopy(manifest), root=root)
            self.assertEqual(first, second)
            claimed = first.pop("result_sha256")
            self.assertEqual(claimed, canonical_sha256(first))

    def test_unknown_manifest_key_is_rejected(self) -> None:
        result = run_matrix(
            {"schema": MATRIX_SCHEMA, "pairs": [], "surprise": 1},
            root=Path("/tmp"),
        )
        self.assertIn("extra=surprise", result["reasons"][0])

    def test_cli_admits_valid_manifest_and_writes_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "matrix.json"
            output_path = root / "result.json"
            write_json(
                manifest_path,
                {
                    "schema": MATRIX_SCHEMA,
                    "pairs": [pair_files(root, "seed-718", 718)],
                },
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "matrix_runner.py"),
                    str(manifest_path),
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8"))["decision"],
                "ADMIT",
            )


if __name__ == "__main__":
    unittest.main()
