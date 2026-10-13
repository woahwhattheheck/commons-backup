import unittest

from claim_liveness import audit_events

NOW = 2_000.0


def e(ts, session="A", event="CLAIM"):
    return {"ts": ts, "lane": "L", "session": session, "event": event}


class ClaimArbitrationTests(unittest.TestCase):
    def row(self, events):
        report = audit_events(events, as_of=NOW, ttl_seconds=100)
        return report, report["lanes"][0]

    def test_earliest_claim_wins_despite_later_heartbeat(self):
        report, row = self.row([
            e(1910, "A"), e(1920, "B"), e(1999, "A", "HEARTBEAT")
        ])
        self.assertEqual("COLLISION", row["status"])
        self.assertEqual("A", row["arbitration"]["preferred_owner"])
        self.assertEqual(["B"], row["arbitration"]["yield_candidates"])
        self.assertFalse(report["policy"]["arbitration_is_overwrite_authority"])

    def test_equal_earliest_claims_fail_closed(self):
        report, row = self.row([e(1950, "B"), e(1950, "A")])
        arbitration = row["arbitration"]
        self.assertIsNone(arbitration["preferred_owner"])
        self.assertEqual(["A", "B"], arbitration["tied_earliest_claimants"])
        self.assertEqual([], arbitration["yield_candidates"])
        self.assertTrue(report["policy"]["equal_earliest_claim_tie_fails_closed"])

    def test_later_claim_yields_even_with_earliest_tie(self):
        _, row = self.row([e(1950, "B"), e(1960, "C"), e(1950, "A")])
        arbitration = row["arbitration"]
        self.assertIsNone(arbitration["preferred_owner"])
        self.assertEqual(["A", "B"], arbitration["tied_earliest_claimants"])
        self.assertEqual(["C"], arbitration["yield_candidates"])

    def test_reclaim_after_terminal_starts_new_claim_epoch(self):
        _, row = self.row([
            e(1900, "A"), e(1910, "A", "RELEASED"),
            e(1940, "B"), e(1950, "A"),
        ])
        self.assertEqual("B", row["arbitration"]["preferred_owner"])
        self.assertEqual(["A"], row["arbitration"]["yield_candidates"])
        owners = {owner["session"]: owner for owner in row["owners"]}
        self.assertEqual(1950.0, owners["A"]["claim_ts"])

    def test_stale_earlier_claim_does_not_beat_fresh_owner(self):
        _, row = self.row([e(1800, "A"), e(1950, "B")])
        self.assertEqual("ACTIVE_WITH_STALE_OWNER", row["status"])
        self.assertEqual("B", row["arbitration"]["preferred_owner"])
        self.assertEqual([], row["arbitration"]["yield_candidates"])


if __name__ == "__main__":
    unittest.main()
