from __future__ import annotations

from .test_support import *  # noqa: F401,F403


class DecisionsTests(GateTestCase):
    def test_empty_ledger_is_ready_but_never_send_authority(self):
        receipt = self.fx.compile()
        self.assert_decision(gate.READY, receipt)
        self.assertEqual([], receipt["reasons"])
        self.assertIsNotNone(receipt["valid_until"])
        self.assertEqual(
            [
                "ATOMIC_ORGANIZATION_OUTBOUND_LEASE",
                "PER_PROSPECT_ATOMIC_LOCK",
                "COMMERCIAL_OPPORTUNITY_CUSTODY",
                "INITIAL_OUTREACH_ONE_SHOT",
                "PROVIDER_BOUND_SEND_CONSUMER",
            ],
            receipt["next_required_controls"],
        )

    def test_cross_contact_proposal_holds_organization(self):
        self.fx.write_ledger([self.fx.event("p-a", gate.EVENT_PROPOSED, route=self.fx.route_a)])
        receipt = self.fx.compile(self.fx.request(route=self.fx.route_b))
        self.assert_decision(gate.HOLD_ORG_ACTIVE, receipt)
        self.assertIn("CROSS_ROUTE_PROPOSAL_PRESSURE", receipt["reasons"])

    def test_two_proposed_routes_are_explicit_collision(self):
        self.fx.write_ledger(
            [
                self.fx.event("p-a", gate.EVENT_PROPOSED, route=self.fx.route_a),
                self.fx.event("p-b", gate.EVENT_PROPOSED, route=self.fx.route_b),
            ]
        )
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_ORG_ACTIVE, receipt)
        self.assertIn("MULTIPLE_PROPOSED_ROUTES", receipt["reasons"])

    def test_recent_sent_to_other_contact_holds(self):
        sent = self.fx.event("s-a", gate.EVENT_SENT, route=self.fx.route_a, observed_at=self.fx.now - timedelta(minutes=5))
        released = self.fx.event(
            "release-s-a",
            gate.EVENT_OWNER_RELEASE,
            route=self.fx.route_a,
            observed_at=self.fx.now - timedelta(minutes=4),
            target_event_id="s-a",
        )
        self.fx.write_ledger([released, sent])
        receipt = self.fx.compile(self.fx.request(route=self.fx.route_b))
        self.assert_decision(gate.HOLD_RECENT_CONTACT, receipt)
        self.assertTrue(any(reason.startswith("COOLDOWN_ACTIVE:") for reason in receipt["reasons"]))

    def test_unresolved_sent_holds_after_cooldown(self):
        self.fx.write_ledger(
            [self.fx.event("s-old", gate.EVENT_SENT, observed_at=self.fx.now - timedelta(hours=4))]
        )
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_ORG_ACTIVE, receipt)
        self.assertIn(f"UNRESOLVED_SENT:{self.fx.event_id('s-old')}", receipt["reasons"])

    def test_release_after_sent_allows_after_cooldown(self):
        sent = self.fx.event("s-old", gate.EVENT_SENT, observed_at=self.fx.now - timedelta(hours=4))
        release = self.fx.event(
            "release-old",
            gate.EVENT_OWNER_RELEASE,
            observed_at=self.fx.now - timedelta(hours=3),
            target_event_id="s-old",
        )
        self.fx.write_ledger([sent, release])
        self.assert_decision(gate.READY, self.fx.compile())

    def test_human_reply_requires_owner_resolution(self):
        self.fx.write_ledger(
            [self.fx.event("reply-1", gate.EVENT_HUMAN_REPLY, observed_at=self.fx.now - timedelta(hours=2))]
        )
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_HUMAN_REPLY, receipt)
        self.assertIn(f"UNRESOLVED_HUMAN_REPLY:{self.fx.event_id('reply-1')}", receipt["reasons"])

    def test_human_reply_release_still_respects_cooldown(self):
        reply = self.fx.event("reply-1", gate.EVENT_HUMAN_REPLY, observed_at=self.fx.now - timedelta(minutes=20))
        release = self.fx.event(
            "release-reply",
            gate.EVENT_OWNER_RELEASE,
            observed_at=self.fx.now - timedelta(minutes=10),
            target_event_id="reply-1",
        )
        self.fx.write_ledger([reply, release])
        self.assert_decision(gate.HOLD_RECENT_CONTACT, self.fx.compile())

    def test_auto_reply_is_not_human_reply_but_is_active(self):
        self.fx.write_ledger([self.fx.event("auto-1", gate.EVENT_AUTO_REPLY)])
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_ORG_ACTIVE, receipt)
        self.assertFalse(any("HUMAN_REPLY" in reason for reason in receipt["reasons"]))
        self.assertIn(f"UNRESOLVED_AUTO_REPLY:{self.fx.event_id('auto-1')}", receipt["reasons"])

    def test_unsubscribe_is_organization_dnr(self):
        self.fx.write_ledger([self.fx.event("u-1", gate.EVENT_UNSUBSCRIBE, route=self.fx.route_b)])
        receipt = self.fx.compile(self.fx.request(route=self.fx.route_a))
        self.assert_decision(gate.HOLD_DNR, receipt)
        self.assertIn(f"ORG_UNSUBSCRIBE:{self.fx.event_id('u-1')}", receipt["reasons"])

    def test_explicit_dnr_is_organization_wide(self):
        self.fx.write_ledger([self.fx.event("dnr-1", gate.EVENT_DNR, route=self.fx.route_b)])
        self.assert_decision(gate.HOLD_DNR, self.fx.compile())

    def test_hard_bounce_blocks_only_same_route(self):
        bounce = self.fx.event("b-1", gate.EVENT_HARD_BOUNCE, route=self.fx.route_a)
        self.fx.write_ledger([bounce])
        self.assert_decision(gate.HOLD_DNR, self.fx.compile(self.fx.request(route=self.fx.route_a)))
        self.assert_decision(gate.READY, self.fx.compile(self.fx.request(route=self.fx.route_b)))
