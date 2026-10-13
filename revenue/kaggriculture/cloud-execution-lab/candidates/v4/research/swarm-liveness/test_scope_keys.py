import itertools
import unittest

from claim_liveness import audit_events

NOW = 2_000.0


def ev(ts, lane, session, event="CLAIM", scope_key=None):
    row = {"ts": ts, "lane": lane, "session": session, "event": event}
    if scope_key is not None:
        row["scope_key"] = scope_key
    return row


class ScopeKeyTests(unittest.TestCase):
    def report(self, events):
        return audit_events(events, as_of=NOW, ttl_seconds=100)

    def test_different_lanes_same_scope_collide(self):
        report = self.report([
            ev(1950, "UNITPIPE", "A", scope_key="unit-pipeline"),
            ev(1960, "TILEPIPE", "B", scope_key="unit-pipeline"),
        ])
        self.assertEqual(0, report["summary"]["collisions"])
        self.assertEqual(1, report["summary"]["cross_lane_scoped_collisions"])
        row = report["scope_groups"][0]
        self.assertEqual("COLLISION", row["status"])
        self.assertEqual(["TILEPIPE", "UNITPIPE"], row["lanes"])
        self.assertEqual("A", row["arbitration"]["preferred_owner"])
        self.assertEqual(["B"], row["arbitration"]["yield_candidates"])

    def test_same_session_aliases_collapse_to_one_owner(self):
        report = self.report([
            ev(1940, "FLOORDRAIN", "A", scope_key="floor-liquidation"),
            ev(1950, "FLOORSINK", "A", scope_key="floor-liquidation"),
        ])
        row = report["scope_groups"][0]
        self.assertEqual("ACTIVE", row["status"])
        self.assertEqual(["A"], row["fresh_active_owners"])
        self.assertEqual(1940.0, row["owners"][0]["claim_ts"])
        self.assertEqual(["FLOORDRAIN", "FLOORSINK"], row["owners"][0]["lanes"])

    def test_heartbeat_scope_drift_is_anomaly_and_does_not_rekey(self):
        report = self.report([
            ev(1950, "L", "A", scope_key="alpha"),
            ev(1990, "L", "A", "HEARTBEAT", scope_key="beta"),
        ])
        self.assertEqual("alpha", report["lanes"][0]["owners"][0]["scope_key"])
        self.assertEqual(["alpha"], [row["scope_key"] for row in report["scope_groups"]])
        drift = [a for a in report["anomalies"] if a["kind"] == "scope_key_drift"]
        self.assertEqual(1, len(drift))
        self.assertEqual("alpha", drift[0]["claimed_scope_key"])
        self.assertEqual("beta", drift[0]["observed_scope_key"])

    def test_equal_cross_lane_claim_time_fails_closed(self):
        report = self.report([
            ev(1950, "A-LANE", "A", scope_key="shared"),
            ev(1950, "B-LANE", "B", scope_key="shared"),
        ])
        arbitration = report["scope_groups"][0]["arbitration"]
        self.assertIsNone(arbitration["preferred_owner"])
        self.assertEqual(["A", "B"], arbitration["tied_earliest_claimants"])
        self.assertEqual([], arbitration["yield_candidates"])

    def test_scope_output_is_permutation_deterministic(self):
        rows = [
            ev(1940, "Z", "A", scope_key="shared"),
            ev(1950, "Y", "B", scope_key="shared"),
            ev(1960, "X", "C", scope_key="other"),
        ]
        expected = self.report(rows)["scope_groups"]
        for perm in itertools.permutations(rows):
            self.assertEqual(expected, self.report(list(perm))["scope_groups"])

    def test_legacy_events_do_not_gain_inferred_scope(self):
        report = self.report([
            ev(1950, "SAME", "A"),
            ev(1960, "SAME", "B"),
        ])
        self.assertEqual("COLLISION", report["lanes"][0]["status"])
        self.assertEqual([], report["scope_groups"])
        self.assertEqual(0, report["summary"]["scoped_collisions"])
        self.assertFalse(report["policy"]["scope_keys_infer_semantic_equivalence"])


if __name__ == "__main__":
    unittest.main()
