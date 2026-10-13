# SPDX-License-Identifier: Apache-2.0
"""Focused custody regressions for the V5 joint-liquidity launcher."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "paired.py"
SPEC = importlib.util.spec_from_file_location("_v5_joint_liquidity_paired", SOURCE)
paired = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(paired)


def _write_file(root: Path, relative: str, data: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _tiny_baseline(path: Path) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, data in (("main.py", b"def agent(o,c=None): return {}\n"),
                           ("frozen_selected.py", b"# frozen\n")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


class JointLiquidityCustodyTests(unittest.TestCase):
    def test_only_published_overlay_sha_is_accepted(self):
        self.assertEqual(
            paired.published_overlay_sha256(paired.OVERLAY_SHA256),
            paired.OVERLAY_SHA256,
        )
        for value in (
            "0" * 64,
            paired.OVERLAY_SHA256.upper(),
            paired.OVERLAY_SHA256[:-1],
            None,
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "must match published"):
                    paired.published_overlay_sha256(value)

    def test_forged_self_hash_fails_before_any_output_for_both_candidate_paths(self):
        forged = "0" * 64
        for mode in ("--overlay", "--candidate"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(
                prefix="joint-liquidity-custody-"
            ) as raw:
                root = Path(raw)
                output = root / "evidence"
                argv = [
                    "paired.py",
                    "--kg-root", str(root / "unused-kg"),
                    "--engine-dir", str(root / "unused-engine"),
                    "--baseline", str(root / "unused-v4.tar.gz"),
                    mode, str(root / "attacker-controlled-input"),
                    "--overlay-sha256", forged,
                    "--output", str(output),
                ]
                with patch.object(sys, "argv", argv):
                    with self.assertRaisesRegex(ValueError, "must match published"):
                        paired.main()
                self.assertFalse(output.exists())

    def test_repository_blob_authentication_rejects_any_tampered_member(self):
        with tempfile.TemporaryDirectory(prefix="joint-liquidity-harness-") as raw:
            root = Path(raw)
            first = _write_file(root, "a.py", b"print('a')\n")
            second = _write_file(root, "nested/b.py", b"print('b')\n")
            pins = {"a.py": paired.git_blob_id(first), "nested/b.py": paired.git_blob_id(second)}
            authenticated = paired.verify_git_blobs(root, pins)
            self.assertEqual(set(authenticated), set(pins))
            for relative in pins:
                with self.subTest(relative=relative):
                    target = root / relative
                    original = target.read_bytes()
                    target.write_bytes(original + b"# tampered\n")
                    with self.assertRaisesRegex(ValueError, "Harness source mismatch"):
                        paired.verify_git_blobs(root, pins)
                    target.write_bytes(original)

    def test_upstream_manifest_hashes_are_authority_not_observations(self):
        with tempfile.TemporaryDirectory(prefix="joint-liquidity-upstream-") as raw:
            root = Path(raw)
            payload = b"loader authority\n"
            _write_file(root, "cloud-pack/upstream/agent.py", payload)
            manifest = {
                "files": {
                    "agent.py": {"sha256": hashlib.sha256(payload).hexdigest()}
                }
            }
            _write_file(
                root,
                "cloud-pack/upstream/manifest.json",
                (json.dumps(manifest) + "\n").encode(),
            )
            with patch.object(paired, "UPSTREAM_MANIFEST", "cloud-pack/upstream/manifest.json"):
                verified = paired.verify_upstream_loader(root)
                self.assertEqual(
                    verified["cloud-pack/upstream/agent.py"],
                    hashlib.sha256(payload).hexdigest(),
                )
                (root / "cloud-pack/upstream/agent.py").write_bytes(b"attacker\n")
                with self.assertRaisesRegex(ValueError, "Upstream loader source mismatch"):
                    paired.verify_upstream_loader(root)

    def test_harness_tamper_fails_before_output_directory_is_created(self):
        with tempfile.TemporaryDirectory(prefix="joint-liquidity-preoutput-") as raw:
            root = Path(raw)
            kg = root / "kg"
            engine = root / "engine"
            kg.mkdir()
            engine.mkdir()
            harness = _write_file(kg, "harness.py", b"print('trusted')\n")
            upstream = b"upstream\n"
            _write_file(kg, "cloud-pack/upstream/agent.py", upstream)
            manifest_path = _write_file(
                kg,
                "cloud-pack/upstream/manifest.json",
                (json.dumps({"files": {"agent.py": {
                    "sha256": hashlib.sha256(upstream).hexdigest()
                }}}) + "\n").encode(),
            )
            pins = {
                "harness.py": paired.git_blob_id(harness),
                "cloud-pack/upstream/manifest.json": paired.git_blob_id(manifest_path),
            }
            baseline = root / "baseline.tar.gz"
            _tiny_baseline(baseline)
            output = root / "evidence"
            # Change an authenticated executable only after deriving its authority.
            harness.write_bytes(b"print('attacker')\n")
            argv = [
                "paired.py",
                "--kg-root", str(kg),
                "--engine-dir", str(engine),
                "--baseline", str(baseline),
                "--candidate", str(root / "unused-candidate.tar.gz"),
                "--overlay-sha256", paired.OVERLAY_SHA256,
                "--output", str(output),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(paired, "BASELINE_SHA256", paired.digest(baseline)),
                patch.object(paired, "HARNESS_GIT_BLOBS", pins),
                patch.object(
                    paired,
                    "BRIDGE_SUPPORT_CORE",
                    ("harness.py", "cloud-pack/upstream/manifest.json"),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "Harness source mismatch"):
                    paired.main()
            self.assertFalse(output.exists())

    def test_snapshot_freezes_authenticated_policy_and_support_bytes(self):
        with tempfile.TemporaryDirectory(prefix="joint-liquidity-snapshot-") as raw:
            root = Path(raw)
            kg = root / "kg"
            snapshot = root / "snapshot"
            kg.mkdir()
            policy = b"policy trusted\n"
            support = b"support trusted\n"
            upstream = b"upstream trusted\n"
            notice = b"notice trusted\n"
            bridge = _write_file(
                kg, paired.BANK + "/reference_policies.py", b"bridge trusted\n"
            )
            registry = {
                "policies": {
                    "demo": {
                        "root": "vendor/demo",
                        "entry": "policy.py",
                        "files": {
                            "policy.py": hashlib.sha256(policy).hexdigest(),
                        },
                        "notices": {
                            "NOTICE": hashlib.sha256(notice).hexdigest(),
                        },
                    }
                }
            }
            registry_path = _write_file(
                kg,
                paired.BANK + "/REFERENCE-POLICIES.json",
                (json.dumps(registry) + "\n").encode(),
            )
            support_path = _write_file(kg, "support.py", support)
            manifest = {
                "files": {
                    "agent.py": {"sha256": hashlib.sha256(upstream).hexdigest()}
                }
            }
            manifest_path = _write_file(
                kg,
                "cloud-pack/upstream/manifest.json",
                (json.dumps(manifest) + "\n").encode(),
            )
            _write_file(kg, "cloud-pack/upstream/agent.py", upstream)
            _write_file(kg, "vendor/demo/policy.py", policy)
            _write_file(kg, "NOTICE", notice)
            pins = {
                paired.BANK + "/reference_policies.py": paired.git_blob_id(bridge),
                paired.BANK + "/REFERENCE-POLICIES.json": paired.git_blob_id(registry_path),
                "support.py": paired.git_blob_id(support_path),
                paired.UPSTREAM_MANIFEST: paired.git_blob_id(manifest_path),
            }
            with (
                patch.object(paired, "HARNESS_GIT_BLOBS", pins),
                patch.object(
                    paired,
                    "BRIDGE_SUPPORT_CORE",
                    ("support.py", paired.UPSTREAM_MANIFEST),
                ),
            ):
                receipt = paired.snapshot_harness(kg, snapshot, ["demo"])
                (kg / "support.py").write_bytes(b"attacker support\n")
                (kg / "vendor/demo/policy.py").write_bytes(b"attacker policy\n")
                self.assertEqual((snapshot / "support.py").read_bytes(), support)
                self.assertEqual((snapshot / "vendor/demo/policy.py").read_bytes(), policy)
                self.assertEqual(
                    receipt["opponent_policy_sha256"]["demo"]["vendor/demo/policy.py"],
                    hashlib.sha256(policy).hexdigest(),
                )
                authenticated = paired.authenticate_harness(snapshot)
                self.assertEqual(
                    authenticated["repository_files"]["support.py"]["git_blob"],
                    pins["support.py"],
                )

    def test_live_repository_harness_matches_published_pins_when_available(self):
        kg_root = HERE.parents[3]
        if not (kg_root / "cloud-pack").is_dir():
            self.skipTest("full Kaggriculture source tree is not present")
        result = paired.authenticate_harness(kg_root)
        self.assertEqual(set(result["repository_files"]), set(paired.HARNESS_GIT_BLOBS))
        self.assertEqual(
            set(result["opponent_support_sha256"]),
            set(paired.BRIDGE_SUPPORT_CORE) | set(result["upstream_files"]),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
