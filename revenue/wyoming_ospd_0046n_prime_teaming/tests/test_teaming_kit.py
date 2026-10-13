import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("teaming_kit", ROOT / "teaming_kit.py")
kit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(kit)


class TeamingKitTests(unittest.TestCase):
    def setUp(self):
        self.offer = json.loads((ROOT / "offer.json").read_text())
        self.cases = json.loads((ROOT / "fixtures" / "acceptance_cases.json").read_text())

    def test_checked_manifest_and_cases_render_deterministically(self):
        first = kit.render_scope(self.offer, self.cases, "Journal Technologies")
        second = kit.render_scope(self.offer, self.cases, "Journal Technologies")
        self.assertEqual(first, second)
        self.assertIn("$2,500 fixed", first)
        self.assertIn("No free custom build", first)
        self.assertIn("Public Purchase", first)
        self.assertIn("7 TASK_READY / 5 HELD", first)

    def test_direct_buyer_email_is_fail_closed(self):
        bad = copy.deepcopy(self.offer)
        bad["direct_buyer_email_allowed"] = True
        with self.assertRaisesRegex(ValueError, "direct buyer email"):
            kit.validate_offer(bad)

    def test_free_custom_work_is_fail_closed(self):
        bad = copy.deepcopy(self.offer)
        bad["free_custom_work"] = True
        with self.assertRaisesRegex(ValueError, "free_custom_work"):
            kit.validate_offer(bad)

    def test_price_drift_is_fail_closed(self):
        bad = copy.deepcopy(self.offer)
        bad["sandbox_proof_price_usd"] = 0
        with self.assertRaisesRegex(ValueError, "2500"):
            kit.validate_offer(bad)

    def test_case_count_and_identity_are_exact(self):
        with self.assertRaisesRegex(ValueError, "expected 12"):
            kit.validate_cases(self.cases[:-1])
        dup = copy.deepcopy(self.cases)
        dup[-1]["id"] = dup[0]["id"]
        with self.assertRaisesRegex(ValueError, "unique"):
            kit.validate_cases(dup)

    def test_terminal_state_is_closed_set(self):
        bad = copy.deepcopy(self.cases)
        bad[0]["expected"] = "SILENT_DROP"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            kit.validate_cases(bad)

    def test_unknown_partner_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            kit.render_scope(self.offer, self.cases, "Unknown Vendor")

    def test_two_prime_routes_render_without_cross_leak(self):
        journal = kit.render_scope(self.offer, self.cases, "Journal Technologies")
        karpel = kit.render_scope(self.offer, self.cases, "Karpel Solutions")
        self.assertIn("eDefender", journal)
        self.assertNotIn("DEFENDERbyKarpel", journal)
        self.assertIn("DEFENDERbyKarpel", karpel)
        self.assertNotIn("eDefender", karpel)


if __name__ == "__main__":
    unittest.main()
