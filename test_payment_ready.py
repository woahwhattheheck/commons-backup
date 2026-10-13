#!/usr/bin/env python3
"""Payment-ready leftover names a $12k diagnostic and stores no payout data."""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "host"))

from payment_ready import (
    CALIBRATION,
    REQUIRED_AT,
    REQUIRED_GATE_OPEN,
    REQUIRED_RAIL_EVENTS,
    SEARCH_SPACE,
    SLACK_TS,
    TAKING_PATH,
    at_gaps,
    classify,
    load_pack,
    measure_bazaar,
    measure_from_rows,
    measure_root,
    milestone_amounts,
)
import revenue_recovery as rr


class TestPaymentReady(unittest.TestCase):
    def test_unmeasured_is_not_stillness(self):
        row = classify({})
        self.assertEqual(row["state"], "UNMEASURED")
        self.assertIn("not stillness", row["note"])
        self.assertEqual(row["z"], "FINDER-FAILED")

    def test_failed_calibration_is_instrument_failure(self):
        verdict = classify(
            {
                "measured": True,
                "calibration_ok": False,
                "card_present": True,
                "pack_present": True,
            }
        )
        self.assertEqual(verdict["state"], "UNMEASURED")
        self.assertIn("Instrument failure", verdict["note"])
        self.assertEqual(verdict["z"], "FINDER-FAILED")

    def test_missing_paths_are_not_landed(self):
        measured = measure_from_rows(
            {
                "card_present": False,
                "pack_present": False,
                "misses": ["ground/PAYMENT_READY.md"],
                "calibration_ok": True,
            }
        )
        self.assertEqual(classify(measured)["state"], "NOT_LANDED")
        self.assertEqual(classify(measured)["z"], "FINDER-FAILED")

    def test_claimed_cash_is_not_landed(self):
        catalog_path = os.path.join(ROOT, "revenue", "payment_ready", "pack.json")
        with open(catalog_path, encoding="utf-8") as handle:
            pack = load_pack(handle.read())
        measured = measure_from_rows(
            {
                "card_present": True,
                "pack_present": True,
                "kind": pack["kind"],
                "mandate": pack["mandate"],
                "fixed_amount": 12000,
                "term_calendar_days": 10,
                "milestone_amounts": [6000, 6000],
                "payment_collection": "NOT_PROVIDED_ON_THIS_PAGE",
                "does_not_replace": "white-box-gguf-pilot-30d",
                "demand": "UNKNOWN",
                "acceptance_rule": "rollback evidence, not metric lift",
                "falsifier": ["x"],
                "downgrade_path": ["y"],
                "at_gaps": at_gaps(pack["acceptance_tests"]),
                "gate_pack": "READY",
                "gate_owner": "NEEDS_OWNER_PRIVATE",
                "gate_buyer": "NEEDS_BUYER",
                "gate_cash": "NOT_LANDED",
                "gate_cash_usd": 0,
                "gate_open": list(REQUIRED_GATE_OPEN),
                "ready_does_not_mean_cash": True,
                "collectable_usd": "NOT_LANDED",
                "collected_cash_usd": 12,
                "banking_only_blocker": False,
                "computer_is_the_product": False,
                "overwrites_commercial_json": False,
                "overwrites_dio": False,
                "usd_offer_count": 0,
                "bazaar_currency": "FREE_COLONY_COMPUTE",
                "white_box_fee": 30000,
                "commercial_offer_id": "white-box-gguf-pilot-30d",
                "dio_present": True,
                "portfolio_collectable": "NOT_LANDED",
                "portfolio_banking_only": False,
                "taking_state": "CARRIER_ONLY",
                "xyz_required": True,
                "remeasurement_owner": "Codex / Grok Build",
                "rails": pack["rails"],
                "rail_events": list(REQUIRED_RAIL_EVENTS),
                "private_manifest_present": True,
                "dissent_present": True,
                "d0_status": "OPEN",
                "calibration_ok": True,
            }
        )
        self.assertEqual(classify(measured)["state"], "NOT_LANDED")

    def test_banking_only_true_is_not_landed(self):
        measured = measure_from_rows(
            {
                "card_present": True,
                "pack_present": True,
                "kind": "PAYMENT_READY_PACK",
                "mandate": "demon-redteam-payment-ready-20260825-02",
                "fixed_amount": 12000,
                "term_calendar_days": 10,
                "milestone_amounts": [6000, 6000],
                "payment_collection": "NOT_PROVIDED_ON_THIS_PAGE",
                "does_not_replace": "white-box-gguf-pilot-30d",
                "demand": "UNKNOWN",
                "acceptance_rule": "rollback",
                "falsifier": ["x"],
                "downgrade_path": ["y"],
                "at_gaps": {"ids": list(REQUIRED_AT), "missing": [], "empty_pass": []},
                "gate_pack": "READY",
                "gate_owner": "NEEDS_OWNER_PRIVATE",
                "gate_buyer": "NEEDS_BUYER",
                "gate_cash": "NOT_LANDED",
                "gate_cash_usd": 0,
                "gate_open": list(REQUIRED_GATE_OPEN),
                "ready_does_not_mean_cash": True,
                "collectable_usd": "NOT_LANDED",
                "collected_cash_usd": 0,
                "banking_only_blocker": True,
                "computer_is_the_product": False,
                "overwrites_commercial_json": False,
                "overwrites_dio": False,
                "usd_offer_count": 0,
                "bazaar_currency": "FREE_COLONY_COMPUTE",
                "white_box_fee": 30000,
                "commercial_offer_id": "white-box-gguf-pilot-30d",
                "dio_present": True,
                "portfolio_collectable": "NOT_LANDED",
                "portfolio_banking_only": False,
                "taking_state": "CARRIER_ONLY",
                "xyz_required": True,
                "remeasurement_owner": "Codex / Grok Build",
                "rails": [{"provider": "Stripe"}, {"provider": "PayPal"}],
                "rail_events": list(REQUIRED_RAIL_EVENTS),
                "private_manifest_present": True,
                "dissent_present": True,
                "d0_status": "OPEN",
                "calibration_ok": True,
            }
        )
        self.assertEqual(classify(measured)["state"], "NOT_LANDED")

    def test_live_tree_matches_the_report(self):
        pack_path = os.path.join(ROOT, "revenue", "payment_ready", "pack.json")
        with open(pack_path, encoding="utf-8") as handle:
            pack = load_pack(handle.read())
        self.assertEqual(pack["slack_ts"], SLACK_TS)
        self.assertEqual(pack["kind"], "PAYMENT_READY_PACK")
        self.assertEqual(pack["mandate"], "demon-redteam-payment-ready-20260825-02")
        self.assertNotIn("titan", pack)
        self.assertEqual(pack["taking_state"], "CARRIER_ONLY")
        self.assertEqual(pack["collectable_usd"], "NOT_LANDED")
        self.assertEqual(pack["collected_cash_usd"], 0)
        self.assertFalse(pack["banking_only_blocker"])
        self.assertFalse(pack["computer_is_the_product"])
        self.assertFalse(pack["overwrites_commercial_json"])
        self.assertFalse(pack["overwrites_dio"])
        self.assertEqual(pack["fixed_amount"], 12000)
        self.assertEqual(pack["term_calendar_days"], 10)
        self.assertEqual(milestone_amounts(pack["milestones"]), [6000, 6000])
        self.assertEqual(pack["payment_collection"], "NOT_PROVIDED_ON_THIS_PAGE")
        self.assertEqual(pack["does_not_replace"], "white-box-gguf-pilot-30d")
        self.assertEqual(pack["demand"], "UNKNOWN")
        self.assertIn("rollback", pack["acceptance_rule"])
        self.assertGreaterEqual(len(pack["falsifier"]), 1)
        self.assertGreaterEqual(len(pack["downgrade_path"]), 1)
        gaps = at_gaps(pack["acceptance_tests"])
        self.assertEqual(gaps["missing"], [])
        self.assertEqual(gaps["empty_pass"], [])
        self.assertEqual(gaps["ids"], list(REQUIRED_AT))
        self.assertEqual(pack["gate_pack"], "READY")
        self.assertEqual(pack["gate_owner"], "NEEDS_OWNER_PRIVATE")
        self.assertEqual(pack["gate_buyer"], "NEEDS_BUYER")
        self.assertEqual(pack["gate_cash"], "NOT_LANDED")
        self.assertEqual(pack["gate_cash_usd"], 0)
        self.assertTrue(pack["ready_does_not_mean_cash"])
        for name in REQUIRED_GATE_OPEN:
            self.assertIn(name, pack["gate_open"])
        self.assertNotIn("READY", pack["gate_open"])
        bazaar_path = os.path.join(ROOT, "bazaar.json")
        with open(bazaar_path, encoding="utf-8") as handle:
            bazaar = measure_bazaar(handle.read())
        self.assertEqual(bazaar["usd_offer_count"], 0)
        self.assertEqual(bazaar["currency"], "FREE_COLONY_COMPUTE")
        row = measure_root(ROOT)
        self.assertTrue(row["calibration_ok"], "known-present calibration must hit EXECUTE + Action Pad")
        self.assertEqual(sorted(row["calibration_hits"]), sorted(CALIBRATION))
        self.assertEqual(row["search_space"], list(SEARCH_SPACE))
        self.assertEqual(row["taking_state"], "CARRIER_ONLY")
        self.assertFalse(row["taking_present"])
        self.assertEqual(row["usd_offer_count"], 0)
        self.assertEqual(row["white_box_fee"], 30000)
        self.assertEqual(row["commercial_offer_id"], "white-box-gguf-pilot-30d")
        self.assertTrue(row["dio_present"])
        self.assertEqual(row["portfolio_collectable"], "NOT_LANDED")
        self.assertFalse(row["portfolio_banking_only"])
        self.assertEqual(classify(row)["state"], "INTEGRATED")
        self.assertFalse(os.path.isfile(os.path.join(ROOT, TAKING_PATH)))
        self.assertTrue(os.path.isdir(os.path.join(ROOT, "revenue", "dio")))
        commercial_path = os.path.join(ROOT, "commercial.json")
        with open(commercial_path, encoding="utf-8") as handle:
            commercial = handle.read()
        self.assertIn("white-box-gguf-pilot-30d", commercial)
        self.assertNotIn("gguf-diagnostic-10d-12k", commercial)

    def test_processor_docs_reject_contest_product_secret_scan_append(self):
        hostile = (
            "Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): "
            "https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, "
            "Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). "
            "Cite Latch Pad KEEP."
        )
        self.assertTrue(rr.contains_sensitive_value(hostile))
        for relative in (
            "revenue/payment_ready/processor_handoff.md",
            "revenue/payment_ready/evidence_contract.md",
        ):
            with self.subTest(relative=relative):
                path = os.path.join(ROOT, relative)
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                self.assertNotIn("## Contest product (titanmcp)", text)
                self.assertNotIn("Cite Latch Pad KEEP", text)
                self.assertFalse(rr.contains_sensitive_value(text))


if __name__ == "__main__":
    unittest.main()
