import copy
import hashlib
import unittest

import p04_route_ranker as p04


def snapshot(shops=("BAKERY", "YARN_STORE")):
    return {
        "first_two_shops": list(shops),
        "market": {
            "prices": {"WOOL": 210, "MILK": 180, "WHEAT": 20, "CARROT": 30},
            "inventory": {"WOOL": 50, "MILK": 60, "WHEAT": 100, "CARROT": 90},
        },
        "own": {
            "cash": 1234,
            "worker_count": 5,
            "animal_counts": {"COW": 2, "SHEEP": 3, "GOOSE": 1},
            "crop_counts": {"WHEAT": 4, "CARROT": 2},
        },
        "rival": {
            "animal_counts": {"COW": 1, "SHEEP": 6, "GOOSE": 0},
            "crop_counts": {"WHEAT": 5, "CARROT": 1},
        },
        "incumbent_plan": p04.expected_incumbent_plan(shops),
    }


def row(plan, *, own=1000, rival=900, snap=None, seed=1, opponent="apex_v7", seat=0):
    snap = copy.deepcopy(snap or snapshot())
    return {
        "seed": seed,
        "opponent": opponent,
        "seat": seat,
        "forced_plan": plan,
        "snapshot": snap,
        "snapshot_sha256": p04.snapshot_sha256(snap),
        "terminal_own": own,
        "terminal_rival": rival,
        "terminal_margin": own - rival,
        "failures": [],
    }


class P04RouteRankerTests(unittest.TestCase):
    def test_source_mapping_and_terminal_plan_boundary(self):
        self.assertEqual(p04.expected_incumbent_plan(("BAKERY", "YARN_STORE")), 3)
        self.assertEqual(p04.expected_incumbent_plan(("BAKERY", "PIZZA_SHOP")), 0)
        self.assertNotIn(2, p04.NATURAL_STEP144_PLANS)
        self.assertEqual(p04.FINAL_PLAN_STEP, 648)

    def test_snapshot_digest_is_canonical(self):
        a = snapshot()
        b = copy.deepcopy(a)
        b["market"]["prices"] = dict(reversed(list(b["market"]["prices"].items())))
        self.assertEqual(p04.snapshot_sha256(a), p04.snapshot_sha256(b))

    def test_snapshot_rejects_private_rival_inventory(self):
        bad = snapshot()
        bad["rival"]["inventory"] = {"WOOL": 999}
        with self.assertRaisesRegex(ValueError, "non-public"):
            p04.canonical_public_snapshot(bad)

    def test_row_rejects_future_rng(self):
        bad = row(0)
        bad["future_rng"] = "oracle"
        with self.assertRaisesRegex(ValueError, "forbidden"):
            p04.normalize_row(bad)

    def test_row_rejects_forged_snapshot_hash(self):
        bad = row(0)
        bad["snapshot_sha256"] = hashlib.sha256(b"forged").hexdigest()
        with self.assertRaisesRegex(ValueError, "does not bind"):
            p04.normalize_row(bad)

    def test_row_rejects_incorrect_margin(self):
        bad = row(0)
        bad["terminal_margin"] += 1
        with self.assertRaisesRegex(ValueError, "must equal"):
            p04.normalize_row(bad)

    def test_source_archetypes_bind_known_route_classes(self):
        self.assertEqual(p04.source_archetype(0)["animal"], "COW4-SHEEP4-GOOSE3")
        self.assertEqual(p04.source_archetype(9)["crop"], "W148-C28-S29")
        self.assertEqual(p04.source_archetype(12)["animal"], "SHEEP12")
        self.assertFalse(p04.source_archetype(2)["natural_step144"])

    def test_feature_signature_is_observation_only(self):
        sig = p04.public_feature_signature(snapshot())
        self.assertEqual(sig["shop_pair"], "BAKERY|YARN_STORE")
        self.assertEqual(sig["first_two_yarn_count"], 1)
        self.assertEqual(sig["wool_vs_milk_price"], "WOOL>MILK")
        self.assertEqual(sig["rival_livestock_leader"], "SHEEP")

    def test_complete_matrix_ranks_best_plan_but_keeps_policy_hold(self):
        snap = snapshot()
        rows = []
        for plan in p04.ALL_PLANS:
            own = 1000 + plan
            rows.append(row(plan, own=own, rival=900, snap=snap))
        report = p04.reduce_matrix(rows)
        self.assertEqual(report["complete_snapshot_groups"], 1)
        self.assertEqual(report["groups"][0]["best_plan"], 12)
        self.assertEqual(report["groups"][0]["incumbent_plan"], 3)
        self.assertFalse(report["policy_ready"])
        self.assertIn("held-out", report["policy_hold_reason"])

    def test_incomplete_matrix_fails_closed(self):
        rows = [row(plan) for plan in range(12)]
        with self.assertRaisesRegex(ValueError, "incomplete route matrix"):
            p04.reduce_matrix(rows)

    def test_duplicate_plan_fails_closed(self):
        rows = [row(plan) for plan in p04.ALL_PLANS]
        rows.append(row(0))
        with self.assertRaisesRegex(ValueError, "duplicate forced plan"):
            p04.reduce_matrix(rows)

    def test_snapshot_mismatch_splits_and_then_fails_complete(self):
        rows = [row(plan) for plan in p04.ALL_PLANS]
        different = snapshot()
        different["own"]["cash"] = 1235
        rows[-1] = row(12, snap=different)
        with self.assertRaisesRegex(ValueError, "incomplete route matrix"):
            p04.reduce_matrix(rows)


if __name__ == "__main__":
    unittest.main()
