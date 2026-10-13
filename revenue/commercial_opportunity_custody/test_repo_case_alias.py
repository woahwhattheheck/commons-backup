from __future__ import annotations

import unittest

from revenue.commercial_opportunity_custody import custody as c
from revenue.commercial_opportunity_custody.test_custody import (
    ANCHOR1,
    IDENTITY,
    SRC1,
    T1,
    MemoryGitHub,
)


class RepoCaseAliasTests(unittest.TestCase):
    def test_github_repo_case_aliases_share_identity_seam_and_ref_namespace(self):
        mixed = dict(IDENTITY)
        mixed["repo"] = "WOAHWHATTHEHECK/COMMONS"

        canonical = c.Identity.parse(IDENTITY)
        aliased = c.Identity.parse(mixed)

        self.assertEqual(aliased.repo, "woahwhattheheck/commons")
        self.assertEqual(aliased, canonical)
        self.assertEqual(aliased.seam_sha256, canonical.seam_sha256)
        self.assertEqual(aliased.ref_prefix, canonical.ref_prefix)

    def test_mixed_case_double_acquire_races_same_generation_ref(self):
        canonical = c.Identity.parse(IDENTITY)
        mixed_raw = dict(IDENTITY)
        mixed_raw["repo"] = "WOAHWHATTHEHECK/COMMONS"
        aliased = c.Identity.parse(mixed_raw)
        self.assertEqual(canonical, aliased)

        a = c._plan_event(
            c.empty_state(canonical),
            action="ACQUIRE_WHOLE",
            actor_owner="ZLF-B8R3",
            actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            target_owner="ZLF-B8R3",
            target_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane=None,
            source_generation_sha256=SRC1,
            anchor_sha=ANCHOR1,
            observed_at=T1,
            legacy_evidence_sha256=None,
        )
        b = c._plan_event(
            c.empty_state(aliased),
            action="ACQUIRE_WHOLE",
            actor_owner="ZNQ-R6M3",
            actor_operation="UTILITY-SAFETY-DATA-AI-RFP-ZNQR6M3-20260913",
            target_owner="ZNQ-R6M3",
            target_operation="UTILITY-SAFETY-DATA-AI-RFP-ZNQR6M3-20260913",
            lane=None,
            source_generation_sha256=SRC1,
            anchor_sha=ANCHOR1,
            observed_at=T1,
            legacy_evidence_sha256=None,
        )

        self.assertEqual(
            canonical.generation_ref(a["generation"]),
            aliased.generation_ref(b["generation"]),
        )

        git = MemoryGitHub()
        first = c._publish_planned_event(canonical, a, git)
        second = c._publish_planned_event(aliased, b, git)

        self.assertTrue(first["event_appended"])
        self.assertFalse(second["event_appended"])
        self.assertEqual(second["reason"], "GENERATION_HELD_BY_OTHER")
        self.assertEqual(len(git.refs), 1)
        self.assertEqual(c.read_live_state(mixed_raw, git).whole_owner, "ZLF-B8R3")


if __name__ == "__main__":
    unittest.main()
