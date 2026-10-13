from __future__ import annotations

from .test_support import *  # noqa: F401,F403


class ConflictsTests(GateTestCase):
    def test_exact_duplicate_event_is_idempotent(self):
        event = self.fx.event("p-1", gate.EVENT_PROPOSED)
        duplicate_document = self.fx.write_ledger([event, dict(event)], generation=1)
        duplicate_receipt = self.fx.compile()
        single_document = self.fx.write_ledger([event], generation=1)
        single_receipt = self.fx.compile()
        self.assertEqual(single_document, duplicate_document)
        self.assertEqual(single_receipt, duplicate_receipt)
        self.assert_decision(gate.HOLD_ORG_ACTIVE, duplicate_receipt)
        self.assertFalse(any(reason.startswith("EVENT_ID_MUTATION") for reason in duplicate_receipt["reasons"]))


    def test_same_event_id_changed_content_is_conflict(self):
        first = self.fx.event("p-1", gate.EVENT_PROPOSED, route=self.fx.route_a)
        changed = self.fx.event("p-1", gate.EVENT_PROPOSED, route=self.fx.route_b)
        self.fx.write_ledger([first, changed], generation=1)
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_CONFLICT, receipt)
        self.assertIn(f"EVENT_ID_MUTATION:{self.fx.event_id('p-1')}", receipt["reasons"])


    def test_generation_count_mismatch_is_conflict(self):
        self.fx.write_ledger([self.fx.event("p-1", gate.EVENT_PROPOSED)], generation=9)
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_CONFLICT, receipt)
        self.assertIn("LEDGER_GENERATION_COUNT_MISMATCH", receipt["reasons"])


    def test_release_missing_target_is_conflict(self):
        release = self.fx.event(
            "release-x",
            gate.EVENT_OWNER_RELEASE,
            target_event_id="does-not-exist",
        )
        self.fx.write_ledger([release])
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_CONFLICT, receipt)
        self.assertIn(f"RELEASE_TARGET_MISSING:{self.fx.event_id('release-x')}", receipt["reasons"])


    def test_release_on_different_route_is_conflict(self):
        target = self.fx.event("p-1", gate.EVENT_PROPOSED, route=self.fx.route_a)
        release = self.fx.event(
            "release-1",
            gate.EVENT_OWNER_RELEASE,
            route=self.fx.route_b,
            observed_at=self.fx.now - timedelta(minutes=1),
            target_event_id="p-1",
        )
        self.fx.write_ledger([target, release])
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_CONFLICT, receipt)
        self.assertIn(
            f"RELEASE_ROUTE_MISMATCH:{self.fx.event_id('release-1')}",
            receipt["reasons"],
        )


    def test_release_before_target_is_conflict(self):
        target = self.fx.event("p-1", gate.EVENT_PROPOSED, observed_at=self.fx.now - timedelta(minutes=5))
        release = self.fx.event(
            "release-1",
            gate.EVENT_OWNER_RELEASE,
            observed_at=self.fx.now - timedelta(minutes=6),
            target_event_id="p-1",
        )
        self.fx.write_ledger([target, release])
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_CONFLICT, receipt)
        self.assertIn(f"RELEASE_NOT_LATER_THAN_TARGET:{self.fx.event_id('release-1')}", receipt["reasons"])


    def test_unknown_route_in_signed_ledger_holds_authority(self):
        self.fx.write_ledger([self.fx.event("p-x", gate.EVENT_PROPOSED, route=self.fx.route_c)])
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIn(f"UNKNOWN_ROUTE_SCOPE:{self.fx.event_id('p-x')}", receipt["reasons"])


    def test_cross_organization_event_holds_authority(self):
        self.fx.write_ledger(
            [self.fx.event("p-x", gate.EVENT_PROPOSED, organization=digest("attacker-org"))]
        )
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIn(f"EVENT_ORGANIZATION_TRANSPLANT:{self.fx.event_id('p-x')}", receipt["reasons"])


    def test_future_event_holds_authority(self):
        self.fx.write_ledger(
            [self.fx.event("p-future", gate.EVENT_PROPOSED, observed_at=self.fx.now + timedelta(seconds=6))],
            updated_at=self.fx.now + timedelta(seconds=5),
        )
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIn(f"FUTURE_EVENT:{self.fx.event_id('p-future')}", receipt["reasons"])


    def test_unknown_request_route_holds_authority(self):
        receipt = self.fx.compile(self.fx.request(route=self.fx.route_c))
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIn("REQUEST_ROUTE_NOT_AUTHORIZED", receipt["reasons"])


    def test_stale_request_holds_authority(self):
        receipt = self.fx.compile(
            self.fx.request(requested_at=self.fx.now - timedelta(seconds=self.fx.policy["request_max_age_seconds"] + 1))
        )
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIn("REQUEST_STALE", receipt["reasons"])


    def test_forged_authority_attacker_key_holds(self):
        self.fx.write_authority(key=bytes.fromhex("99" * 32))
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIsNone(receipt["authority_sha256"])
        verified = gate._verify_receipt_integrity_at(self.fx.receipt_bytes(receipt), root=self.root)
        self.assertEqual(receipt, verified)


    def test_future_issued_authority_holds(self):
        self.fx.authority_issued_at = self.fx.now + timedelta(seconds=6)
        self.fx.write_authority()
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)


    def test_expired_authority_holds(self):
        self.fx.write_authority(valid_until=ts(self.fx.now - timedelta(seconds=1)))
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)


    def test_forged_ledger_attacker_key_holds(self):
        self.fx.write_ledger([], key=bytes.fromhex("99" * 32))
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIsNone(receipt["authority_sha256"])
        self.assertIsNone(receipt["ledger_sha256"])
        verified = gate._verify_receipt_integrity_at(self.fx.receipt_bytes(receipt), root=self.root)
        self.assertEqual(receipt, verified)


    def test_input_order_determinism(self):
        events = [
            self.fx.event("sent-a", gate.EVENT_SENT, observed_at=self.fx.now - timedelta(hours=2)),
            self.fx.event(
                "release-a",
                gate.EVENT_OWNER_RELEASE,
                observed_at=self.fx.now - timedelta(hours=1, minutes=50),
                target_event_id="sent-a",
            ),
            self.fx.event("bounce-b", gate.EVENT_HARD_BOUNCE, route=self.fx.route_b),
        ]
        first_document = self.fx.write_ledger(events)
        first_receipt = self.fx.compile(self.fx.request(route=self.fx.route_a))
        second_document = self.fx.write_ledger(list(reversed(events)))
        second_receipt = self.fx.compile(self.fx.request(route=self.fx.route_a))
        self.assertEqual(first_document, second_document)
        self.assertEqual(first_receipt, second_receipt)
