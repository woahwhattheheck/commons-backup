# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ci_support import git_blob_id
from historical_provenance import verify_historical_pair


def _row(opponent: str, seed: int, seat: int) -> dict[str, object]:
    return {
        "opponent": opponent,
        "seed": seed,
        "candidate_seat": seat,
        "status": "complete",
        "scores": [100.0 + seat, 99.0 + seat],
        "failure": None,
    }


def _payload(rows: list[dict[str, object]]) -> bytes:
    return b"".join(
        (json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )


class HistoricalProvenanceTests(unittest.TestCase):
    def _fixture(self, root: Path):
        rows = [_row("arlene", 11, 0), _row("arlene", 11, 1)]
        baseline = _payload(rows)
        candidate = _payload(rows)
        (root / "canonical.GAMES.jsonl").write_bytes(baseline)
        (root / "land.GAMES.jsonl").write_bytes(candidate)
        pin = {
            "head_commit": "a" * 40,
            "pull_request": 11459,
            "expected_rows_per_arm": 2,
            "baseline_games_git_blob": git_blob_id(baseline),
            "baseline_games_sha256": hashlib.sha256(baseline).hexdigest(),
            "land_games_git_blob": git_blob_id(candidate),
            "land_games_sha256": hashlib.sha256(candidate).hexdigest(),
        }
        return pin

    def test_exact_pair_writes_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pin = self._fixture(root)
            receipt = verify_historical_pair(root, pin)
            self.assertEqual(receipt["paired_cells"], 2)
            self.assertEqual(receipt["baseline"]["rows"], 2)
            self.assertTrue((root / "PROVENANCE.json").is_file())

    def test_one_byte_replacement_rejects(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pin = self._fixture(root)
            path = root / "land.GAMES.jsonl"
            path.write_bytes(path.read_bytes().replace(b"100.0", b"101.0", 1))
            with self.assertRaisesRegex(ValueError, "Git blob drifted"):
                verify_historical_pair(root, pin)

    def test_duplicate_cell_rejects(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pin = self._fixture(root)
            path = root / "canonical.GAMES.jsonl"
            first = path.read_bytes().splitlines(keepends=True)[0]
            path.write_bytes(first + first)
            pin["baseline_games_git_blob"] = git_blob_id(path.read_bytes())
            pin["baseline_games_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "duplicate historical cell"):
                verify_historical_pair(root, pin)

    def test_unpaired_grid_rejects(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pin = self._fixture(root)
            replacement = _payload([_row("arlene", 11, 0), _row("apex", 11, 1)])
            path = root / "land.GAMES.jsonl"
            path.write_bytes(replacement)
            pin["land_games_git_blob"] = git_blob_id(replacement)
            pin["land_games_sha256"] = hashlib.sha256(replacement).hexdigest()
            with self.assertRaisesRegex(ValueError, "paired grid drifted"):
                verify_historical_pair(root, pin)

    def test_missing_final_newline_rejects(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pin = self._fixture(root)
            path = root / "land.GAMES.jsonl"
            payload = path.read_bytes().rstrip(b"\n")
            path.write_bytes(payload)
            pin["land_games_git_blob"] = git_blob_id(payload)
            pin["land_games_sha256"] = hashlib.sha256(payload).hexdigest()
            with self.assertRaisesRegex(ValueError, "lacks final newline"):
                verify_historical_pair(root, pin)


if __name__ == "__main__":
    unittest.main()
