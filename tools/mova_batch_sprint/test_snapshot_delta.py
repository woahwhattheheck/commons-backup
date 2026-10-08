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
