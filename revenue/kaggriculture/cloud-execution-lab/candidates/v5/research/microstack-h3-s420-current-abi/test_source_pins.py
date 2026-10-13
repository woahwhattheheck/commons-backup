# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[3]
PINS = json.loads((HERE / "SOURCE-PINS.json").read_text())


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


class SourcePinsTest(unittest.TestCase):
    def test_current_source_blobs_are_exact(self):
        repo_root = LAB.parents[2]
        for name, entry in PINS["current_sources"].items():
            with self.subTest(name=name):
                path = repo_root / entry["path"]
                self.assertTrue(path.is_file(), path)
                self.assertEqual(git_blob(path.read_bytes()), entry["git_blob"])

    def test_canonical_h3s420_composer_is_exact(self):
        repo_root = LAB.parents[2]
        entry = PINS["canonical_authority"]
        path = repo_root / entry["path"]
        self.assertTrue(path.is_file(), path)
        self.assertEqual(git_blob(path.read_bytes()), entry["git_blob"])
        text = path.read_text()
        self.assertIn("if now < H3S420_SUPPRESS_NEW_PLANS_AFTER:", text)
        self.assertIn("skip the entire new-plan selection block", entry["semantics"])

    def test_current_native_horizon_and_optimizer_seams_are_present(self):
        scheduler = (LAB / "scheduler.py").read_text()
        frozen = (LAB / "frozen_selected.py").read_text()
        self.assertIn("HORIZON = 8", scheduler)
        self.assertEqual(
            frozen.count("baseline_end=min(now+HORIZON,represented_end)"), 1
        )
        self.assertEqual(frozen.count("plan,info=optimize_lot("), 1)
        self.assertIn("minimum_now=minimum", frozen)
        self.assertIn("seller_choice_rank(info)", frozen)

    def test_forbidden_legacy_feature_keys_are_not_production_config(self):
        runtime = (LAB / "titan_runtime.py").read_text()
        config = (LAB / "TITAN-CONFIG.json").read_text()
        for legacy_key in (
            "r04_sale_horizon",
            "r04_no_late_sale_advance_step",
        ):
            self.assertNotIn(legacy_key, runtime)
            self.assertNotIn(legacy_key, config)

    def test_forbidden_alternate_s420_semantics_stay_declared(self):
        forbidden = PINS["forbidden"]
        self.assertIn(
            "equal-total-only or noncomparable-plan S420 reinterpretation", forbidden
        )
        self.assertIn(
            "forced-feasibility bypass of the canonical S420 cutoff", forbidden
        )


if __name__ == "__main__":
    unittest.main()
