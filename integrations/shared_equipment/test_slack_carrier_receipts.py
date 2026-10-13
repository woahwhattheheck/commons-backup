import json
import tempfile
import unittest
from pathlib import Path

from integrations.shared_equipment.slack_carrier import (
    RECEIPT_CLOSE,
    RECEIPT_OPEN,
    SlackEquipmentCarrier,
)


class _Journal:
    def __init__(self):
        self.rows = {}

    def execute_journaled(self, request_id, call_id, name, arguments, runner):
        key = (request_id, call_id)
        encoded = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        prior = self.rows.get(key)
        if prior is not None:
            if prior["arguments"] != encoded:
                return {"isError": True, "error": "call_id_reused_with_different_arguments"}
            return prior["result"]
        result = runner(name, arguments)
        self.rows[key] = {"arguments": encoded, "result": result}
        return result


class _Services:
    def __init__(self):
        self.sent = []

    def _slack_write_route_verified(self, _channel_id=None):
        return True

    def call(self, name, arguments):
        if name != "slack_post_message":
            raise AssertionError("unexpected service call: " + name)
        self.sent.append(arguments)
        return {"result": {"ok": True, "ts": f"4.{len(self.sent)}"}}


class _Catalog:
    def __init__(self, result):
        self.services = _Services()
        self.result = result
        self.effects = 0

    def call(self, name, arguments):
        self.effects += 1
        self.last_call = (name, arguments)
        return self.result


def _receipt_payloads(sent):
    receipts = []
    for message in sent:
        text = message["text"]
        if not text.startswith(RECEIPT_OPEN):
            continue
        if not text.endswith(RECEIPT_CLOSE):
            raise AssertionError("receipt envelope is incomplete")
        receipts.append(json.loads(text[len(RECEIPT_OPEN):-len(RECEIPT_CLOSE)]))
    return receipts


class ExternalDemoCarrierReceiptTests(unittest.TestCase):
    def _process(self, result, *, request_id="receipt-request-1", call_id="post-1",
                 operation_id="receipt-operation-1", text="PRIVATE DEMO BODY"):
        catalog = _Catalog(result)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        calls = _Journal()
        carrier = SlackEquipmentCarrier(
            catalog,
            calls,
            {"channel_id": "C0BU51F1PL3"},
            Path(temp.name) / "cursor.json",
        )
        message = {
            "ts": "1791260000.123456",
            "text": (
                '<commons_equipment_request>'
                + json.dumps({
                    "request_id": request_id,
                    "call_id": call_id,
                    "name": "slack_post_external_demo_message",
                    "arguments": {"operation_id": operation_id, "text": text},
                })
                + '</commons_equipment_request>'
            ),
        }
        carrier.process(message)
        return carrier, catalog, message

    def test_delivered_receipts_are_payload_free_and_replay_safe(self):
        result = {
            "isError": False,
            "uncertain": False,
            "result": {
                "ok": True,
                "state": "DELIVERED",
                "delivered": True,
                "receipt": {
                    "operation_id": "receipt-operation-1",
                    "payload_sha256": "abc123",
                    "channel_id": "C0C7S2D5QRE",
                    "message_ts": "1791260001.654321",
                    "message_permalink": "https://example.invalid/message",
                    "sender_verified": True,
                    "body_verified": True,
                },
            },
        }
        carrier, catalog, message = self._process(result)
        receipts = _receipt_payloads(catalog.services.sent)
        self.assertEqual([row["state"] for row in receipts], ["ACCEPTED", "DELIVERED"])
        self.assertEqual(receipts[1]["channel_id"], "C0C7S2D5QRE")
        self.assertEqual(receipts[1]["message_ts"], "1791260001.654321")
        self.assertNotIn("PRIVATE DEMO BODY", json.dumps(receipts))
        self.assertEqual(catalog.effects, 1)

        carrier.process(message)
        self.assertEqual(catalog.effects, 1)
        self.assertEqual(len(catalog.services.sent), 3)

    def test_duplicate_receipt_returns_only_original_safe_receipt_fields(self):
        result = {
            "isError": False,
            "uncertain": False,
            "result": {
                "ok": True,
                "state": "DELIVERED",
                "delivered": True,
                "replayed": True,
                "receipt": {
                    "operation_id": "receipt-operation-1",
                    "payload_sha256": "abc123",
                    "channel_id": "C0C7S2D5QRE",
                    "message_ts": "1791260001.654321",
                    "message_permalink": "https://example.invalid/message",
                    "sender_user_id": "U0C17K9ALP7",
                    "sender_verified": True,
                    "body_verified": True,
                    "provider_footer_present": False,
                    "readback_state": "confirmed",
                    "text": "MUST NOT LEAK",
                },
            },
        }
        _carrier, catalog, _message = self._process(result)
        receipts = _receipt_payloads(catalog.services.sent)
        self.assertEqual([row["state"] for row in receipts], ["ACCEPTED", "DUPLICATE"])
        original = receipts[1]["original_receipt"]
        self.assertEqual(original["channel_id"], "C0C7S2D5QRE")
        self.assertEqual(original["message_ts"], "1791260001.654321")
        self.assertNotIn("text", original)
        self.assertNotIn("MUST NOT LEAK", json.dumps(receipts))

    def test_failed_receipt_exposes_stable_code_not_provider_message(self):
        result = {
            "isError": True,
            "uncertain": True,
            "result": {
                "ok": False,
                "state": "RECONCILE_REQUIRED",
                "message": "provider detail MUST NOT LEAK",
            },
        }
        _carrier, catalog, _message = self._process(result)
        receipts = _receipt_payloads(catalog.services.sent)
        self.assertEqual([row["state"] for row in receipts], ["ACCEPTED", "FAILED"])
        self.assertEqual(receipts[1]["code"], "RECONCILE_REQUIRED")
        self.assertTrue(receipts[1]["uncertain"])
        self.assertNotIn("MUST NOT LEAK", json.dumps(receipts))


if __name__ == "__main__":
    unittest.main()
