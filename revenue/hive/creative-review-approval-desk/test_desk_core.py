#!/usr/bin/env python3
from __future__ import annotations

from _test_support import *  # noqa: F401,F403


class CreativeReviewDeskCoreTests(CreativeReviewDeskTestCase):
    def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(self) -> None:
        with self.assertRaises(InvalidInput):
            strict_json_loads('{"a":1,"a":2}')
        with self.assertRaises(InvalidInput):
            strict_json_loads('{"a":NaN}')

    def test_spec_normalization_is_order_invariant_and_rejects_bool_alias(self) -> None:
        reversed_spec = json.loads(json.dumps(self.spec))
        reversed_spec["assets"].reverse()
        for asset in reversed_spec["assets"]:
            asset["destinations"].reverse()
            asset["required_roles"].reverse()
        self.assertEqual(normalize_spec(self.spec), normalize_spec(reversed_spec))
        broken = json.loads(json.dumps(self.spec))
        broken["policy"]["prohibit_author_review"] = 1
        with self.assertRaises(InvalidInput):
            normalize_spec(broken)

    def test_initial_campaign_is_hold_until_exact_assets_exist(self) -> None:
        self.create()
        status = self.desk.status("fall-launch")["derived"]
        self.assertEqual(status["campaign_state"], "HOLD")
        self.assertIn("hero-image:MISSING_CURRENT_VERSION", status["campaign_holds"])
        self.assertIn("social-video:MISSING_CURRENT_VERSION", status["campaign_holds"])

    def test_submitted_assets_require_assignments_and_approvals(self) -> None:
        self.create()
        self.submit_hero()
        self.submit_video()
        status = self.desk.status("fall-launch")["derived"]
        self.assertEqual(status["campaign_state"], "REVIEW_REQUIRED")
        hero = next(item for item in status["assets"] if item["asset_id"] == "hero-image")
        self.assertIn("MISSING_ASSIGNMENT:brand", hero["review"])
        self.assertIn("MISSING_APPROVAL:legal", hero["review"])

    def test_full_workflow_reaches_ready_with_all_authority_false(self) -> None:
        self.make_ready()
        derived = self.desk.status("fall-launch")["derived"]
        self.assertEqual(derived["campaign_state"], "READY_FOR_OWNER_HANDOFF")
        self.assertEqual(derived["authority"], AUTHORITY)
        self.assertFalse(any(derived["authority"].values()))

    def test_author_cannot_review_own_asset(self) -> None:
        self.create()
        self.submit_hero()
        with self.assertRaises(InvalidState):
            self.desk.assign_reviewer("bad-author", "fall-launch", "hero-image", "brand", "designer-a")

    def test_distinct_reviewer_policy_prevents_role_collision(self) -> None:
        self.create()
        self.submit_hero()
        self.desk.assign_reviewer("one-role", "fall-launch", "hero-image", "brand", "reviewer-one")
        with self.assertRaises(InvalidState):
            self.desk.assign_reviewer("two-role", "fall-launch", "hero-image", "legal", "reviewer-one")

    def test_exact_idempotent_replay_and_semantic_conflict(self) -> None:
        first = self.desk.create_campaign("same-request", self.spec)
        second = self.desk.create_campaign("same-request", self.spec)
        self.assertEqual(first, second)
        changed = json.loads(json.dumps(self.spec))
        changed["name"] = "Other"
        with self.assertRaises(IdempotencyConflict):
            self.desk.create_campaign("same-request", changed)

    def test_new_exact_bytes_create_version_and_invalidate_old_approval(self) -> None:
        self.make_ready()
        changed = self.root / "hero-v2.bin"
        changed.write_bytes(b"synthetic hero generation 2")
        result = self.submit_hero("submit-hero-v2", changed)
        self.assertEqual(result["version"], 2)
        status = self.desk.status("fall-launch")["derived"]
        self.assertEqual(status["campaign_state"], "REVIEW_REQUIRED")
        hero = next(item for item in status["assets"] if item["asset_id"] == "hero-image")
        self.assertEqual(hero["current_version"], 2)
        self.assertIn("MISSING_ASSIGNMENT:brand", hero["review"])

    def test_campaign_requirement_revision_invalidates_prior_approvals(self) -> None:
        self.make_ready()
        revised = json.loads(json.dumps(self.spec))
        revised["assets"][0]["destinations"].append("display-network")
        result = self.desk.revise_campaign("revise-2", 1, revised)
        self.assertEqual(result["revision"], 2)
        status = self.desk.status("fall-launch")["derived"]
        self.assertEqual(status["campaign_state"], "REVIEW_REQUIRED")
        self.assertTrue(all(item["review"] for item in status["assets"]))

    def test_stale_expected_revision_fails_closed(self) -> None:
        self.create()
        revised = json.loads(json.dumps(self.spec))
        revised["name"] = "Revision two"
        self.desk.revise_campaign("revise-ok", 1, revised)
        with self.assertRaises(InvalidState):
            self.desk.revise_campaign("revise-stale", 1, self.spec)

    def test_media_type_and_metadata_mismatch_are_rejected(self) -> None:
        self.create()
        with self.assertRaises(InvalidState):
            self.desk.submit_asset(
                "wrong-type",
                "fall-launch",
                "hero-image",
                "designer-a",
                self.hero,
                "video",
                self.image_metadata(),
                "fixture",
            )
        wrong = self.image_metadata()
        wrong["width"] = 1199
        with self.assertRaises(InvalidState):
            self.desk.submit_asset(
                "wrong-size",
                "fall-launch",
                "hero-image",
                "designer-a",
                self.hero,
                "image",
                wrong,
                "fixture",
            )

    def test_unassigned_reviewer_cannot_annotate_or_decide(self) -> None:
        self.create()
        self.submit_hero()
        with self.assertRaises(InvalidState):
            self.desk.add_annotation(
                "bad-ann",
                "ann-bad",
                "fall-launch",
                "hero-image",
                "brand",
                "intruder",
                {"kind": "GLOBAL"},
                "OTHER",
                "not assigned",
            )
        with self.assertRaises(InvalidState):
            self.desk.decide(
                "bad-decision",
                "fall-launch",
                "hero-image",
                "brand",
                "intruder",
                "APPROVE",
                "",
            )

    def test_open_annotation_blocks_approval_until_resolved(self) -> None:
        self.create()
        self.submit_hero()
        self.assign_hero()
        self.desk.add_annotation(
            "ann-open",
            "annotation-1",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand",
            {"kind": "PIXEL_RECT", "x": 5, "y": 6, "width": 100, "height": 120},
            "BRAND_REVIEW_REQUIRED",
            "owner needs to inspect this region",
        )
        with self.assertRaises(InvalidState):
            self.desk.decide(
                "approve-too-soon",
                "fall-launch",
                "hero-image",
                "brand",
                "reviewer-brand",
                "APPROVE",
                "",
            )
        self.assertEqual(self.desk.status("fall-launch")["derived"]["campaign_state"], "HOLD")
        # social-video is missing, so campaign is HOLD; hero itself is CHANGES_REQUESTED.
        hero = next(
            item
            for item in self.desk.status("fall-launch")["derived"]["assets"]
            if item["asset_id"] == "hero-image"
        )
        self.assertEqual(hero["state"], "CHANGES_REQUESTED")
        self.desk.resolve_annotation("resolve-1", "fall-launch", "annotation-1", "designer-a")
        self.desk.decide(
            "approve-after-resolve",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand",
            "APPROVE",
            "resolved and reviewed",
        )

    def test_changes_requested_can_be_superseded_by_approve(self) -> None:
        self.create()
        self.submit_hero()
        self.submit_video()
        self.assign_hero()
        self.assign_video()
        self.desk.decide(
            "changes-first",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand",
            "CHANGES_REQUESTED",
            "change owner-supplied layout",
        )
        derived = self.desk.status("fall-launch")["derived"]
        self.assertEqual(derived["campaign_state"], "CHANGES_REQUESTED")
        self.desk.decide(
            "approve-later",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand",
            "APPROVE",
            "revision accepted for workflow purposes",
        )
        self.desk.decide("approve-legal", "fall-launch", "hero-image", "legal", "reviewer-legal", "APPROVE", "")
        self.approve_video()
        self.assertEqual(self.desk.status("fall-launch")["derived"]["campaign_state"], "READY_FOR_OWNER_HANDOFF")

    def test_location_validation_for_pixel_and_time_ranges(self) -> None:
        self.create()
        self.submit_hero()
        self.submit_video()
        self.assign_hero()
        self.assign_video()
        self.desk.add_annotation(
            "rect-ok",
            "rect-1",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand",
            {"kind": "PIXEL_RECT", "x": 0, "y": 0, "width": 1200, "height": 628},
            "OTHER",
            "whole frame",
        )
        self.desk.add_annotation(
            "time-ok",
            "time-1",
            "fall-launch",
            "social-video",
            "brand",
            "reviewer-v-brand",
            {"kind": "TIME_MS", "start_ms": 1000, "end_ms": 2000},
            "CONTENT",
            "synthetic timestamp note",
        )
        with self.assertRaises(InvalidInput):
            self.desk.add_annotation(
                "rect-bad",
                "rect-bad",
                "fall-launch",
                "hero-image",
                "brand",
                "reviewer-brand",
                {"kind": "PIXEL_RECT", "x": 1199, "y": 0, "width": 2, "height": 1},
                "OTHER",
                "outside",
            )
        with self.assertRaises(InvalidInput):
            self.desk.add_annotation(
                "time-on-image",
                "time-bad",
                "fall-launch",
                "hero-image",
                "brand",
                "reviewer-brand",
                {"kind": "TIME_MS", "start_ms": 1, "end_ms": 2},
                "OTHER",
                "wrong media type",
            )



if __name__ == "__main__":
    unittest.main(verbosity=2)
