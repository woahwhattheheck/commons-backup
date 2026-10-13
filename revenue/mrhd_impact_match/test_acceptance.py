from __future__ import annotations

import copy
import random
import unittest

from revenue.mrhd_impact_match.acceptance import (
    build_buyer_acceptance_fixture,
    reconcile,
)
from revenue.mrhd_impact_match.fixture import FIXTURE_EVENT_COUNT
from revenue.mrhd_impact_match.rail import (
    ELIGIBLE_GEOGRAPHIES,
    FOCUS_CATEGORIES,
    verify_manifest_signature,
)

KEY = b"synthetic-test-key-not-a-production-secret"


class BuyerAcceptanceTests(unittest.TestCase):
    def test_buyer_fixture_is_exactly_180_and_contains_duplicate_pair(self):
        records = build_buyer_acceptance_fixture()
        self.assertEqual(len(records), FIXTURE_EVENT_COUNT)
        self.assertEqual(len(records), 180)
        approvals = [r for r in records if r["event_type"] == "AWARD_APPROVED"]
        pairs = [
            (r["payload"]["applicant_id"], r["payload"]["project_id"])
            for r in approvals
            if r["award_id"].startswith("SYN-AWARD-")
        ]
        self.assertLess(len(set(pairs)), len(pairs))

    def test_duplicate_pair_is_held_without_dropping_approved_award(self):
        manifest = reconcile(build_buyer_acceptance_fixture(), signing_key=KEY)
        self.assertEqual(manifest["cycle"]["award_count"], 20)
        self.assertIn(
            "DUPLICATE_APPLICANT_PROJECT",
            {h["code"] for h in manifest["holds"]},
        )

    def test_all_focus_areas_and_geographies_remain_covered(self):
        approvals = [
            r
            for r in build_buyer_acceptance_fixture()
            if r["event_type"] == "AWARD_APPROVED"
        ]
        self.assertEqual(
            {
                r["payload"]["category"]
                for r in approvals
                if r["payload"]["category"] in FOCUS_CATEGORIES
            },
            set(FOCUS_CATEGORIES),
        )
        self.assertEqual(
            {
                r["payload"]["geography"]
                for r in approvals
                if r["payload"]["geography"] in ELIGIBLE_GEOGRAPHIES
            },
            set(ELIGIBLE_GEOGRAPHIES),
        )

    def test_clean_room_replay_remains_byte_identical_and_signed(self):
        records = build_buyer_acceptance_fixture()
        first = reconcile(records, signing_key=KEY)
        shuffled = copy.deepcopy(records)
        random.Random(913452).shuffle(shuffled)
        second = reconcile(shuffled, signing_key=KEY)
        self.assertEqual(first, second)
        self.assertTrue(verify_manifest_signature(first, signing_key=KEY))


if __name__ == "__main__":
    unittest.main()
