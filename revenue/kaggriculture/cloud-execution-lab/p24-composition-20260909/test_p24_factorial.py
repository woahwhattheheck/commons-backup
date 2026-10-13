from __future__ import annotations

import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import p24_factorial as p24


class MatrixTests(unittest.TestCase):
    def test_complete_unique_matrix(self):
        rows = p24.variant_matrix()
        self.assertEqual(len(rows), 16)
        self.assertEqual(len({row["name"] for row in rows}), 16)
        self.assertEqual(rows[0]["name"], "baseline")
        self.assertEqual(rows[-1]["name"], "joint_all")
        self.assertEqual(sum(row["flags"]["early_capital"] for row in rows), 8)

    def test_mobius_additive_and_synergy(self):
        values = {frozenset(part): 10 + sum(range(1, len(part) + 1)) for part in p24.powerset(p24.FACTORS)}
        # Use a truly additive surface for zero pair interaction.
        weights = {factor: index + 1 for index, factor in enumerate(p24.FACTORS)}
        values = {frozenset(part): 10 + sum(weights[x] for x in part) for part in p24.powerset(p24.FACTORS)}
        self.assertEqual(p24.mobius(values, frozenset(p24.FACTORS[:2])), 0)
        pair = frozenset(p24.FACTORS[:2])
        values = {frozenset(part): len(part) + (9 if pair <= frozenset(part) else 0)
                  for part in p24.powerset(p24.FACTORS)}
        self.assertEqual(p24.mobius(values, pair), 9)


class ArchiveTests(unittest.TestCase):
    def make(self, path, names, link=False):
        with tarfile.open(path, "w:gz") as bundle:
            for name in (names if isinstance(names, (list, tuple)) else [names]):
                member = tarfile.TarInfo(name)
                if link:
                    member.type = tarfile.SYMTYPE; member.linkname = "/tmp/escape"; bundle.addfile(member)
                else:
                    data = b"ok"; member.size = len(data); bundle.addfile(member, io.BytesIO(data))

    def test_accepts_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / "ok.tar.gz"; self.make(archive, "sub/file")
            self.assertEqual(p24.safe_extract(archive, root / "out"), ["sub/file"])

    def test_rejects_traversal_and_link(self):
        for name, link in (("../escape", False), ("link", True)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); archive = root / "bad.tar.gz"; self.make(archive, name, link)
                with self.assertRaises(ValueError):
                    p24.safe_extract(archive, root / "out")

    def test_rejects_duplicate_member_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / "dup.tar.gz"
            self.make(archive, ["a", "a"])
            with self.assertRaises(ValueError):
                p24.safe_extract(archive, root / "out")


class ValidationTests(unittest.TestCase):
    def game(self, variant, seat):
        return {"variant": variant, "opponent": "rival", "seed": 1, "candidate_seat": seat,
                "status": "complete", "failure": None, "scores": [10.0, 9.0], "steps": 719,
                "episode_steps": 720, "trace_sha256": "a" * 64}

    def test_exact_cells_and_failures(self):
        variants = p24.variant_matrix()[:2]
        games = [self.game(row["name"], seat) for row in variants for seat in (0, 1)]
        p24.validate_games(games, variants, ["rival"], [1])
        with self.assertRaises(AssertionError):
            p24.validate_games(games[:-1], variants, ["rival"], [1])
        games[0]["status"] = "failed"; games[0]["failure"] = {"kind": "timeout"}
        with self.assertRaises(AssertionError):
            p24.validate_games(games, variants, ["rival"], [1])

    def test_valid_hash_64hex(self):
        self.assertTrue(p24.valid_hash("a" * 64))
        self.assertFalse(p24.valid_hash("x"))
        self.assertFalse(p24.valid_hash("A" * 64))
        self.assertFalse(p24.valid_hash("a" * 63))
        self.assertFalse(p24.valid_hash(None))


class ConfigTests(unittest.TestCase):
    def test_only_factors_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); base = root / "base"; base.mkdir()
            (base / "main.py").write_text("def agent(obs, cfg=None): return {}\n")
            config = {"fixed": "keep", **{factor: True for factor in p24.FACTORS}}
            (base / "TITAN-CONFIG.json").write_text(json.dumps(config))
            rows, original = p24.prepare_variants(base, root / "variants")
            self.assertEqual(original, config)
            for row in rows:
                built = json.loads((root / "variants" / row["name"] / "TITAN-CONFIG.json").read_text())
                self.assertEqual(built["fixed"], "keep")
                self.assertEqual({factor: built[factor] for factor in p24.FACTORS}, row["flags"])


if __name__ == "__main__":
    unittest.main()
