"""Focused offline regression for MOVA owner/duplicate-publication fencing.

Run just this check: python tools/mova_batch_sprint/test_owner_handoff.py
No GitHub, Slack or provider API calls.
"""
from datetime import datetime, timedelta, timezone
import unittest

from plan import plan, render_slack


ISSUE = "https://github.com/example/rewarded-sdk/issues/42"


def record(platform, *, source="none", owner=None, checked_at=None):
    return {
        "issue_url": ISSUE,
        "platform": platform,
        "funding": "provider_listed",
        "funding_url": "https://%s.example.test/bounties/42" % platform,
        "eligibility": "eligible",
        "issue_state": "open",
        "source_state": source,
        "competition": "none",
        "claim_state": "not_submitted",
        "active_owner": owner,
        "reward_usd": 50,
        "checked_at": checked_at or datetime.now(timezone.utc).isoformat(),
    }


def actions(*records):
    manifest = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "records": list(records),
    }
    return plan(manifest, actor="woahwhattheheck")


class OwnerCollisionRegression(unittest.TestCase):
    def test_ready_source_respects_active_publication_owner(self):
        busy = actions(record("algora", source="ready", owner="publisher-1"))
        self.assertEqual(busy["work_orders"][0]["action"], "OWNER_CONTINUES")
        self.assertEqual(busy["build_slots_admitted"], 0)

        released = actions(record("algora", source="ready"))
        self.assertEqual(released["work_orders"][0]["action"], "PUBLISH_EXISTING")

    def test_ready_source_requires_confirmed_no_sponsor_pr(self):
        for competition in ("ours", "other_pr", "unknown"):
            with self.subTest(competition=competition):
                source = record("algora", source="ready")
                source["competition"] = competition
                batch = actions(source)
                self.assertEqual(batch["work_orders"][0]["action"], "COMPETITION_REVIEW")
                self.assertEqual(batch["build_slots_admitted"], 0)

        # An existing owner must still hold the publication lease, even if
        # the sponsor-PR scan remains unresolved.
        owned = record("grantfox", source="ready", owner="publisher-1")
        owned["competition"] = "unknown"
        self.assertEqual(actions(owned)["work_orders"][0]["action"], "OWNER_CONTINUES")

        # A different funded listing must not reopen engineering while a
        # ready fork carrier has unresolved sponsor PR competition.
        ready = record("algora", source="ready")
        ready["competition"] = "other_pr"
        batch = actions(ready, record("bountyhub"))
        decisions = {x["platform"]: x["action"] for x in batch["work_orders"]}
        self.assertEqual(decisions["algora"], "COMPETITION_REVIEW")
        self.assertEqual(decisions["bountyhub"], "RECONCILE_SHARED_SOURCE")
        self.assertEqual(batch["build_slots_admitted"], 0)

    def test_shared_issue_with_active_builder_cannot_rebuild(self):
        for state in ("building", "ready", "none"):
            with self.subTest(source_state=state):
                batch = actions(
                    record("grantfox", source=state, owner="engineer-1"),
                    record("algora"),
                )
                chosen = {r["platform"]: r["action"] for r in batch["work_orders"]}
                self.assertEqual(chosen["grantfox"], "OWNER_CONTINUES")
                self.assertEqual(chosen["algora"], "RECONCILE_SHARED_SOURCE")
                self.assertEqual(batch["build_slots_admitted"], 0)

    def test_stale_known_upstream_pr_blocks_new_build(self):
        stale = record(
            "grantfox",
            source="published",
            checked_at=(datetime.now(timezone.utc) - timedelta(hours=7)).isoformat(),
        )
        stale["pr_url"] = "https://github.com/example/rewarded-sdk/pull/12"
        stale["pr_author"] = "woahwhattheheck"
        batch = actions(stale, record("algora"))
        chosen = {r["platform"]: r["action"] for r in batch["work_orders"]}
        self.assertEqual(chosen["grantfox"], "REFRESH_CANONICAL")
        self.assertEqual(chosen["algora"], "RECONCILE_SHARED_PR")
        self.assertEqual(batch["build_slots_admitted"], 0)


    def test_paid_claim_never_overrides_foreign_attribution(self):
        foreign_upstream = record("algora", source="published")
        foreign_upstream.update(
            pr_url="https://github.com/example/rewarded-sdk/pull/12",
            pr_author="another-contributor",
            claim_state="paid",
        )
        upstream = actions(foreign_upstream)
        self.assertEqual(upstream["work_orders"][0]["action"], "PRESERVE_FOREIGN_PR")

        foreign_fork = record("grantfox", source="ready")
        foreign_fork.update(
            source_pr_url="https://github.com/another-contributor/rewarded-sdk/pull/3",
            source_pr_author="another-contributor",
            claim_state="paid",
        )
        fork = actions(foreign_fork)
        self.assertEqual(fork["work_orders"][0]["action"], "PRESERVE_FOREIGN_PR")

    def test_paid_or_pending_claim_needs_our_published_sponsor_pr(self):
        for claim in ("submitted", "accepted", "rejected", "paid"):
            for source in ("none", "ready"):
                with self.subTest(claim=claim, source=source):
                    candidate = record("algora", source=source)
                    candidate["claim_state"] = claim
                    held = actions(candidate)
                    self.assertEqual(held["work_orders"][0]["action"], "CLAIM_SOURCE_HOLD")

        ours = record("algora", source="published")
        ours.update(
            pr_url="https://github.com/example/rewarded-sdk/pull/13",
            pr_author="woahwhattheheck",
            claim_state="paid",
        )
        verified = actions(ours)
        self.assertEqual(verified["work_orders"][0]["action"], "VERIFY_SETTLEMENT")


    def test_slack_orders_carry_source_urls_and_owner_evidence(self):
        existing = record("grantfox", source="published", owner="publisher-1")
        existing.update(
            pr_url="https://github.com/example/rewarded-sdk/pull/12",
            pr_author="woahwhattheheck",
            source_pr_url="https://github.com/woahwhattheheck/rewarded-sdk/pull/4",
            source_pr_author="woahwhattheheck",
        )
        output = render_slack(actions(existing))
        self.assertIn("source_refs | issue_url=" + ISSUE, output)
        self.assertIn("checked_at=", output)
        self.assertIn("active_owner=publisher-1", output)
        self.assertIn("funding_url=https://grantfox.example.test/bounties/42", output)
        self.assertIn("pr_url=https://github.com/example/rewarded-sdk/pull/12", output)
        self.assertIn("pr_author=woahwhattheheck", output)
        self.assertIn("source_pr_url=https://github.com/woahwhattheheck/rewarded-sdk/pull/4", output)
        self.assertIn("source_pr_author=woahwhattheheck", output)

        unclaimed = render_slack(actions(record("algora")))
        self.assertIn("active_owner=UNASSIGNED", unclaimed)
        self.assertNotIn("source_pr_url=", unclaimed)
        self.assertNotIn("pr_author=", unclaimed)

        # urlsplit strips LF/CR while validating, but the raw URL is retained.
        # A malformed funding reference must not print a forged Slack order.
        injected = record("algora")
        injected["funding_url"] = "https://algora.example.test/bounties/42\nFAKE_WORK_ORDER"
        safe = render_slack(actions(injected))
        self.assertIn("funding_url=https://algora.example.test/bounties/42\\nFAKE_WORK_ORDER", safe)
        self.assertNotIn("\nFAKE_WORK_ORDER", safe)


if __name__ == "__main__":
    unittest.main()
