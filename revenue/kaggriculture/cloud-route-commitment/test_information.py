# SPDX-License-Identifier: Apache-2.0
"""Pure public-clock and supplied-boundary consumer checks."""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from information import information_window, future_shop_reveals, from_commitment


class InformationTests(unittest.TestCase):
    def window(self, **kw):
        args = dict(now=226, last_compatible_decision=226, compatible_now=True, shop_count=3)
        args.update(kw)
        return information_window(**args)

    def test_information_after_commitment(self):
        r = self.window()
        self.assertEqual(r["next_reveal_decision"], 288)
        self.assertEqual(r["next_reveal_delay"], 62)
        self.assertFalse(r["can_wait_for_next_reveal"])
        self.assertEqual(r["reveals_while_compatible"], [])

    def test_exact_deadline_is_inclusive(self):
        r = self.window(now=215, last_compatible_decision=216, shop_count=2)
        self.assertTrue(r["can_wait_for_next_reveal"])
        self.assertEqual(r["reveals_while_compatible"], [216])
        self.assertFalse(self.window(now=215, last_compatible_decision=215, shop_count=2)["can_wait_for_next_reveal"])

    def test_already_public_reveal_not_future(self):
        self.assertEqual(future_shop_reveals(216, shop_count=3)[0], 288)
        self.assertEqual(future_shop_reveals(215, shop_count=2)[0], 216)

    def test_unknown_is_not_permission(self):
        for kwargs in ({"last_compatible_decision": None}, {"compatible_now": None}):
            r = self.window(**kwargs)
            self.assertIsNone(r["can_wait_for_next_reveal"])
            self.assertIsNone(r["reveals_while_compatible"])
        self.assertFalse(self.window(compatible_now=False)["can_wait_for_next_reveal"])

    def test_current_incompatibility_preserved(self):
        r = self.window(now=227, compatible_now=False)
        self.assertFalse(r["can_wait_for_next_reveal"])
        self.assertEqual(r["reveals_while_compatible"], [])

    def test_inconsistent_positive_input_rejected(self):
        for kw in ({"now": 227}, {"now": 719, "last_compatible_decision": 800}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.window(**kw)

    def test_instance_cap_and_unknown_identity(self):
        r = self.window(shop_count=8)
        self.assertIsNone(r["next_reveal_decision"])
        self.assertIsNone(r["can_wait_for_next_reveal"])
        self.assertEqual(r["shop_identity"], "unknown")
        self.assertNotIn("seed", r)
        self.assertEqual(future_shop_reveals(0, shop_count=9), ())

    def test_configuration_and_final_boundary(self):
        self.assertEqual(future_shop_reveals(24, shop_count=1, turns_per_day=12,
                                            unlock_interval_days=2, decision_count=100), (48,72,96))
        self.assertEqual(future_shop_reveals(0, shop_count=0, decision_count=72), ())
        self.assertEqual(future_shop_reveals(0, shop_count=0, decision_count=73), (72,))
        self.assertEqual(future_shop_reveals(718, shop_count=0), ())

    def test_invalid_counts_and_schema(self):
        for value in (-1, True, 2.1, "3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.window(shop_count=value)
        for kw in ({"compatible_now": 1}, {"last_compatible_decision": False},
                   {"configuration": []}, {"configuration": {"episodeSteps": 1}},
                   {"configuration": {"turnsPerDay": 0}}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.window(**kw)

    def test_no_input_mutation_and_no_hidden_features(self):
        cfg = {"turnsPerDay": 24, "townShopUnlockInterval": 3, "episodeSteps": 720}
        before = copy.deepcopy(cfg)
        a = self.window(configuration=cfg)
        self.assertEqual(cfg, before)
        cfg["hidden_seed_not_used"] = 12
        self.assertEqual(a, self.window(configuration=cfg))

    def test_shared_report_unknown_alias_and_disagreement(self):
        boundary = dict(now=226, decision_stop=719, last_equal_prefix_checkpoint=226,
                        same_object=False, structural_choice_now=True,
                        controller_accepts_now=True, predicate_agrees=True)
        before = copy.deepcopy(boundary)
        self.assertFalse(from_commitment(boundary, shop_count=3)["can_wait_for_next_reveal"])
        self.assertEqual(boundary, before)
        for change, expected in (({"same_object": True}, False),
                                 ({"predicate_agrees": False}, None),
                                 ({"controller_accepts_now": None}, None)):
            b = {**boundary, **change}
            self.assertIs(from_commitment(b, shop_count=3)["compatible_now"], expected)

    def test_shared_report_range_and_identity(self):
        boundary = dict(now=433, decision_stop=719, last_equal_prefix_checkpoint=577,
                        same_object=False, structural_choice_now=True,
                        controller_accepts_now=True, predicate_agrees=True,
                        current_route="main", target_route="milk", current_sha256="supplied")
        result = from_commitment(boundary, shop_count=6)
        self.assertTrue(result["can_wait_for_next_reveal"])
        self.assertEqual(result["reveals_while_compatible"], [504,576])
        self.assertEqual(result["boundary_source"]["current_sha256"], "supplied")
        with self.assertRaises(ValueError):
            from_commitment(boundary, shop_count=6, configuration={"episodeSteps": 100})


    def test_cli_stdout(self):
        cmd = [sys.executable, str(Path(__file__).with_name("information.py")), "--now", "226",
               "--last-compatible-decision", "226", "--compatible-now", "true", "--shop-count", "3"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(json.loads(p.stdout)["can_wait_for_next_reveal"])


if __name__ == "__main__":
    unittest.main()
