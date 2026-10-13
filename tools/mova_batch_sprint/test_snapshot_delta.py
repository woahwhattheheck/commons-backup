"""Focused stdlib regression only: python test_snapshot_delta.py."""
import unittest

from snapshot_delta import diff_snapshots, render_slack

OLD = "2026-10-08T04:00:00+00:00"
NEW = "2026-10-08T04:10:00+00:00"


def record(platform="grantfox", **updates):
    item = {
        "issue_key": "example/sponsor#42", "platform": platform,
        "funding_url": "https://%s.test/42" % platform,
        "action": "BUILD", "source_state": "none",
        "active_owner": None, "claim_state": "not_submitted",
        "competition": "none", "reward_usd": 60,
        "checked_at": OLD, "fresh": True,
    }
    item.update(updates)
    return item


def batch(at, *items, actor="woahwhattheheck"):
    return {"as_of": at, "actor": actor, "work_orders": list(items)}


class SnapshotDeltaRegression(unittest.TestCase):
    def test_timestamp_and_note_only_refresh_suppressed(self):
        old = record()
        new = record(checked_at=NEW, reason="renderer update", note="fresh source")
        result = diff_snapshots(batch(OLD, old), batch(NEW, new))
        self.assertEqual(result["events"], [])
        self.assertEqual(result["unchanged_suppressed"], 1)

    def test_planner_operation_id_change_reissues_only_affected_listing(self):
        old = record(operation_id="MOVA-example-sponsor-42-VERIFY_CLAIM-old")
        new = record(operation_id="MOVA-example-sponsor-42-VERIFY_CLAIM-new")
        first = diff_snapshots(batch(OLD, old), batch(NEW, new))
        again = diff_snapshots(batch(OLD, old), batch(NEW, new))
        self.assertEqual(first["events"], again["events"])
        self.assertEqual(first["events_count"], 1)
        event = first["events"][0]
        self.assertEqual(event["event"], "MATERIAL_CHANGE")
        self.assertEqual(event["changed_fields"]["operation_id"], {
            "from": old["operation_id"], "to": new["operation_id"]
        })
        self.assertEqual(event["planner_operation_id"], new["operation_id"])
        self.assertIn("REISSUED WORK KEY", render_slack(first))
        self.assertIn(new["operation_id"], render_slack(first))
        self.assertEqual(first["provider_queries_executed"], 0)
        self.assertEqual(diff_snapshots(batch(OLD, old), batch(NEW, old))["events"], [])
        with self.assertRaisesRegex(ValueError, "invalid work-order operation_id"):
            diff_snapshots(batch(OLD, old), batch(NEW, record(operation_id="bad\\nspoof")))

    def test_ready_to_published_original_claim_transition_idempotent(self):
        old = record(action="PUBLISH_EXISTING", source_state="ready")
        new = record(action="SUBMIT_EXISTING_CLAIM", source_state="published",
                     pr_url="https://github.com/example/sponsor/pull/9",
                     pr_author="woahwhattheheck")
        first = diff_snapshots(batch(OLD, old), batch(NEW, new))
        repeated = diff_snapshots(batch(OLD, old), batch(NEW, new))
        self.assertEqual(first["events"], repeated["events"])
        event = first["events"][0]
        self.assertEqual(event["event"], "MATERIAL_CHANGE")
        self.assertEqual(event["action"], "SUBMIT_EXISTING_CLAIM")
        self.assertIn("pr_url", event["changed_fields"])

    def test_slack_dispatch_preserves_distinct_bountyhub_funding_urls(self):
        ids = ("27c3cfe0-da9e-4192-848a-b676402de81c",
               "ef91cb1e-dd69-4a33-bd90-21c9679c9247")
        entries = [
            record("bountyhub",
                   funding_url=f"https://www.bountyhub.dev/en/bounty/view/{value}/cast",
                   action="VERIFY_CLAIM")
            for value in ids
        ]
        delta = diff_snapshots(batch(OLD), batch(NEW, *entries))
        self.assertEqual(delta["events_count"], 2)
        posted = render_slack(delta)
        for item in entries:
            self.assertIn("Snapshot listing URL: " + item["funding_url"], posted)
        self.assertEqual(len({e["operation_id"] for e in delta["events"]}), 2)

    def test_slack_uses_observed_alias_and_preserves_original_fork_link(self):
        listing_id = "27c3cfe0-da9e-4192-848a-b676402de81c"
        before = record("bountyhub",
                        funding_url=f"https://bountyhub.dev/en/bounty/view/{listing_id}/cast")
        observed = f"https://api.bountyhub.dev/api/bounties/{listing_id}"
        original = "https://github.com/woahwhattheheck/GmsCore/pull/9"
        after = record("bountyhub", funding_url=observed, action="PUBLISH_EXISTING",
                       source_pr_url=original, source_state="ready")
        delta = diff_snapshots(batch(OLD, before), batch(NEW, after))
        posted = render_slack(delta)
        self.assertIn("Snapshot listing URL: " + observed, posted)
        self.assertIn("Existing fork source: " + original, posted)
        self.assertNotIn("Snapshot listing URL: " + before["funding_url"], posted)

    def test_malformed_listing_url_is_not_rebroadcast_as_slack_instruction(self):
        hostile = "https://example.test/funding\\nCLAIM NOW"
        event = {
            "event": "NEW_LISTING", "issue_key": "example/sponsor#42",
            "platform": "bountyhub", "funding_url": hostile,
            "previous_action": None, "action": "VERIFY_CLAIM",
            "changed_fields": {}, "operation_id": "MOVA-DELTA-test",
            "planner_operation_id": None, "source_pr_url": None,
            "pr_url": None,
        }
        delta = {"previous_as_of": OLD, "as_of": NEW,
                 "events": [event], "unchanged_suppressed": 0}
        posted = render_slack(delta)
        self.assertIn("INVALID/AMBIGUOUS", posted)
        self.assertNotIn("CLAIM NOW", posted)

    def test_bountyhub_locale_slug_and_api_aliases_do_not_reopen_orders(self):
        uuid = "27c3cfe0-da9e-4192-848a-b676402de81c"
        old = record("bountyhub", action="VERIFY_CLAIM",
                     funding_url=f"https://www.bountyhub.dev/en/bounty/view/{uuid}/cast-one")
        new = record("bountyhub", action="VERIFY_CLAIM", checked_at=NEW,
                     funding_url=f"https://api.bountyhub.dev/api/bounties/{uuid.upper()}")
        result = diff_snapshots(batch(OLD, old), batch(NEW, new))
        self.assertEqual(result["events"], [])
        self.assertEqual(result["unchanged_suppressed"], 1)

    def test_bountyhub_alias_changes_keep_material_receipt_identity(self):
        uuid = "27c3cfe0-da9e-4192-848a-b676402de81c"
        first = f"https://www.bountyhub.dev/en/bounty/view/{uuid}/cast-one"
        alias = f"https://bountyhub.dev/de/bounty/view/{uuid}/cast-two"
        old = record("bountyhub", action="VERIFY_CLAIM", funding_url=first)
        after = record("bountyhub", action="VERIFY_SETTLEMENT", claim_state="paid")
        a = diff_snapshots(batch(OLD, old),
                           batch(NEW, dict(after, funding_url=first)))["events"][0]
        b = diff_snapshots(batch(OLD, old),
                           batch(NEW, dict(after, funding_url=alias)))["events"][0]
        self.assertEqual(a["event"], "MATERIAL_CHANGE")
        self.assertEqual(a["operation_id"], b["operation_id"])
        self.assertEqual(alias, b["funding_url"])
        self.assertIsNone(diff_snapshots(batch(OLD, old),
                        batch(NEW, dict(after, funding_url=alias)))["earned_usd"])

    def test_distinct_bountyhub_ids_and_unknown_urls_never_merge(self):
        first = "27c3cfe0-da9e-4192-848a-b676402de81c"
        second = "ef91cb1e-dd69-4a33-bd90-21c9679c9247"
        old = record("bountyhub", funding_url=f"https://bountyhub.dev/en/bounty/view/{first}/cast")
        new = record("bountyhub", funding_url=f"https://api.bountyhub.dev/api/bounties/{second}")
        result = diff_snapshots(batch(OLD, old), batch(NEW, new))
        self.assertEqual({x["event"] for x in result["events"]},
                         {"MISSING_FROM_SNAPSHOT", "NEW_LISTING"})
        # An unrecognized lookalike route is NOT allowed to masquerade as a
        # canonical first-party UUID or collapse an actual bounty obligation.
        unknown = record("bountyhub", funding_url=f"https://bountyhub.dev/anything/{first}")
        self.assertEqual(2, diff_snapshots(batch(OLD, old),
                                          batch(NEW, unknown))["events_count"])

    def test_duplicate_aliases_in_one_snapshot_are_an_audit_hold(self):
        uuid = "27c3cfe0-da9e-4192-848a-b676402de81c"
        old = record("bountyhub",
                     funding_url=f"https://bountyhub.dev/en/bounty/view/{uuid}/cast")
        alias = record("bountyhub",
                       funding_url=f"https://api.bountyhub.dev/api/bounties/{uuid}")
        result = diff_snapshots(batch(OLD),
                                batch(NEW, old, alias))
        self.assertEqual("CONFLICTING_LISTINGS", result["events"][0]["event"])
        self.assertEqual(2, result["events"][0]["changed_fields"]["current_rows"])

    def test_multiple_providers_remain_separate_claim_obligations(self):
        before = batch(OLD, record("algora", action="VERIFY_CLAIM"),
                       record("bountyhub", action="VERIFY_CLAIM"))
        after = batch(NEW, record("algora", action="VERIFY_SETTLEMENT",
                                  claim_state="paid"),
                      record("bountyhub", action="VERIFY_CLAIM"))
        result = diff_snapshots(before, after)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["platform"], "algora")
        self.assertIsNone(result["earned_usd"])

    def test_disappearance_is_audit_hold_not_waiver(self):
        result = diff_snapshots(batch(OLD, record()), batch(NEW))
        self.assertEqual(result["events"][0]["event"], "MISSING_FROM_SNAPSHOT")
        self.assertIn("AUDIT HOLD", render_slack(result))
        self.assertIsNone(result["earned_usd"])

    def test_duplicate_listing_warns_instead_of_erasing_claim(self):
        result = diff_snapshots(batch(OLD), batch(NEW, record(), record()))
        self.assertEqual(result["events_count"], 1)
        self.assertEqual(result["events"][0]["event"], "CONFLICTING_LISTINGS")
        self.assertEqual(result["events"][0]["changed_fields"]["current_rows"], 2)

    def test_actor_switch_and_reversed_snapshot_rejected(self):
        with self.assertRaises(ValueError):
            diff_snapshots(batch(NEW), batch(OLD))
        with self.assertRaises(ValueError):
            diff_snapshots(batch(OLD), batch(NEW, actor="tokenjunkielabs"))


if __name__ == "__main__":
    unittest.main()
