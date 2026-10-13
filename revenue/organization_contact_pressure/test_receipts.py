from __future__ import annotations

import inspect

from revenue.organization_contact_pressure import compiler, receipts, verifier
from .test_support import *  # noqa: F401,F403


class ReceiptsTests(GateTestCase):
    def test_supported_receipt_surfaces_have_no_caller_root_or_time_authority(self):
        forbidden = {
            "_compile_at",
            "_verify_receipt_current_at",
            "_verify_receipt_integrity_at",
        }
        for module in (gate, receipts, compiler, verifier):
            for name in forbidden:
                self.assertFalse(hasattr(module, name), f"{module.__name__}.{name} remains importable")
        self.assertEqual(
            ["compile_current", "verify_receipt_current", "verify_receipt_integrity"],
            sorted(receipts.__all__),
        )
        for function in (
            gate.compile_current,
            gate.verify_receipt_current,
            gate.verify_receipt_integrity,
            receipts.compile_current,
            receipts.verify_receipt_current,
            receipts.verify_receipt_integrity,
        ):
            parameters = inspect.signature(function).parameters
            self.assertNotIn("root", parameters)
            self.assertNotIn("now", parameters)

    def test_receipt_tamper_and_public_reseal_fail(self):
        receipt = self.fx.compile()
        tampered = dict(receipt)
        tampered["decision"] = gate.HOLD_DNR
        signed_without_sha = dict(tampered)
        signed_without_sha.pop("receipt_sha256")
        tampered["receipt_sha256"] = gate._sha256(gate._canonical_bytes(signed_without_sha))
        with self.assertRaises(gate.VerificationError):
            self.fx.verify_integrity(tampered)

    def test_ready_receipt_verifies_current(self):
        receipt = self.fx.compile()
        result = self.fx.verify_current(receipt)
        self.assertEqual(receipt, result)

    def test_ready_receipt_validity_is_capped_by_request_freshness(self):
        self.fx.policy["request_max_age_seconds"] = 30
        self.fx.policy["ready_validity_seconds"] = 120
        self.fx.write_authority()
        requested_at = self.fx.now - timedelta(seconds=20)
        receipt = self.fx.compile(self.fx.request(requested_at=requested_at))
        request_expiry = self.fx.now + timedelta(seconds=10)
        self.assertEqual(ts(request_expiry), receipt["valid_until"])
        self.assertEqual(receipt, self.fx.verify_current(receipt, now=request_expiry))
        with self.assertRaisesRegex(gate.VerificationError, "READY receipt is expired"):
            self.fx.verify_current(receipt, now=request_expiry + timedelta(seconds=1))

    def test_ready_receipt_expires(self):
        receipt = self.fx.compile()
        future = self.fx.now + timedelta(seconds=self.fx.policy["ready_validity_seconds"] + 1)
        with self.assertRaises(gate.VerificationError):
            self.fx.verify_current(receipt, now=future)

    def test_ready_receipt_invalidated_by_ledger_generation_move(self):
        receipt = self.fx.compile()
        self.fx.write_ledger([self.fx.event("p-1", gate.EVENT_PROPOSED)], updated_at=self.fx.now)
        with self.assertRaisesRegex(gate.VerificationError, "ledger generation moved"):
            self.fx.verify_current(receipt)

    def test_hold_receipt_remains_historically_verifiable_after_drift(self):
        self.fx.write_ledger([self.fx.event("dnr-1", gate.EVENT_DNR)])
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_DNR, receipt)
        self.fx.write_ledger([], updated_at=self.fx.now)
        result = self.fx.verify_current(receipt, now=self.fx.now + timedelta(days=30))
        self.assertEqual(receipt, result)
