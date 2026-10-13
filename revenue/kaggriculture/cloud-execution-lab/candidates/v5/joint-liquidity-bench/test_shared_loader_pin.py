# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import paired


ROOT = Path(__file__).resolve().parents[4]
LOADER = "20260907-offline-agent/evaluate.py"
HELPER = "cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py"
FACTORIAL = "cloud-execution-lab/candidates/v5/v4-added-features-factorial/paired.py"
CROSS = "cloud-execution-lab/candidates/v5/v4-added-features-factorial/feedstock_fourflag_cross.py"
LANDED_LOADER_BLOB = "387712c7b85dae4e624a3aab11df96f1ddb5b451"
PRE_CUSTODY_LOADER_BLOB = "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5"
LANDED_HELPER_BLOB = "719e3514d72bc7ea4c3e505836d16fcddae11019"
LANDED_FACTORIAL_BLOB = "198006f24936fe1ec8a6ac6d6d6cae015adf91cc"


def load_source(relative: str, name: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SharedLoaderPinTest(unittest.TestCase):
    def test_shared_pin_matches_landed_loader_bytes(self):
        self.assertEqual(paired.HARNESS_GIT_BLOBS[LOADER], LANDED_LOADER_BLOB)
        self.assertEqual(paired.git_blob_id(ROOT / LOADER), LANDED_LOADER_BLOB)

    def test_snapshot_harness_accepts_and_binds_landed_loader(self):
        with tempfile.TemporaryDirectory(prefix="v5-loader-pin-") as td:
            snapshot = Path(td) / "snapshot"
            receipt = paired.snapshot_harness(ROOT, snapshot, ["apex_v7"])
            self.assertEqual(
                receipt["repository_files"][LOADER]["git_blob"],
                LANDED_LOADER_BLOB,
            )
            self.assertEqual(
                (snapshot / LOADER).read_bytes(),
                (ROOT / LOADER).read_bytes(),
            )

            # The copied closure, not the mutable acquisition tree, is authority.
            # Any post-copy loader mutation must fail the same immutable pin check.
            (snapshot / LOADER).write_bytes(b"POISON\n")
            with self.assertRaisesRegex(ValueError, "Harness source mismatch"):
                paired.verify_git_blobs(snapshot, paired.HARNESS_GIT_BLOBS)

    def test_pre_custody_loader_pin_is_rejected(self):
        self.assertNotEqual(PRE_CUSTODY_LOADER_BLOB, LANDED_LOADER_BLOB)
        with self.assertRaisesRegex(ValueError, "Harness source mismatch"):
            paired.verify_git_blobs(ROOT, {LOADER: PRE_CUSTODY_LOADER_BLOB})

    def test_downstream_pin_chain_matches_landed_bytes(self):
        self.assertEqual(paired.git_blob_id(ROOT / HELPER), LANDED_HELPER_BLOB)
        factorial = load_source(FACTORIAL, "shared_pin_factorial")
        cross = load_source(CROSS, "shared_pin_cross")
        self.assertEqual(factorial.HELPER_GIT_BLOB, LANDED_HELPER_BLOB)
        self.assertEqual(paired.git_blob_id(ROOT / FACTORIAL), LANDED_FACTORIAL_BLOB)
        self.assertEqual(cross.FACTORIAL_GIT_BLOB, LANDED_FACTORIAL_BLOB)


if __name__ == "__main__":
    unittest.main()
