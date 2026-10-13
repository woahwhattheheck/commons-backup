#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import materialize_ablation_matrix as matrix


COMMIT = "a" * 40
FLAGS = matrix.SUSPECT_FLAGS


def _base_config() -> dict[str, object]:
    return {
        "consumer": "frozen",
        "seed": True,
        "redundant_hire": True,
        "market_pressure": True,
        "operating_stock": True,
        "idle_fertilizer": True,
        "crop_release": True,
        "early_capital": True,
        "nested": {"budget": 1.0, "order": ["SELL", "HIRE"]},
    }


def _write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


class MaterializeMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "TITAN-CONFIG.json"
        self.closure = self.root / "source.tar.gz"
        self.output = self.root / "matrix"
        _write(self.config, (json.dumps(_base_config()) + "\n").encode())
        _write(self.closure, b"immutable-current-source-closure\n")
        self.closure_sha = hashlib.sha256(self.closure.read_bytes()).hexdigest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def materialize(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "base_config_path": self.config,
            "source_closure_path": self.closure,
            "source_commit": COMMIT,
            "output_dir": self.output,
            "matrix_id": "matrix-test",
            "expected_source_closure_sha256": self.closure_sha,
        }
        arguments.update(overrides)
        return matrix.materialize_matrix(**arguments)  # type: ignore[arg-type]

    def test_materializes_exact_seven_arm_matrix(self) -> None:
        manifest = self.materialize()
        self.assertEqual(7, len(manifest["arms"]))
        self.assertEqual(6, len(manifest["comparisons"]))
        names = [arm["name"] for arm in manifest["arms"]]
        self.assertEqual([name for name, _ in matrix.ARM_SPECS], names)
        self.assertEqual(
            {"neutral-current-source"},
            {comparison["before"] for comparison in manifest["comparisons"]},
        )
        self.assertTrue((self.output / "ABLATION-MATRIX.json").is_file())

    def test_each_single_arm_differs_only_at_its_flag(self) -> None:
        manifest = self.materialize()
        by_name = {arm["name"]: arm for arm in manifest["arms"]}
        for flag in FLAGS:
            name = flag.replace("_", "-") + "-only"
            arm = by_name[name]
            self.assertEqual([flag], arm["enabled_suspect_flags"])
            self.assertEqual([f"$.{flag}"], arm["changed_paths_from_neutral"])
            payload = json.loads((self.output / arm["config_path"]).read_text())
            self.assertTrue(payload[flag])
            self.assertTrue(all(payload[item] is (item == flag) for item in FLAGS))

    def test_full_current_matches_base_semantics(self) -> None:
        manifest = self.materialize()
        full = manifest["arms"][-1]
        payload = json.loads((self.output / full["config_path"]).read_text())
        self.assertEqual(_base_config(), payload)
        self.assertEqual([], full["changed_paths_from_source"])
        self.assertEqual(sorted(f"$.{flag}" for flag in FLAGS), full["changed_paths_from_neutral"])

    def test_preserves_non_suspect_nested_config(self) -> None:
        manifest = self.materialize()
        for arm in manifest["arms"]:
            payload = json.loads((self.output / arm["config_path"]).read_text())
            self.assertEqual(_base_config()["nested"], payload["nested"])
            self.assertEqual("frozen", payload["consumer"])
            self.assertTrue(payload["redundant_hire"])

    def test_output_is_deterministic_across_directories(self) -> None:
        first = self.materialize()
        second_output = self.root / "matrix-two"
        second = self.materialize(output_dir=second_output)
        self.assertEqual(first, second)
        self.assertEqual(
            (self.output / "ABLATION-MATRIX.json").read_bytes(),
            (second_output / "ABLATION-MATRIX.json").read_bytes(),
        )
        for arm in first["arms"]:
            self.assertEqual(
                (self.output / arm["config_path"]).read_bytes(),
                (second_output / arm["config_path"]).read_bytes(),
            )

    def test_rejects_duplicate_json_key_without_output(self) -> None:
        _write(
            self.config,
            b'{"market_pressure":true,"market_pressure":true,"operating_stock":true,'
            b'"idle_fertilizer":true,"crop_release":true,"early_capital":true}',
        )
        with self.assertRaisesRegex(matrix.MatrixError, "duplicate JSON key"):
            self.materialize()
        self.assertFalse(self.output.exists())

    def test_rejects_missing_suspect_flag(self) -> None:
        config = _base_config()
        del config["crop_release"]
        _write(self.config, json.dumps(config).encode())
        with self.assertRaisesRegex(matrix.MatrixError, "missing suspect flag"):
            self.materialize()

    def test_rejects_non_boolean_suspect_flag(self) -> None:
        config = _base_config()
        config["early_capital"] = 1
        _write(self.config, json.dumps(config).encode())
        with self.assertRaisesRegex(matrix.MatrixError, "expected a boolean"):
            self.materialize()

    def test_rejects_partially_disabled_base(self) -> None:
        config = _base_config()
        config["operating_stock"] = False
        _write(self.config, json.dumps(config).encode())
        with self.assertRaisesRegex(matrix.MatrixError, "expected true"):
            self.materialize()

    def test_rejects_source_closure_hash_mismatch(self) -> None:
        with self.assertRaisesRegex(matrix.MatrixError, "SHA-256 mismatch"):
            self.materialize(expected_source_closure_sha256="0" * 64)
        self.assertFalse(self.output.exists())

    def test_rejects_existing_output_without_modifying_it(self) -> None:
        self.output.mkdir()
        marker = self.output / "KEEP"
        marker.write_text("unchanged")
        with self.assertRaisesRegex(matrix.MatrixError, "already exists"):
            self.materialize()
        self.assertEqual("unchanged", marker.read_text())
        self.assertEqual([marker], list(self.output.iterdir()))

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_rejects_symlink_output(self) -> None:
        target = self.root / "target"
        target.mkdir()
        self.output.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(matrix.MatrixError, "already exists"):
            self.materialize()
        self.assertEqual([], list(target.iterdir()))

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_rejects_symlink_config(self) -> None:
        real = self.root / "real-config.json"
        self.config.rename(real)
        self.config.symlink_to(real)
        with self.assertRaisesRegex(matrix.MatrixError, "non-symlink"):
            self.materialize()
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_rejects_symlink_source_closure(self) -> None:
        real = self.root / "real-source.tar.gz"
        self.closure.rename(real)
        self.closure.symlink_to(real)
        with self.assertRaisesRegex(matrix.MatrixError, "non-symlink"):
            self.materialize()
        self.assertFalse(self.output.exists())

    def test_rejects_invalid_commit_and_matrix_id(self) -> None:
        with self.assertRaisesRegex(matrix.MatrixError, "source_commit"):
            self.materialize(source_commit="main")
        with self.assertRaisesRegex(matrix.MatrixError, "matrix_id"):
            self.materialize(matrix_id="bad matrix id")

    def test_cli_success_and_invalid_exit_codes(self) -> None:
        script = Path(matrix.__file__).resolve()
        successful = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base-config",
                str(self.config),
                "--source-closure",
                str(self.closure),
                "--source-commit",
                COMMIT,
                "--expected-source-closure-sha256",
                self.closure_sha,
                "--output-dir",
                str(self.output),
                "--matrix-id",
                "cli-test",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, successful.returncode, successful.stderr)
        self.assertEqual(
            {"arms": 7, "comparisons": 6, "matrix_id": "cli-test", "status": "MATERIALIZED"},
            json.loads(successful.stdout),
        )
        failed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base-config",
                str(self.config),
                "--source-closure",
                str(self.closure),
                "--source-commit",
                "not-a-commit",
                "--output-dir",
                str(self.root / "bad-output"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(2, failed.returncode)
        self.assertIn("INVALID:", failed.stderr)
        self.assertFalse((self.root / "bad-output").exists())


if __name__ == "__main__":
    unittest.main()
