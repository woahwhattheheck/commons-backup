#!/usr/bin/env python3
"""Exact local certificates for issue 14999. Not a prize proof."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kuhn import kuhn_tets, refine_n, tet_volume_times_6
from local_div import dim_pk, local_div_qrank, monomials

RECEIPT = HERE / "receipts" / "local_div_rank.json"


def build_receipt() -> dict:
    tets = kuhn_tets()
    ranks = {str(k): {"rank": local_div_qrank(k), "dim_p_km1": dim_pk(k - 1)} for k in range(1, 7)}
    return {
        "issue": 14999,
        "kuhn_cube_tets": len(tets),
        "tet_6vol": [tet_volume_times_6(tet) for tet in tets],
        "refine_n": {str(n): refine_n(n) for n in (1, 2, 3, 4)},
        "dim_pk": {str(k): dim_pk(k) for k in range(0, 7)},
        "local_div_qrank": ranks,
        "continuity_boundary_singular_included": False,
        "mesh_uniform_k4_k5": "OPEN",
        "prize_claim": False,
        "sponsor_contact": False,
    }


def write_receipt(data: dict) -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class KuhnCubeTests(unittest.TestCase):
    def test_six_equal_positive_tets(self):
        tets = kuhn_tets()
        self.assertEqual(len(tets), 6)
        self.assertEqual(len(set(tets)), 6)
        for tet in tets:
            self.assertEqual(tet_volume_times_6(tet), 1)

    def test_refine_n_counts(self):
        for n in range(1, 8):
            self.assertEqual(refine_n(n), 6 * n * n * n)


class PolynomialDimTests(unittest.TestCase):
    def test_dim_matches_binomial(self):
        expected = {0: 1, 1: 4, 2: 10, 3: 20, 4: 35, 5: 56, 6: 84}
        for k, dim in expected.items():
            self.assertEqual(dim_pk(k), dim)
            self.assertEqual(len(monomials(k)), dim)


class LocalDivRankTests(unittest.TestCase):
    def test_qrank_equals_dim_p_km1_for_k_1_through_6(self):
        for k in range(1, 7):
            self.assertEqual(local_div_qrank(k), dim_pk(k - 1))


class AdvertisedSurfaceTests(unittest.TestCase):
    def test_readme_points_at_this_file_and_receipt(self):
        text = (HERE / "README.md").read_text(encoding="utf-8")
        self.assertIn("python3 test_certificates.py", text)
        self.assertIn("receipts/local_div_rank.json", text)
        self.assertIn("Open advertised cases: k = 4 and k = 5", text)
        self.assertNotIn("not " + "authorized", text)
        self.assertNotIn("not " + "permitted", text)

    def test_ledger_keeps_mesh_uniform_open_and_forbids_prize(self):
        text = (HERE / "LEDGER.md").read_text(encoding="utf-8")
        self.assertIn("Sponsor conjecture k>=4 mesh-uniform inf-sup | OPEN", text)
        self.assertIn("Prize / payment / sponsor email | FORBIDDEN by issue", text)
        self.assertIn("Local div : [P_k]^3 -> P_{k-1} surjective on one tet, k=1..6 | CERTIFIED", text)

    def test_advertised_modules_exist(self):
        self.assertTrue((HERE / "kuhn.py").is_file())
        self.assertTrue((HERE / "local_div.py").is_file())
        self.assertTrue((HERE / "test_certificates.py").is_file())

    def test_receipt_matches_exact_certificates(self):
        data = build_receipt()
        write_receipt(data)
        loaded = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(loaded, json.loads(json.dumps(data, indent=2, sort_keys=True)))
        self.assertEqual(loaded["tet_6vol"], [1, 1, 1, 1, 1, 1])
        self.assertEqual(loaded["refine_n"]["3"], 162)
        for k in range(1, 7):
            row = loaded["local_div_qrank"][str(k)]
            self.assertEqual(row["rank"], row["dim_p_km1"])
        self.assertIs(loaded["prize_claim"], False)
        self.assertEqual(loaded["mesh_uniform_k4_k5"], "OPEN")


if __name__ == "__main__":
    write_receipt(build_receipt())
    unittest.main()
