import json
import tempfile
import unittest
from pathlib import Path

from tools.grantfox_fwc26_workfeed.compile import (
    WorkfeedError,
    classify,
    compile_records,
    main,
    render_markdown,
)


LABELS = [
    "GRANTFOX OSS",
    "MAYBE REWARDED",
    "Official Campaign | FWC26",
]


def issue(**overrides):
    base = {
        "repository": "StableRoute-Org/Stableroute-backend",
        "number": 551,
        "title": "sliding-window rate limiter scoped per tenant/API key",
        "url": "https://github.com/StableRoute-Org/Stableroute-backend/issues/551",
        "state": "open",
        "labels": LABELS,
        "assignees": [],
        "body": (
            "Part of the GrantFox OSS / Official Campaign (FWC26) — this task may be rewarded. "
            "Run `npm run lint`, `npm test`, and `npm run build` locally."
        ),
    }
    base.update(overrides)
    return base


class WorkfeedTests(unittest.TestCase):
    def test_ready_discretionary_issue(self):
        item = classify(issue())
        self.assertEqual(item.status, "READY")
        self.assertEqual(item.reward_class, "DISCRETIONARY_CAMPAIGN_REWARD")
        self.assertEqual(item.commands, ("npm run lint", "npm test", "npm run build"))

    def test_explicit_amount_is_evidence_not_guarantee(self):
        item = classify(issue(body="Campaign text says 400 USDC pool and this task may be rewarded."))
        self.assertEqual(item.reward_class, "EXPLICIT_AMOUNT_MENTIONED")
        self.assertEqual(item.explicit_reward_mentions, ("400 USDC",))
        self.assertNotIn("guarantee", item.reason.lower())

    def test_assignment_blocks_ready(self):
        item = classify(issue(assignees=[{"login": "someone"}]))
        self.assertEqual(item.status, "ASSIGNED")

    def test_official_campaign_bot_assignment_blocks_vacant_search_result(self):
        bot = {
            "user": {"login": "grantfox-oss[bot]"},
            "body": "🦊 **GrantFox** — @Primex-hub has been assigned to this issue as part of the **Official Campaign | FWC26** campaign!",
        }
        item = classify(issue(assignees=[], issue_comments=[bot]))
        self.assertEqual(item.status, "ASSIGNED")
        self.assertEqual(item.assignees, ("Primex-hub",))
        self.assertIn("Primex-hub", item.reason)

    def test_unverified_quoted_assignment_is_not_official(self):
        quoted = {
            "user": {"login": "other-contributor"},
            "body": "@Primex-hub has been assigned to this issue",
        }
        self.assertEqual(classify(issue(issue_comments=[quoted])).status, "READY")

    def test_bot_assignments_union_native_assignees_without_duplicate(self):
        bot = {
            "user": {"login": "grantfox-oss[bot]"},
            "body": "@Primex-hub has been assigned to this issue",
        }
        item = classify(issue(assignees=["maintainer", "Primex-hub"], issue_comments=[bot, bot]))
        self.assertEqual(item.status, "ASSIGNED")
        self.assertEqual(item.assignees, ("maintainer", "Primex-hub"))

    def test_malformed_comment_census_rejected(self):
        with self.assertRaisesRegex(WorkfeedError, "issue_comments must be a list"):
            classify(issue(issue_comments="not a verified comment collection"))

    def test_claim_instruction_requires_claim_step(self):
        item = classify(issue(body="Comment on this issue and wait for assignment before coding. Maybe rewarded."))
        self.assertEqual(item.status, "CLAIM_REQUIRED")
        self.assertTrue(item.claim_required)

    def test_observed_claimant_blocks_ready(self):
        item = classify(issue(claimant_comments=[{"user": {"login": "alice"}, "body": "I would like to work on this"}]))
        self.assertEqual(item.status, "CLAIMED_OR_PR_OPEN")
        self.assertEqual(item.observed_claimants, ("alice",))

    def test_open_pr_blocks_ready(self):
        item = classify(issue(open_pull_requests=[{"url": "https://github.com/StableRoute-Org/Stableroute-backend/pull/572"}]))
        self.assertEqual(item.status, "CLAIMED_OR_PR_OPEN")
        self.assertEqual(item.open_pull_requests, ("https://github.com/StableRoute-Org/Stableroute-backend/pull/572",))

    def test_active_swarm_claim_blocks_duplicate_take(self):
        item = classify(issue(coordination_claims=[{"owner": "ZZ-Sol-Kestrel"}]))
        self.assertEqual(item.status, "SWARM_TAKEN")
        self.assertEqual(item.coordination_owners, ("ZZ-Sol-Kestrel",))

    def test_stale_snapshot_blocks_ready(self):
        item = classify(
            issue(observed_at="2026-09-19T17:00:00-04:00"),
            fresh_after="2026-09-19T17:30:00-04:00",
        )
        self.assertEqual(item.status, "STALE_EVIDENCE")
        self.assertIn("older than", item.reason)

    def test_missing_observed_at_is_stale_when_floor_requested(self):
        item = classify(issue(), fresh_after="2026-09-19T17:30:00-04:00")
        self.assertEqual(item.status, "STALE_EVIDENCE")
        self.assertIn("no observed_at", item.reason)

    def test_fresh_snapshot_remains_ready(self):
        item = classify(
            issue(observed_at="2026-09-19T17:31:00-04:00"),
            fresh_after="2026-09-19T17:30:00-04:00",
        )
        self.assertEqual(item.status, "READY")

    def test_naive_freshness_timestamp_refused(self):
        with self.assertRaisesRegex(WorkfeedError, "timezone offset"):
            classify(issue(observed_at="2026-09-19T17:31:00"), fresh_after="2026-09-19T17:30:00-04:00")

    def test_malformed_coordination_fields_refused(self):
        with self.assertRaisesRegex(WorkfeedError, "claimant_comments must be a list"):
            classify(issue(claimant_comments={"user": "alice"}))

    def test_missing_campaign_label_is_ineligible(self):
        item = classify(issue(labels=LABELS[:2]))
        self.assertEqual(item.status, "INELIGIBLE")
        self.assertIn("official campaign | fwc26", item.reason)

    def test_closed_issue_is_ineligible(self):
        self.assertEqual(classify(issue(state="closed")).status, "INELIGIBLE")

    def test_security_sensitive_detection(self):
        item = classify(issue(title="admin settlement authorization guard"))
        self.assertTrue(item.security_sensitive)

    def test_security_sensitive_secret_redaction_detection(self):
        item = classify(issue(title="Add SDK secret redaction and unsafe logging protections"))
        self.assertTrue(item.security_sensitive)

    def test_security_sensitive_vault_fund_safety_detection(self):
        item = classify(issue(title="Add token transfer rollback verification", body="This is fund-safety critical for vault state."))
        self.assertTrue(item.security_sensitive)

    def test_duplicate_issue_key_refused(self):
        with self.assertRaisesRegex(WorkfeedError, "duplicate issue key"):
            compile_records([issue(), issue()])

    def test_boolean_issue_number_refused(self):
        with self.assertRaisesRegex(WorkfeedError, "positive integer"):
            classify(issue(number=True))

    def test_non_github_url_refused(self):
        with self.assertRaisesRegex(WorkfeedError, "canonical GitHub"):
            classify(issue(url="https://example.com/issues/551"))

    def test_markdown_contains_authority_warning(self):
        text = render_markdown([classify(issue())])
        self.assertIn("does **not** claim", text)
        self.assertIn("READY", text)
        self.assertIn("DISCRETIONARY_CAMPAIGN_REWARD", text)

    def test_cli_is_create_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "issues.json"
            source.write_text(json.dumps([issue()]), encoding="utf-8")
            out = root / "out"
            self.assertEqual(main([str(source), "--out-dir", str(out)]), 0)
            self.assertTrue((out / "queue.json").exists())
            self.assertTrue((out / "QUEUE.md").exists())
            with self.assertRaisesRegex(WorkfeedError, "already exists"):
                main([str(source), "--out-dir", str(out)])

    def test_json_output_authority_flags_are_false(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "issues.jsonl"
            source.write_text(json.dumps(issue()) + "\n", encoding="utf-8")
            out = root / "out"
            main([str(source), "--out-dir", str(out)])
            payload = json.loads((out / "queue.json").read_text(encoding="utf-8"))
            self.assertIsNone(payload["evidence_fresh_after"])
            self.assertEqual(
                payload["authority"],
                {
                    "assigns_issues": False,
                    "claims_issues": False,
                    "guarantees_payment": False,
                    "mutates_external_systems": False,
                },
            )


if __name__ == "__main__":
    unittest.main()
