# SPDX-License-Identifier: MIT
from __future__ import annotations

import copy
import hashlib
import json
import unittest

from revenue.autonoma_carrier_landing_core.core import (
    LandingInputError,
    apply_plan,
    build_plan,
    empty_state,
    make_branch,
    verify_plan,
)


BASE = "a" * 64
STALE = "b" * 64
BAD_MANIFEST = "c" * 64


def tree(label: str) -> str:
    return hashlib.sha256(f"tree:{label}".encode()).hexdigest()


def redigest(plan: dict) -> None:
    body = {key: value for key, value in plan.items() if key != "receipt_sha256"}
    plan["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def six_branch_fixture() -> dict:
    return {
        "schema_version": 1,
        "batch_id": "autonoma-six-branch-acceptance-v1",
        "base_sha": BASE,
        "carrier_prefix": "carrier/",
        "branches": [
            make_branch(
                branch_id="valid-alpha",
                order=10,
                base_sha=BASE,
                paths=["carrier/alpha/adapter.py", "carrier/alpha/test_adapter.py"],
                purpose="bounded alpha carrier",
                candidate_tree_sha=tree("alpha"),
            ),
            make_branch(
                branch_id="forbidden-path",
                order=20,
                base_sha=BASE,
                paths=["payments/live_checkout.py"],
                purpose="must never escape the carrier root",
                candidate_tree_sha=tree("forbidden"),
            ),
            make_branch(
                branch_id="stale-base",
                order=30,
                base_sha=STALE,
                paths=["carrier/stale/adapter.py"],
                purpose="stale carrier",
                candidate_tree_sha=tree("stale"),
            ),
            make_branch(
                branch_id="manifest-mismatch",
                order=40,
                base_sha=BASE,
                paths=["carrier/manifest/adapter.py"],
                purpose="manifest digest mismatch",
                candidate_tree_sha=tree("manifest"),
                manifest_digest_override=BAD_MANIFEST,
            ),
            make_branch(
                branch_id="test-failure",
                order=50,
                base_sha=BASE,
                paths=["carrier/red/adapter.py"],
                purpose="red carrier",
                candidate_tree_sha=tree("red"),
                premerge_status="FAIL",
            ),
            make_branch(
                branch_id="valid-omega",
                order=60,
                base_sha=BASE,
                paths=["carrier/omega/adapter.py", "carrier/omega/test_adapter.py"],
                purpose="bounded omega carrier",
                candidate_tree_sha=tree("omega"),
            ),
        ],
    }


class CarrierLandingAcceptanceTests(unittest.TestCase):
    def test_six_branch_fixture_lands_exactly_two_in_declared_order(self):
        plan = build_plan(six_branch_fixture())
        self.assertEqual(plan["landing_order"], ["valid-alpha", "valid-omega"])
        dispositions = {
            item["branch_id"]: (item["disposition"], item["reason_codes"])
            for item in plan["branches"]
        }
        self.assertEqual(dispositions["valid-alpha"], ("LAND", []))
        self.assertEqual(dispositions["valid-omega"], ("LAND", []))
        self.assertEqual(dispositions["forbidden-path"], ("HOLD", ["FORBIDDEN_PATH"]))
        self.assertEqual(dispositions["stale-base"], ("HOLD", ["STALE_BASE"]))
        self.assertEqual(
            dispositions["manifest-mismatch"], ("HOLD", ["MANIFEST_MISMATCH"])
        )
        self.assertEqual(dispositions["test-failure"], ("HOLD", ["TEST_FAILURE"]))

    def test_provider_intents_never_force_push_or_delete_unrelated_branches(self):
        plan = build_plan(six_branch_fixture())
        self.assertEqual(
            plan["provider_intents"],
            [
                {
                    "operation": "MERGE",
                    "branch_id": "valid-alpha",
                    "force": False,
                    "delete_branch": False,
                },
                {
                    "operation": "MERGE",
                    "branch_id": "valid-omega",
                    "force": False,
                    "delete_branch": False,
                },
            ],
        )

    def test_apply_keeps_main_green_after_each_landing_and_replay_is_zero_merge(self):
        plan = build_plan(six_branch_fixture())
        first = apply_plan(plan, empty_state())
        self.assertEqual(first.new_merges, 2)
        self.assertEqual(
            [event["branch_id"] for event in first.merge_events],
            ["valid-alpha", "valid-omega"],
        )
        self.assertTrue(all(event["main_green_after"] for event in first.merge_events))
        self.assertTrue(first.state["main_green"])

        second = apply_plan(plan, first.state)
        self.assertEqual(second.new_merges, 0)
        self.assertEqual(second.merge_events, ())
        self.assertEqual(second.receipt, first.receipt)
        self.assertEqual(second.state, first.state)

    def test_receipt_is_order_invariant_to_json_serialization(self):
        payload = six_branch_fixture()
        round_trip = json.loads(json.dumps(payload, sort_keys=False))
        self.assertEqual(build_plan(payload), build_plan(round_trip))

    def test_tampered_receipt_fails_closed(self):
        plan = build_plan(six_branch_fixture())
        tampered = copy.deepcopy(plan)
        tampered["provider_intents"][0]["force"] = True
        with self.assertRaisesRegex(LandingInputError, "digest mismatch"):
            verify_plan(tampered)

    def test_redigesting_a_destructive_intent_still_fails_closed(self):
        plan = build_plan(six_branch_fixture())
        tampered = copy.deepcopy(plan)
        tampered["provider_intents"][0]["delete_branch"] = True
        redigest(tampered)
        with self.assertRaisesRegex(LandingInputError, "canonical landing order"):
            verify_plan(tampered)

    def test_redigesting_a_held_branch_into_landing_order_still_fails_closed(self):
        plan = build_plan(six_branch_fixture())
        tampered = copy.deepcopy(plan)
        forbidden = next(
            row for row in tampered["branches"] if row["branch_id"] == "forbidden-path"
        )
        forbidden["disposition"] = "LAND"
        forbidden["reason_codes"] = []
        tampered["landing_order"].insert(1, "forbidden-path")
        tampered["provider_intents"].insert(
            1,
            {
                "operation": "MERGE",
                "branch_id": "forbidden-path",
                "force": False,
                "delete_branch": False,
            },
        )
        redigest(tampered)
        with self.assertRaisesRegex(LandingInputError, "escapes the carrier prefix"):
            verify_plan(tampered)

    def test_redigesting_unknown_branch_into_provider_intent_fails_closed(self):
        plan = build_plan(six_branch_fixture())
        tampered = copy.deepcopy(plan)
        tampered["landing_order"].append("forged-branch")
        tampered["provider_intents"].append(
            {
                "operation": "MERGE",
                "branch_id": "forged-branch",
                "force": False,
                "delete_branch": False,
            }
        )
        redigest(tampered)
        with self.assertRaisesRegex(LandingInputError, "does not match LAND dispositions"):
            verify_plan(tampered)

    def test_overlapping_valid_carrier_is_held(self):
        payload = six_branch_fixture()
        payload["branches"].append(
            make_branch(
                branch_id="valid-but-colliding",
                order=15,
                base_sha=BASE,
                paths=["carrier/alpha/adapter.py"],
                purpose="collision",
                candidate_tree_sha=tree("collision"),
            )
        )
        plan = build_plan(payload)
        item = next(
            branch
            for branch in plan["branches"]
            if branch["branch_id"] == "valid-but-colliding"
        )
        self.assertEqual(item["disposition"], "HOLD")
        self.assertEqual(item["reason_codes"], ["OWNERSHIP_COLLISION"])

    def test_unknown_fields_fail_closed(self):
        payload = six_branch_fixture()
        payload["branches"][0]["surprise"] = "ignored-by-lax-parsers"
        with self.assertRaisesRegex(LandingInputError, "unknown fields"):
            build_plan(payload)

    def test_missing_fields_fail_closed(self):
        payload = six_branch_fixture()
        del payload["branches"][0]["candidate_tree_sha"]
        with self.assertRaisesRegex(LandingInputError, "missing fields"):
            build_plan(payload)

    def test_unsafe_paths_fail_closed_before_planning(self):
        payload = six_branch_fixture()
        payload["branches"][0]["manifest"]["paths"][0] = "carrier/alpha/../payments.py"
        with self.assertRaisesRegex(LandingInputError, "unsafe path segment"):
            build_plan(payload)

    def test_uppercase_digest_is_rejected_instead_of_silently_normalized(self):
        payload = six_branch_fixture()
        payload["base_sha"] = BASE.upper()
        with self.assertRaisesRegex(LandingInputError, "lowercase SHA-256"):
            build_plan(payload)

    def test_non_boolean_main_state_cannot_pass_truthiness(self):
        plan = build_plan(six_branch_fixture())
        state = empty_state()
        state["main_green"] = 1
        with self.assertRaisesRegex(LandingInputError, "main_green must be boolean"):
            apply_plan(plan, state)

    def test_existing_branch_outside_receipt_blocks_ambiguous_reapply(self):
        plan = build_plan(six_branch_fixture())
        state = empty_state()
        state["landed_branches"] = ["valid-alpha"]
        with self.assertRaisesRegex(LandingInputError, "already landed outside this receipt"):
            apply_plan(plan, state)

    def test_duplicate_state_entries_fail_closed(self):
        plan = build_plan(six_branch_fixture())
        state = empty_state()
        state["landed_branches"] = ["old", "old"]
        with self.assertRaisesRegex(LandingInputError, "must not contain duplicates"):
            apply_plan(plan, state)

    def test_plan_contains_no_clock_or_provider_generated_state(self):
        plan = build_plan(six_branch_fixture())
        serialized = json.dumps(plan, sort_keys=True)
        self.assertNotIn("timestamp", serialized.lower())
        self.assertNotIn("token", serialized.lower())
        self.assertNotIn("delete_branch\": true", serialized.lower())
        self.assertNotIn("force\": true", serialized.lower())


if __name__ == "__main__":
    unittest.main()
