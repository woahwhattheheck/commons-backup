import unittest

from claim_liveness import DEFAULT_CANONICAL_ROOT, audit_events

NOW = 2_000.0
TTL = 100


def writer_claim(ts):
    return {
        "ts": ts,
        "lane": "writer-lane",
        "session": "writer",
        "event": "CLAIM",
        "event_id": "claim",
        "writes_repo": True,
        "canonical_root": DEFAULT_CANONICAL_ROOT,
    }


def rootless_followup(ts, event):
    return {
        "ts": ts,
        "lane": "writer-lane",
        "session": "writer",
        "event": event,
        "event_id": event.lower(),
        "writes_repo": False,
    }


def audit(events):
    return audit_events(events, as_of=NOW, ttl_seconds=TTL)


def lane_row(report):
    return next(row for row in report["lanes"] if row["lane"] == "writer-lane")


class WriterEpochRawOrderTests(unittest.TestCase):
    def test_rootless_heartbeat_cannot_gain_authority_from_raw_row_order(self):
        claim = writer_claim(1_800)
        heartbeat = rootless_followup(1_990, "HEARTBEAT")
        for events in ([claim, heartbeat], [heartbeat, claim]):
            with self.subTest(raw_order=[row["event"] for row in events]):
                report = audit(events)
                row = lane_row(report)
                owner = row["owners"][0]
                kinds = {anomaly["kind"] for anomaly in report["anomalies"]}
                self.assertEqual("STALE_CLAIM", row["status"])
                self.assertEqual(1_800.0, owner["last_ts"])
                self.assertIn("writer_epoch_followup_root_unbound", kinds)

    def test_rootless_terminal_cannot_gain_authority_from_raw_row_order(self):
        claim = writer_claim(1_950)
        complete = rootless_followup(1_960, "COMPLETE")
        for events in ([claim, complete], [complete, claim]):
            with self.subTest(raw_order=[row["event"] for row in events]):
                report = audit(events)
                row = lane_row(report)
                owner = row["owners"][0]
                kinds = {anomaly["kind"] for anomaly in report["anomalies"]}
                self.assertEqual("ACTIVE", row["status"])
                self.assertEqual({}, row["terminal_owners"])
                self.assertEqual(1_950.0, owner["last_ts"])
                self.assertIn("writer_epoch_followup_root_unbound", kinds)


if __name__ == "__main__":
    unittest.main()
