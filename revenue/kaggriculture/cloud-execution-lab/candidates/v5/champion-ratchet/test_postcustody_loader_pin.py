#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
KG_ROOT = HERE.parents[3]
LOADER_REL = "20260907-offline-agent/evaluate.py"
LANDED_LOADER_BLOB = "387712c7b85dae4e624a3aab11df96f1ddb5b451"
PRE_CUSTODY_LOADER_BLOB = "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5"


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


G = load_module(HERE / "champion_gate.py", "champion_postcustody_gate")
R = load_module(HERE.parent / "promotion-gate" / "release_transaction.py", "champion_postcustody_release")


class PostCustodyLoaderPinTest(unittest.TestCase):
    def test_default_champion_harness_authenticates_landed_loader(self):
        self.assertEqual(LANDED_LOADER_BLOB, G.REPO_GIT_BLOBS[LOADER_REL])
        self.assertEqual(LANDED_LOADER_BLOB, git_blob((KG_ROOT / LOADER_REL).read_bytes()))
        receipt = G.authenticate_repo(KG_ROOT)
        self.assertEqual(LANDED_LOADER_BLOB, receipt[LOADER_REL]["git_blob"])

    def test_pre_custody_loader_authority_is_rejected(self):
        stale = dict(G.REPO_GIT_BLOBS)
        stale[LOADER_REL] = PRE_CUSTODY_LOADER_BLOB
        with self.assertRaisesRegex(G.ChampionError, "repo authority drift"):
            G.authenticate_repo(KG_ROOT, repo_pins=stale)

    def test_release_transaction_pins_exact_current_champion_gate(self):
        actual = git_blob((HERE / "champion_gate.py").read_bytes())
        self.assertEqual(actual, R.CHAMPION_GATE_GIT_BLOB)


if __name__ == "__main__":
    unittest.main()
