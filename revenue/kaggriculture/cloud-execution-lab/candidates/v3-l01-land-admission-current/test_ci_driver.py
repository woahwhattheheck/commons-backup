# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from ci_support import extract_verified, git_blob_id

LANE = Path(__file__).resolve().parent


class CiDriverTests(unittest.TestCase):
    def test_git_blob_identity(self):
        payload = b"hello\n"
        expected = hashlib.sha1(b"blob 6\0hello\n").hexdigest()  # noqa: S324
        self.assertEqual(git_blob_id(payload), expected)

    def test_extract_rejects_links(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as handle:
                member = tarfile.TarInfo("escape")
                member.type = tarfile.SYMTYPE
                member.linkname = "../outside"
                handle.addfile(member, io.BytesIO())
            with self.assertRaises(ValueError):
                extract_verified(archive, root / "out")

    def test_historical_panel_pin_matches_verified_source(self):
        pin = json.loads((LANE / "PIN.json").read_text(encoding="utf-8"))
        historical = pin["historical_source"]
        self.assertEqual(
            {
                "head_commit": historical["head_commit"],
                "baseline_games_git_blob": historical["baseline_games_git_blob"],
                "land_games_git_blob": historical["land_games_git_blob"],
            },
            {
                "head_commit": "c817c06af6c8d184c04c1d17fe9c1b42fcf1a65a",
                "baseline_games_git_blob": "54cffb15c70762fb20b791487ea9682fd9a7ee1e",
                "land_games_git_blob": "694ef44cd53047b15a61d9b351e66b8147d7f11f",
            },
        )

    def test_holdout_cardinality_matches_axes(self):
        pin = json.loads((LANE / "PIN.json").read_text(encoding="utf-8"))
        holdout = pin["holdout"]
        games_per_arm = (
            holdout["seed_count"]
            * len(holdout["opponents"])
            * len(holdout["candidate_seats"])
        )
        self.assertEqual(holdout["scheduled_games_per_arm"], games_per_arm)
        self.assertEqual(holdout["scheduled_games_total"], 2 * games_per_arm)

    def test_holdout_workers_matches_admitted_carrier(self):
        pin = json.loads((LANE / "PIN.json").read_text(encoding="utf-8"))
        self.assertEqual(pin["holdout"]["workers"], 2)


if __name__ == "__main__":
    unittest.main()
