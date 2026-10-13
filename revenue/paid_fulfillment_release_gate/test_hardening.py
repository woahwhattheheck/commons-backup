from test_gate import base_payload, gate, ts
import unittest


class ReleaseGateHardeningTests(unittest.TestCase):
    def test_subsecond_staleness_does_not_round_down(self):
        payload = base_payload()
        payload["snapshot_at"] = "2026-09-13T08:02:00.900000Z"
        payload["freshness_window_seconds"] = 10
        payload["sources"]["ORDER_SYSTEM"]["observed_at"] = "2026-09-13T08:01:50Z"
        receipt = gate.evaluate(payload)
        self.assertEqual("HOLD", receipt["decision"])
        self.assertIn("SOURCE_STALE:ORDER_SYSTEM", receipt["reasons"])
        self.assertEqual(10.9, receipt["sources"]["ORDER_SYSTEM"]["age_seconds"])

    def test_non_rfc3339_space_timestamp_is_rejected(self):
        payload = base_payload()
        payload["snapshot_at"] = "2026-09-13 08:02:00+00:00"
        with self.assertRaisesRegex(gate.GateInputError, "RFC3339"):
            gate.evaluate(payload)

    def test_release_before_full_payment_is_exception(self):
        payload = base_payload()
        payload["events"][0]["occurred_at"] = ts(40)
        payload["events"].append({
            "event_id": "evt-release",
            "kind": "FULFILLMENT_RELEASED",
            "source": "FULFILLMENT_SYSTEM",
            "order_id": "order-001",
            "occurred_at": ts(30),
            "release_id": "release-001",
        })
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("RELEASE_WITHOUT_FULL_PAYMENT", receipt["reasons"])

    def test_release_before_ready_state_is_exception(self):
        payload = base_payload()
        payload["events"][1]["occurred_at"] = ts(40)
        payload["events"].append({
            "event_id": "evt-release",
            "kind": "FULFILLMENT_RELEASED",
            "source": "FULFILLMENT_SYSTEM",
            "order_id": "order-001",
            "occurred_at": ts(30),
            "release_id": "release-001",
        })
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("RELEASE_WITHOUT_READY_STATE", receipt["reasons"])


if __name__ == "__main__":
    unittest.main()
