from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).with_name("gate.py")
spec = importlib.util.spec_from_file_location("paid_fulfillment_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)

BASE_TIME = datetime(2026, 9, 13, 8, 0, 0, tzinfo=timezone.utc)
TEST_EVALUATED_AT = BASE_TIME + timedelta(seconds=180)
_ORIGINAL_EVALUATE = gate.evaluate


def _deterministic_evaluate(payload: dict) -> dict:
    return _ORIGINAL_EVALUATE(payload, evaluated_at=TEST_EVALUATED_AT)


# Existing decision tests must not depend on the wall clock. Production callers
# omit evaluated_at and therefore use trusted current UTC time by default.
gate.evaluate = _deterministic_evaluate


def ts(seconds: int) -> str:
    return (BASE_TIME + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def base_payload() -> dict:
    return {
        "schema_version": 1,
        "decision_id": "decision-001",
        "snapshot_at": ts(120),
        "freshness_window_seconds": 300,
        "order": {
            "order_id": "order-001",
            "currency": "AUD",
            "required_amount_minor": 150000,
        },
        "sources": {
            "PAYMENT_PROVIDER": {"complete": True, "observed_at": ts(110)},
            "OPERATIONS_SYSTEM": {"complete": True, "observed_at": ts(110)},
            "ORDER_SYSTEM": {"complete": True, "observed_at": ts(110)},
            "FULFILLMENT_SYSTEM": {"complete": True, "observed_at": ts(110)},
        },
        "events": [
            {
                "event_id": "evt-pay",
                "kind": "PAYMENT_CAPTURED",
                "source": "PAYMENT_PROVIDER",
                "order_id": "order-001",
                "occurred_at": ts(10),
                "payment_id": "pay-001",
                "amount_minor": 150000,
                "currency": "AUD",
            },
            {
                "event_id": "evt-ready",
                "kind": "FULFILLMENT_READY",
                "source": "OPERATIONS_SYSTEM",
                "order_id": "order-001",
                "occurred_at": ts(20),
            },
        ],
    }


class ReleaseGateTests(unittest.TestCase):
    def test_happy_path_releases(self):
        receipt = gate.evaluate(base_payload())
        self.assertEqual("RELEASE", receipt["decision"])
        self.assertTrue(receipt["release_authorized"])
        self.assertEqual(150000, receipt["money"]["net_paid_amount_minor"])
        self.assertEqual(ts(180).replace("Z", ".000000Z"), receipt["evaluated_at"])
        self.assertEqual(300, receipt["authorization"]["ttl_seconds"])
        # Source evidence was observed at t=110 with a 300s freshness window,
        # so it expires at t=410 before the snapshot max-TTL boundary at t=420.
        self.assertEqual(ts(410).replace("Z", ".000000Z"), receipt["authorization"]["expires_at"])
        self.assertFalse(receipt["authorization"]["expired"])

    def test_old_internally_fresh_snapshot_cannot_replay_release(self):
        payload = base_payload()
        receipt = _ORIGINAL_EVALUATE(
            payload,
            evaluated_at=BASE_TIME + timedelta(days=1),
        )
        self.assertEqual("HOLD", receipt["decision"])
        self.assertFalse(receipt["release_authorized"])
        self.assertIn("SNAPSHOT_EXPIRED", receipt["reasons"])
        self.assertTrue(receipt["authorization"]["expired"])
        self.assertGreater(receipt["authorization"]["snapshot_age_seconds"], 80_000)

    def test_default_evaluation_uses_trusted_wall_clock(self):
        trusted_now = BASE_TIME + timedelta(days=2)
        with mock.patch.object(gate, "_utcnow", return_value=trusted_now):
            receipt = _ORIGINAL_EVALUATE(base_payload())
        self.assertEqual("HOLD", receipt["decision"])
        self.assertIn("SNAPSHOT_EXPIRED", receipt["reasons"])
        self.assertEqual(
            trusted_now.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            receipt["evaluated_at"],
        )

    def test_source_freshness_is_checked_at_evaluation_time(self):
        payload = base_payload()
        payload["freshness_window_seconds"] = 60
        receipt = _ORIGINAL_EVALUATE(
            payload,
            evaluated_at=BASE_TIME + timedelta(seconds=180),
        )
        self.assertEqual("HOLD", receipt["decision"])
        self.assertFalse(receipt["release_authorized"])
        self.assertIn("SOURCE_STALE:PAYMENT_PROVIDER", receipt["reasons"])
        self.assertEqual(10.0, receipt["sources"]["PAYMENT_PROVIDER"]["age_seconds"])
        self.assertEqual(
            70.0,
            receipt["sources"]["PAYMENT_PROVIDER"]["evaluation_age_seconds"],
        )

    def test_receipt_expiry_is_capped_by_source_freshness(self):
        payload = base_payload()
        payload["freshness_window_seconds"] = 100
        receipt = _ORIGINAL_EVALUATE(
            payload,
            evaluated_at=BASE_TIME + timedelta(seconds=180),
        )
        self.assertEqual("RELEASE", receipt["decision"])
        self.assertEqual(
            ts(210).replace("Z", ".000000Z"),
            receipt["authorization"]["expires_at"],
        )
        self.assertTrue(
            gate.verify_release_receipt(
                receipt,
                consumed_at=BASE_TIME + timedelta(seconds=209),
            )
        )
        with self.assertRaisesRegex(gate.GateInputError, "has expired"):
            gate.verify_release_receipt(
                receipt,
                consumed_at=BASE_TIME + timedelta(seconds=210),
            )

    def test_future_snapshot_is_rejected_against_trusted_time(self):
        with self.assertRaisesRegex(
            gate.GateInputError, "after trusted evaluation time"
        ):
            _ORIGINAL_EVALUATE(
                base_payload(),
                evaluated_at=BASE_TIME + timedelta(seconds=119),
            )

    def test_release_receipt_consumer_enforces_expiry_boundary(self):
        receipt = _ORIGINAL_EVALUATE(
            base_payload(),
            evaluated_at=BASE_TIME + timedelta(seconds=180),
        )
        self.assertTrue(
            gate.verify_release_receipt(
                receipt,
                consumed_at=BASE_TIME + timedelta(seconds=409),
            )
        )
        with self.assertRaisesRegex(gate.GateInputError, "has expired"):
            gate.verify_release_receipt(
                receipt,
                consumed_at=BASE_TIME + timedelta(seconds=410),
            )

    def test_release_receipt_consumer_rejects_tampering(self):
        receipt = _ORIGINAL_EVALUATE(
            base_payload(),
            evaluated_at=BASE_TIME + timedelta(seconds=180),
        )
        receipt["authorization"]["expires_at"] = ts(999)
        with self.assertRaisesRegex(gate.GateInputError, "does not match"):
            gate.verify_release_receipt(
                receipt,
                consumed_at=BASE_TIME + timedelta(seconds=181),
            )

    def test_non_release_receipt_cannot_be_consumed_as_release(self):
        payload = base_payload()
        payload["events"][0]["amount_minor"] = 149999
        receipt = _ORIGINAL_EVALUATE(
            payload,
            evaluated_at=BASE_TIME + timedelta(seconds=180),
        )
        with self.assertRaisesRegex(gate.GateInputError, "does not authorize"):
            gate.verify_release_receipt(
                receipt,
                consumed_at=BASE_TIME + timedelta(seconds=181),
            )

    def test_exact_event_replay_is_deduplicated(self):
        payload = base_payload()
        payload["events"].append(copy.deepcopy(payload["events"][0]))
        receipt = gate.evaluate(payload)
        self.assertEqual("RELEASE", receipt["decision"])
        self.assertEqual(1, receipt["events"]["deduplicated_count"])
        self.assertEqual(150000, receipt["money"]["captured_amount_minor"])

    def test_conflicting_event_id_is_rejected(self):
        payload = base_payload()
        duplicate = copy.deepcopy(payload["events"][0])
        duplicate["amount_minor"] = 149999
        payload["events"].append(duplicate)
        with self.assertRaisesRegex(gate.GateInputError, "event_id reused"):
            gate.evaluate(payload)

    def test_same_payment_id_cannot_change_amount(self):
        payload = base_payload()
        second = copy.deepcopy(payload["events"][0])
        second["event_id"] = "evt-pay-conflict"
        second["amount_minor"] = 1
        payload["events"].append(second)
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("PAYMENT_ID_CONFLICT:pay-001", receipt["reasons"])

    def test_partial_payment_holds(self):
        payload = base_payload()
        payload["events"][0]["amount_minor"] = 149999
        receipt = gate.evaluate(payload)
        self.assertEqual("HOLD", receipt["decision"])
        self.assertIn("PAYMENT_INSUFFICIENT", receipt["reasons"])

    def test_multiple_payments_can_satisfy_total(self):
        payload = base_payload()
        payload["events"][0]["amount_minor"] = 100000
        second = copy.deepcopy(payload["events"][0])
        second.update(
            event_id="evt-pay-2",
            payment_id="pay-002",
            amount_minor=50000,
            occurred_at=ts(11),
        )
        payload["events"].append(second)
        receipt = gate.evaluate(payload)
        self.assertEqual("RELEASE", receipt["decision"])
        self.assertEqual(["pay-001", "pay-002"], receipt["money"]["payment_ids"])

    def test_wrong_currency_is_exception(self):
        payload = base_payload()
        payload["events"][0]["currency"] = "USD"
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("PAYMENT_CURRENCY_MISMATCH:evt-pay", receipt["reasons"])

    def test_refund_is_explicit_exception(self):
        payload = base_payload()
        payload["events"].append(
            {
                "event_id": "evt-refund",
                "kind": "PAYMENT_REFUNDED",
                "source": "PAYMENT_PROVIDER",
                "order_id": "order-001",
                "occurred_at": ts(30),
                "payment_id": "pay-001",
                "refund_id": "refund-001",
                "amount_minor": 1,
                "currency": "AUD",
            }
        )
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("REFUND_PRESENT", receipt["reasons"])
        self.assertEqual(149999, receipt["money"]["net_paid_amount_minor"])

    def test_refund_without_capture_is_exception(self):
        payload = base_payload()
        payload["events"] = [
            payload["events"][1],
            {
                "event_id": "evt-refund",
                "kind": "PAYMENT_REFUNDED",
                "source": "PAYMENT_PROVIDER",
                "order_id": "order-001",
                "occurred_at": ts(30),
                "payment_id": "missing-payment",
                "refund_id": "refund-001",
                "amount_minor": 10,
                "currency": "AUD",
            },
        ]
        receipt = gate.evaluate(payload)
        self.assertIn("REFUND_WITHOUT_CAPTURE:refund-001", receipt["reasons"])

    def test_chargeback_is_explicit_exception(self):
        payload = base_payload()
        payload["events"].append(
            {
                "event_id": "evt-cb",
                "kind": "PAYMENT_CHARGEBACK",
                "source": "PAYMENT_PROVIDER",
                "order_id": "order-001",
                "occurred_at": ts(40),
                "payment_id": "pay-001",
                "chargeback_id": "cb-001",
            }
        )
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("CHARGEBACK_PRESENT", receipt["reasons"])

    def test_cancel_is_explicit_exception(self):
        payload = base_payload()
        payload["events"].append(
            {
                "event_id": "evt-cancel",
                "kind": "ORDER_CANCELLED",
                "source": "ORDER_SYSTEM",
                "order_id": "order-001",
                "occurred_at": ts(40),
                "cancellation_id": "cancel-001",
            }
        )
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("ORDER_CANCELLED", receipt["reasons"])

    def test_not_ready_holds(self):
        payload = base_payload()
        payload["events"].append(
            {
                "event_id": "evt-not-ready",
                "kind": "FULFILLMENT_NOT_READY",
                "source": "OPERATIONS_SYSTEM",
                "order_id": "order-001",
                "occurred_at": ts(50),
            }
        )
        receipt = gate.evaluate(payload)
        self.assertEqual("HOLD", receipt["decision"])
        self.assertIn("FULFILLMENT_NOT_READY", receipt["reasons"])

    def test_conflicting_readiness_at_same_time_is_exception(self):
        payload = base_payload()
        payload["events"].append(
            {
                "event_id": "evt-not-ready",
                "kind": "FULFILLMENT_NOT_READY",
                "source": "OPERATIONS_SYSTEM",
                "order_id": "order-001",
                "occurred_at": ts(20),
            }
        )
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("READINESS_CONFLICT_AT_SAME_TIME", receipt["reasons"])

    def test_incomplete_source_holds(self):
        payload = base_payload()
        payload["sources"]["FULFILLMENT_SYSTEM"]["complete"] = False
        receipt = gate.evaluate(payload)
        self.assertEqual("HOLD", receipt["decision"])
        self.assertIn("SOURCE_INCOMPLETE:FULFILLMENT_SYSTEM", receipt["reasons"])

    def test_stale_source_holds(self):
        payload = base_payload()
        payload["freshness_window_seconds"] = 10
        payload["sources"]["ORDER_SYSTEM"]["observed_at"] = ts(100)
        receipt = gate.evaluate(payload)
        self.assertEqual("HOLD", receipt["decision"])
        self.assertIn("SOURCE_STALE:ORDER_SYSTEM", receipt["reasons"])

    def test_event_newer_than_source_snapshot_is_rejected(self):
        payload = base_payload()
        payload["sources"]["PAYMENT_PROVIDER"]["observed_at"] = ts(5)
        with self.assertRaisesRegex(
            gate.GateInputError, "newer than its source snapshot"
        ):
            gate.evaluate(payload)

    def test_existing_release_is_idempotent(self):
        payload = base_payload()
        payload["events"].append(
            {
                "event_id": "evt-release",
                "kind": "FULFILLMENT_RELEASED",
                "source": "FULFILLMENT_SYSTEM",
                "order_id": "order-001",
                "occurred_at": ts(30),
                "release_id": "release-001",
            }
        )
        receipt = gate.evaluate(payload)
        self.assertEqual("ALREADY_RELEASED", receipt["decision"])
        self.assertFalse(receipt["release_authorized"])
        self.assertEqual(
            ["release-001"], receipt["release_history"]["release_ids"]
        )

    def test_second_distinct_release_is_exception(self):
        payload = base_payload()
        for suffix, when in (("001", 30), ("002", 31)):
            payload["events"].append(
                {
                    "event_id": f"evt-release-{suffix}",
                    "kind": "FULFILLMENT_RELEASED",
                    "source": "FULFILLMENT_SYSTEM",
                    "order_id": "order-001",
                    "occurred_at": ts(when),
                    "release_id": f"release-{suffix}",
                }
            )
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("MULTIPLE_RELEASE_IDS", receipt["reasons"])

    def test_post_release_readiness_reversal_is_exception(self):
        payload = base_payload()
        payload["events"].extend(
            [
                {
                    "event_id": "evt-release",
                    "kind": "FULFILLMENT_RELEASED",
                    "source": "FULFILLMENT_SYSTEM",
                    "order_id": "order-001",
                    "occurred_at": ts(30),
                    "release_id": "release-001",
                },
                {
                    "event_id": "evt-not-ready",
                    "kind": "FULFILLMENT_NOT_READY",
                    "source": "OPERATIONS_SYSTEM",
                    "order_id": "order-001",
                    "occurred_at": ts(40),
                },
            ]
        )
        receipt = gate.evaluate(payload)
        self.assertEqual("EXCEPTION", receipt["decision"])
        self.assertIn("POST_RELEASE_REVERSAL", receipt["reasons"])

    def test_out_of_order_input_has_identical_receipt(self):
        a = base_payload()
        b = base_payload()
        b["events"] = list(reversed(b["events"]))
        self.assertEqual(gate.evaluate(a), gate.evaluate(b))

    def test_receipt_is_byte_deterministic(self):
        a = gate.evaluate(base_payload())
        b = gate.evaluate(copy.deepcopy(base_payload()))
        self.assertEqual(a["receipt_sha256"], b["receipt_sha256"])
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_boolean_amount_is_rejected(self):
        payload = base_payload()
        payload["events"][0]["amount_minor"] = True
        with self.assertRaisesRegex(gate.GateInputError, "amount_minor"):
            gate.evaluate(payload)

    def test_cross_order_event_is_rejected(self):
        payload = base_payload()
        payload["events"][0]["order_id"] = "other-order"
        with self.assertRaisesRegex(gate.GateInputError, "does not match"):
            gate.evaluate(payload)

    def test_wrong_source_for_event_kind_is_rejected(self):
        payload = base_payload()
        payload["events"][0]["source"] = "ORDER_SYSTEM"
        with self.assertRaisesRegex(
            gate.GateInputError, "must be PAYMENT_PROVIDER"
        ):
            gate.evaluate(payload)

    def test_json_duplicate_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(
                '{"schema_version":1,"schema_version":1}', encoding="utf-8"
            )
            with self.assertRaisesRegex(
                gate.GateInputError, "duplicate JSON object key"
            ):
                gate.load_json(path)

    def test_atomic_output_refuses_input_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(base_payload()), encoding="utf-8")
            with self.assertRaisesRegex(gate.GateInputError, "different files"):
                gate._write_atomic(path, gate.evaluate(base_payload()), path)

    def test_atomic_output_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            output_path = Path(tmp) / "receipt.json"
            input_path.write_text(json.dumps(base_payload()), encoding="utf-8")
            receipt = gate.evaluate(base_payload())
            gate._write_atomic(output_path, receipt, input_path)
            self.assertEqual(
                receipt,
                json.loads(output_path.read_text(encoding="utf-8")),
            )


if __name__ == "__main__":
    unittest.main()
