from __future__ import annotations

from .test_support import *  # noqa: F401,F403


class AdmissionTests(GateTestCase):
    def test_released_proposal_event_id_cannot_be_reused(self):
        proposal = self.fx.event(
            "proposal-zrt-1",
            gate.EVENT_PROPOSED,
            route=self.fx.route_a,
            observed_at=self.fx.now - timedelta(minutes=2),
        )
        release = self.fx.event(
            "release-proposal-zrt-1",
            gate.EVENT_OWNER_RELEASE,
            route=self.fx.route_a,
            observed_at=self.fx.now - timedelta(minutes=1),
            target_event_id="proposal-zrt-1",
        )
        self.fx.write_ledger([proposal, release])

        receipt = self.fx.compile(self.fx.request(route=self.fx.route_b))

        self.assert_decision(gate.HOLD_CONFLICT, receipt)
        self.assertIn(
            f"PROPOSED_EVENT_ID_ALREADY_RECORDED:{self.fx.event_id('proposal-zrt-1')}",
            receipt["reasons"],
        )

    def test_proposed_event_id_used_by_another_kind_and_route_is_conflict(self):
        existing = self.fx.event(
            "proposal-zrt-1",
            gate.EVENT_HARD_BOUNCE,
            route=self.fx.route_b,
        )
        self.fx.write_ledger([existing])

        receipt = self.fx.compile(self.fx.request(route=self.fx.route_a))

        self.assert_decision(gate.HOLD_CONFLICT, receipt)
        self.assertIn(
            f"PROPOSED_EVENT_ID_ALREADY_RECORDED:{self.fx.event_id('proposal-zrt-1')}",
            receipt["reasons"],
        )
