from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "restore_vendor.py"
SPEC = importlib.util.spec_from_file_location("restore_vendor", SCRIPT)
assert SPEC and SPEC.loader
restore_vendor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore_vendor)


class RestoreVendorTest(unittest.TestCase):
    def test_detects_then_restores_exact_pinned_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            package = repo / "revenue" / "agents_for_humans"
            local = package / "vendor" / "autopsy" / "RUNBOOK.md"
            local.parent.mkdir(parents=True)
            local.write_bytes(b"drift\n")
            pinned = b"attributed bytes\n"
            sha = restore_vendor.blob_id(pinned)
            manifest = package / "SOURCE_MANIFEST.json"
            manifest.write_text(
                json.dumps(
                    {
                        "upstream_files": [
                            {"local_path": "vendor/autopsy/RUNBOOK.md", "git_blob": sha}
                        ]
                    }
                ),
                encoding="utf-8",
            )

            def reader(_repo: Path, requested: str) -> bytes:
                self.assertEqual(requested, sha)
                return pinned

            expected = "revenue/agents_for_humans/vendor/autopsy/RUNBOOK.md"
            self.assertEqual(
                restore_vendor.reconcile(
                    package_root=package,
                    repo_root=repo,
                    manifest_path=manifest,
                    blob_reader=reader,
                ),
                [expected],
            )
            self.assertEqual(local.read_bytes(), b"drift\n")
            self.assertEqual(
                restore_vendor.reconcile(
                    package_root=package,
                    repo_root=repo,
                    manifest_path=manifest,
                    apply=True,
                    blob_reader=reader,
                ),
                [expected],
            )
            self.assertEqual(local.read_bytes(), pinned)
            self.assertEqual(
                restore_vendor.reconcile(
                    package_root=package,
                    repo_root=repo,
                    manifest_path=manifest,
                    blob_reader=reader,
                ),
                [],
            )

    def test_rejects_manifest_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            package = repo / "revenue" / "agents_for_humans"
            package.mkdir(parents=True)
            pinned = b"x"
            sha = restore_vendor.blob_id(pinned)
            manifest = package / "SOURCE_MANIFEST.json"
            manifest.write_text(
                json.dumps(
                    {"upstream_files": [{"local_path": "../escape", "git_blob": sha}]}
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unsafe manifest local_path"):
                restore_vendor.reconcile(
                    package_root=package,
                    repo_root=repo,
                    manifest_path=manifest,
                    blob_reader=lambda _repo, _sha: pinned,
                )


if __name__ == "__main__":
    unittest.main()
