from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from preflight import ALLOWED_PHASES, DEFAULT_MANIFEST, load_manifest, repo_root_from, validate
from sample_run import resolve_command, run_sample


class OperatorHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest(DEFAULT_MANIFEST)
        cls.root = repo_root_from()

    def test_manifest_covers_all_phases_and_has_unique_assets(self) -> None:
        assets = self.manifest["assets"]
        self.assertEqual(set(self.manifest["phases"]), ALLOWED_PHASES)
        ids = [asset["asset_id"] for asset in assets]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(assets), 15)

    def test_preflight_resolves_snapshot_assets_in_checkout(self) -> None:
        result = validate(self.manifest, self.root)
        self.assertTrue(result["ok"], result["errors"])
        self.assertGreaterEqual(result["executable_assets"], 8)
        self.assertEqual(result["resolved_paths"], len(self.manifest["assets"]) - 1)

    def test_pending_readout_is_explicit_not_silently_working(self) -> None:
        pending = [
            asset for asset in self.manifest["assets"]
            if asset["status"] == "pending_at_snapshot"
        ]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["work_order"], "UIOWA-088")
        self.assertEqual(pending[0]["path"], "")
        self.assertIn("refresh current main", pending[0]["operator_action"])

    def test_every_sample_script_exists_and_stays_inside_repo(self) -> None:
        executable = [asset for asset in self.manifest["assets"] if asset.get("sample_commands")]
        self.assertGreaterEqual(len(executable), 8)
        for asset in executable:
            workdir = (self.root / asset["working_dir"]).resolve()
            workdir.relative_to(self.root.resolve())
            for command in asset["sample_commands"]:
                script = (workdir / command[0]).resolve()
                script.relative_to(self.root.resolve())
                self.assertTrue(script.is_file(), f"missing {script}")

    def test_output_placeholder_resolution(self) -> None:
        command = ["tool.py", "--out", "${OUT}/result.json"]
        resolved = resolve_command(command, Path("/tmp/uiowa-100"))
        self.assertEqual(resolved, ["tool.py", "--out", "/tmp/uiowa-100/result.json"])

    def test_dry_run_builds_receipt_without_executing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = run_sample(
                self.manifest,
                self.root,
                Path(tmp),
                timeout=1.0,
                dry_run=True,
            )
            self.assertTrue(receipt["success"])
            self.assertGreaterEqual(len(receipt["steps"]), 10)
            self.assertTrue(all(step["returncode"] is None for step in receipt["steps"]))
            self.assertTrue((Path(tmp) / "sample-run-receipt.json").is_file())

    def test_university_inputs_are_visible_not_invented(self) -> None:
        inputs = self.manifest["required_university_inputs"]
        self.assertGreaterEqual(len(inputs), 8)
        joined = " ".join(inputs).lower()
        self.assertIn("actual process documents", joined)
        self.assertIn("participant", joined)
        self.assertIn("maturity-anchor", joined)

    def test_manifest_is_valid_json_round_trip(self) -> None:
        encoded = json.dumps(self.manifest, sort_keys=True)
        self.assertEqual(json.loads(encoded)["schema"], "uiowa.operator-handoff.v1")


if __name__ == "__main__":
    unittest.main()
