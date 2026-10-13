#!/usr/bin/env python3
"""tjlabs sold-pack ToS: owner slots, no invented share, not a Commons gate."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "host"))

import tjlabs_pack_terms as tos  # noqa: E402


class TjlabsPackTermsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.law = tos.load_law()
        self.card = (ROOT / "ground" / "TJLABS_PACK_TERMS.md").read_text(
            encoding="utf-8"
        )
        self.template = (ROOT / "packs" / "_template" / "terms.md").read_text(
            encoding="utf-8"
        )
        self.door = (ROOT / "packs" / "tjlabs-terms.html").read_text(encoding="utf-8")
        self.land = (ROOT / "land" / "tjlabs-pack-tos-20260902.md").read_text(
            encoding="utf-8"
        )
        self.receipt = (
            ROOT / "p" / "cursor-tjlabs-pack-tos-20260902-01.md"
        ).read_text(encoding="utf-8")

    def test_law_is_not_a_commons_gate_and_does_not_invent_numbers(self) -> None:
        self.assertEqual(self.law["id"], "cursor-tjlabs-pack-tos-20260902-01")
        self.assertIs(self.law["gate"], False)
        self.assertIs(self.law["commons_admission"], False)
        self.assertEqual(self.law["source_channel_id"], "C0BU51F1PL3")
        self.assertEqual(self.law["source_slack_ts"], "1788326869.732839")
        self.assertEqual(self.law["entity_short"], "tjlabs")
        self.assertEqual(self.law["profit_share_percent"], "OWNER_UNSET")
        self.assertEqual(self.law["partial_ownership_fraction"], "OWNER_UNSET")
        self.assertIs(self.law["owner_pasted"], False)
        self.assertIs(self.law["counsel_cleared"], False)
        self.assertIs(self.law["saleable"], False)
        self.assertEqual(self.law["checkout"], "NOT_MINTED")
        self.assertIs(self.law["no_fake_stripe_urls"], True)
        self.assertIs(self.law["did_not_write_scout_research"], True)
        self.assertIs(self.law["counsel_questions_are_not_rulings"], True)
        dumped = json.dumps(self.law)
        self.assertNotIn("337 NO", dumped)
        self.assertNotRegex(dumped, r'"profit_share_percent":\s*\d')

    def test_default_instance_is_incomplete(self) -> None:
        result = tos.classify_instance()
        self.assertIs(result["gate"], False)
        self.assertEqual(result["verdict"], "TOS_INCOMPLETE")
        self.assertIs(result["saleable"], False)
        self.assertIs(result["hold_counsel"], True)
        self.assertEqual(result["checkout"], "NOT_MINTED")

    def test_owner_pasted_slots_without_counsel_are_set_not_saleable(self) -> None:
        result = tos.classify_instance(
            {
                "profit_share_percent": "12",
                "partial_ownership_fraction": "1/10",
                "owner_pasted": True,
                "counsel_cleared": False,
            }
        )
        self.assertEqual(result["verdict"], "TOS_SLOTS_SET")
        self.assertIs(result["saleable"], False)
        self.assertIs(result["hold_counsel"], True)

    def test_numbers_without_owner_pasted_flag_stay_incomplete(self) -> None:
        result = tos.classify_instance(
            {
                "profit_share_percent": "15",
                "partial_ownership_fraction": "1/5",
                "owner_pasted": False,
            }
        )
        self.assertEqual(result["verdict"], "TOS_INCOMPLETE")
        self.assertIs(result["saleable"], False)

    def test_counsel_cleared_with_owner_slots_is_saleable_terms_only(self) -> None:
        result = tos.classify_instance(
            {
                "profit_share_percent": "8",
                "partial_ownership_fraction": "1/20",
                "owner_pasted": True,
                "counsel_cleared": True,
            }
        )
        self.assertEqual(result["verdict"], "TOS_COUNSEL_CLEARED")
        self.assertIs(result["saleable"], True)
        self.assertIs(result["hold_counsel"], False)
        self.assertEqual(result["checkout"], "NOT_MINTED")

    def test_earnings_copy_is_rejected(self) -> None:
        result = tos.classify_instance(
            {
                "copy": "Make $200 this weekend with this pack",
                "profit_share_percent": "10",
                "partial_ownership_fraction": "1/8",
                "owner_pasted": True,
                "counsel_cleared": True,
            }
        )
        self.assertEqual(result["verdict"], "EARNINGS_CLAIM")
        self.assertIs(result["saleable"], False)
        self.assertIs(result["no_earnings_copy"], False)

    def test_invented_stripe_buy_url_is_rejected(self) -> None:
        result = tos.classify_instance(
            {
                "terms_text": "Pay at https://buy.stripe.com/fake",
                "profit_share_percent": "10",
                "partial_ownership_fraction": "1/8",
                "owner_pasted": True,
                "counsel_cleared": True,
            }
        )
        self.assertEqual(result["verdict"], "FAKE_STRIPE_URL")
        self.assertIs(result["no_fake_stripe_urls"], False)
        self.assertIs(result["saleable"], False)

    def test_template_and_door_keep_unset_slots(self) -> None:
        self.assertTrue(tos.template_has_unset_slots(ROOT))
        for blob in (self.template, self.door, self.card, self.land, self.receipt):
            self.assertIn("OWNER_UNSET", blob)
            self.assertIn("NOT_MINTED", blob)
            self.assertNotIn("337 NO", blob)
            self.assertNotIn("buy.stripe.com", blob)
            self.assertNotIn("donate.stripe.com", blob)

    def test_door_has_robots_and_no_earnings_pitch(self) -> None:
        self.assertIn('name="robots" content="index,follow"', self.door)
        self.assertIn("TokenJunkie Labs", self.door)
        self.assertNotRegex(self.door, r"(?i)make \$\d+ this weekend")

    def test_does_not_touch_scout_or_thanks_pixel_paths(self) -> None:
        self.assertFalse(
            (ROOT / "revenue" / "business_packs_marketing" / "BUYER_TIERS.md")
            .read_text(encoding="utf-8")
            .startswith("# overwritten")
        )
        self.assertIn("did not take `packs/thanks.html`", self.receipt)
        self.assertIn("did not write SCOUT marketing files", self.receipt)


if __name__ == "__main__":
    unittest.main()
