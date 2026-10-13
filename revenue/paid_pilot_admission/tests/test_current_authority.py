from __future__ import annotations

import copy
import inspect
import unittest
from datetime import datetime, timedelta, timezone

from revenue.paid_pilot_admission import AUDIT_READY, audit_at, evaluate, evaluate_current, verify
from revenue.paid_pilot_admission.acceptance import fixture
from revenue.paid_pilot_admission.gate import READY


class CurrentAuthorityTests(unittest.TestCase):
    def test_current_api_has_no_caller_clock(self):
        packet, now = fixture()
        self.assertEqual(list(inspect.signature(evaluate_current).parameters), ["packet"])
        self.assertEqual(list(inspect.signature(evaluate).parameters), ["packet"])
        with self.assertRaises(TypeError):
            evaluate_current(packet, now=now)
        with self.assertRaises(TypeError):
            evaluate(packet, at=now)

    def test_expired_packet_cannot_be_resurrected_as_current(self):
        historical = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=3)
        packet, _ = fixture(historical)

        current = evaluate_current(packet)
        self.assertNotEqual(current.status, READY)
        self.assertIn("HOLD_OFFER_EXPIRED", current.reasons)

        audit = audit_at(packet, at=historical)
        self.assertEqual(audit.status, AUDIT_READY)
        self.assertNotEqual(audit.status, READY)
        self.assertEqual(audit.receipt["decision_status_at_time"], READY)
        self.assertEqual(audit.receipt["evaluation_kind"], "HISTORICAL_AUDIT")
        self.assertIs(audit.receipt["current_work_admission_authority"], False)
        self.assertTrue(verify(packet, audit.receipt))

    def test_audit_hold_is_also_non_authorizing(self):
        historical = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)
        packet, _ = fixture(historical)
        packet = copy.deepcopy(packet)
        packet["funding"]["amount_minor"] = packet["offer"]["admission_funding_minor"] - 1

        audit = audit_at(packet, at=historical)
        self.assertTrue(audit.status.startswith("AUDIT_HOLD_"))
        self.assertIs(audit.receipt["current_work_admission_authority"], False)
        self.assertTrue(verify(packet, audit.receipt))

    def test_audit_tamper_fails_verification(self):
        historical = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
        packet, _ = fixture(historical)
        receipt = copy.deepcopy(audit_at(packet, at=historical).receipt)
        receipt["current_work_admission_authority"] = True
        self.assertFalse(verify(packet, receipt))

    def test_current_receipts_keep_existing_integrity_contract(self):
        packet, _ = fixture()
        current = evaluate_current(packet)
        self.assertEqual(current.status, READY)
        self.assertEqual(current.receipt["evaluation_kind"], "CURRENT_AT_EVALUATION")
        self.assertIs(current.receipt["historical_only_after_evaluation"], True)
        self.assertTrue(verify(packet, current.receipt))
        self.assertEqual(evaluate(packet).status, READY)


if __name__ == "__main__":
    unittest.main()
