from __future__ import annotations

import copy
import inspect
import json
import unittest
from datetime import timedelta

from revenue.paid_pilot_admission.acceptance import fixture
from revenue.paid_pilot_admission.gate import AdmissionError, READY, digest, evaluate, markdown, normalize_packet, verify
from revenue.paid_pilot_admission.strict_json import StrictJSONError, loads


class GateTests(unittest.TestCase):
    def setUp(self):
        self.packet, self.now = fixture()

    def test_ready_and_verify(self):
        result = evaluate(self.packet)
        self.assertEqual(result.status, READY)
        self.assertTrue(verify(self.packet, result.receipt))
        self.assertIn("Authority ceiling", markdown(result.receipt))
        self.assertTrue(all(value is False for value in result.receipt["external_authority"].values()))

    def test_current_api_has_no_caller_clock(self):
        self.assertNotIn("now", inspect.signature(evaluate).parameters)
        with self.assertRaises(TypeError):
            evaluate(self.packet, now=self.now)

    def test_predecessor_resurrection_is_closed(self):
        packet = copy.deepcopy(self.packet)
        packet["offer"]["expires_at"] = (self.now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        self.assertIn("HOLD_OFFER_EXPIRED", evaluate(packet).reasons)
        with self.assertRaises(TypeError):
            evaluate(packet, now=self.now - timedelta(minutes=30))

    def test_order_invariant_binding(self):
        original = evaluate(self.packet).receipt
        reordered = json.loads(json.dumps(self.packet, sort_keys=True))
        other = evaluate(reordered).receipt
        for key in ("input_sha256", "offer_sha256", "scope_sha256", "acceptance_criteria_sha256"):
            self.assertEqual(original[key], other[key])

    def test_hold_variants(self):
        variants = []

        def add(name, mutate):
            packet = copy.deepcopy(self.packet)
            mutate(packet)
            variants.append((name, packet))

        add("partial", lambda p: p["funding"].__setitem__("amount_minor", 299999))
        add("over quoted price", lambda p: p["funding"].__setitem__("amount_minor", 600001))
        add("authorized", lambda p: p["funding"].__setitem__("status", "AUTHORIZED"))
        add("currency", lambda p: p["funding"].__setitem__("currency", "EUR"))
        add("funding offer", lambda p: p["funding"].__setitem__("offer_id", "x"))
        add("acceptance offer", lambda p: p["acceptance"].__setitem__("offer_id", "x"))
        add("stale", lambda p: p["funding"].__setitem__("observed_at", (self.now - timedelta(days=2)).isoformat().replace("+00:00", "Z")))
        add("future funding", lambda p: p["funding"].__setitem__("observed_at", (self.now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")))
        add("future acceptance", lambda p: p["acceptance"].__setitem__("accepted_at", (self.now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")))
        for name, packet in variants:
            with self.subTest(name=name):
                self.assertNotEqual(evaluate(packet).status, READY)

    def test_acceptance_after_funding(self):
        packet = copy.deepcopy(self.packet)
        packet["acceptance"]["accepted_at"] = (self.now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        packet["funding"]["observed_at"] = (self.now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        self.assertIn("HOLD_ACCEPTANCE_AFTER_FUNDING", evaluate(packet).reasons)

    def test_tampered_receipt_rejected(self):
        receipt = evaluate(self.packet).receipt
        for key, value in [("status", "X"), ("price_minor", 1), ("funding_evidence_sha256", "c" * 64)]:
            with self.subTest(key=key):
                packet = copy.deepcopy(receipt)
                packet[key] = value
                self.assertFalse(verify(self.packet, packet))

    def test_strict_shape_and_values(self):
        packet = copy.deepcopy(self.packet)
        packet["extra"] = 1
        with self.assertRaises(AdmissionError):
            normalize_packet(packet)
        packet = copy.deepcopy(self.packet)
        packet["funding"]["source_authority"] = "UNVERIFIED_SCREENSHOT"
        with self.assertRaises(AdmissionError):
            normalize_packet(packet)

    def test_duplicate_json_rejected(self):
        with self.assertRaises(StrictJSONError):
            loads('{"x":1,"x":2}')
        with self.assertRaises(StrictJSONError):
            loads('{"x":NaN}')

    def test_exact_offer_hash(self):
        normalized = normalize_packet(self.packet)
        self.assertEqual(normalized["derived"]["offer_sha256"], digest(normalized["offer"]))


if __name__ == "__main__":
    unittest.main()
