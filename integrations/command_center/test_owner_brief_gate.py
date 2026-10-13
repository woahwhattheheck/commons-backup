"""Regression tests for the owner-meeting-brief gate (WO-2).

All inputs are synthetic and explicit; no network, no live sends.

Run from the worktree root:
    python -m unittest integrations.command_center.test_owner_brief_gate -v
"""
import time
import unittest
from pathlib import Path

from integrations.command_center import owner_brief_gate as obg
from integrations.command_center.owner_brief_gate import (
    DEFAULT_MIN_LEAD_SECONDS,
    STATUS_EXTERNALLY_CONFIRMED,
    STATUS_OWNER_APPROVED,
    STATUS_PROPOSED,
    URGENCY_ROUTINE,
    URGENCY_URGENT,
    VERDICT_NOT_APPLICABLE,
    VERDICT_PASS,
    VERDICT_STOP,
    DeliveryRecord,
    Meeting,
    OwnerBrief,
    OwnerBriefGate,
    RecordingSurface,
    brief_packet_template,
    packet_problems,
)

# Fixed synthetic clock: 2026-09-19 12:00:00 UTC.
T0 = 1_789_848_000.0
START = T0 + 48 * 3600          # meeting starts 48 h after T0
LEAD_OK = 2 * 3600              # brief delivered 2 h before start (real lead time)


def make_meeting(**overrides):
    fields = dict(
        meeting_id="MTG-1001",
        deal_id="DEAL-555",
        title="Acme Corp procurement review",
        counterparty_name="Dana Reyes",
        organization="Acme Corp",
        start_ts=START,
        timezone="America/New_York",
        location_or_link="https://meet.example.com/acme-1001",
        status=STATUS_EXTERNALLY_CONFIRMED,
        owner_attends=True,
        deal_version=3,
        deal_value_usd=25_000.0,
        time_sensitive=False,
    )
    fields.update(overrides)
    return Meeting(**fields)


def make_brief(meeting, **overrides):
    fields = dict(
        brief_id="OB-MTG-1001-v3",
        meeting_id=meeting.meeting_id,
        deal_id=meeting.deal_id,
        meeting_start_ts=meeting.start_ts,
        deal_version=meeting.deal_version,
        generated_ts=T0,
        generated_by="seat-orchestrator-7",
        counterparty_name="Dana Reyes",
        organization="Acme Corp",
        lead_origin="Inbound demo request from acme.example.com pricing page, 2026-09-10",
        deal_summary="Acme Corp wants a 12-month fleet-ops pilot across 4 depots.",
        deal_value_usd=25_000.0,
        deal_value_range="$20k-$30k ARR",
        value_evidence="Pricing sheet v4 + 2026-09-12 scoping call notes",
        said_promised_offered="Quoted pilot pricing; promised a 2-week onboarding plan. No discounts promised.",
        meeting_objective="Confirm pilot scope and get a signed SOW date.",
        likely_asks=("Volume discount", "On-prem data residency", "SLA terms"),
        key_questions=("Who signs the SOW?", "What is the go-live deadline?", "What kills this deal?"),
        commitments_risks_to_avoid="Do not promise custom integrations or fixed delivery dates.",
        recommended_opening="Recap the scoping call wins, then confirm the pilot depots.",
        recommended_closing="Propose the SOW review date and name the follow-up owner.",
        source_links=("https://crm.example.com/deals/DEAL-555", "https://notes.example.com/scoping-2026-09-12"),
        scheduled_time_line="2026-09-21 12:00 UTC (America/New_York) -- https://meet.example.com/acme-1001",
        followup_owner="seat-orchestrator-7",
        delivered_ts=START - LEAD_OK,
        delivery_channel="owner-brief-drop",
    )
    fields.update(overrides)
    return OwnerBrief(**fields)


class OwnerBriefGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = OwnerBriefGate()

    # -- acceptance 1: confirmed + no brief = STOP -------------------------
    def test_confirmed_meeting_without_brief_is_stop(self):
        meeting = make_meeting()
        decision = self.gate.evaluate(meeting, None, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertTrue(decision.is_blocked)
        self.assertIn("no owner brief exists", decision.reasons[0])
        self.assertTrue(decision.confirmed)

    # -- acceptance 2: stale brief fails ------------------------------------
    def test_stale_brief_old_start_time_is_stop(self):
        meeting = make_meeting(start_ts=START + 3600)  # rescheduled 1 h later
        brief = make_brief(make_meeting())            # brief bound to old start
        decision = self.gate.evaluate(meeting, brief, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("stale brief", decision.reasons[0])
        self.assertIn("rescheduled", decision.reasons[0])

    def test_stale_brief_old_deal_version_is_stop(self):
        meeting = make_meeting(deal_version=4)
        brief = make_brief(make_meeting())  # brief bound to version 3
        decision = self.gate.evaluate(meeting, brief, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("stale brief", decision.reasons[0])
        self.assertIn("deal version", decision.reasons[0])

    # -- acceptance 3: wrong-deal brief fails --------------------------------
    def test_wrong_meeting_brief_is_stop(self):
        meeting = make_meeting()
        brief = make_brief(meeting, meeting_id="MTG-9999", brief_id="OB-MTG-9999-v3")
        decision = self.gate.evaluate(meeting, brief, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("wrong-deal brief", decision.reasons[0])

    def test_wrong_deal_id_brief_is_stop(self):
        meeting = make_meeting()
        brief = make_brief(meeting, deal_id="DEAL-OTHER")
        decision = self.gate.evaluate(meeting, brief, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("wrong-deal brief", decision.reasons[0])

    # -- acceptance 4: fresh complete brief + lead time = PASS ---------------
    def test_fresh_complete_brief_with_lead_time_passes(self):
        meeting = make_meeting()
        brief = make_brief(meeting)
        # Evaluate after delivery (brief in Bryce's hands) but before the start.
        decision = self.gate.evaluate(meeting, brief, now=START - LEAD_OK)
        self.assertEqual(decision.verdict, VERDICT_PASS)
        self.assertFalse(decision.is_blocked)
        self.assertEqual(decision.brief_id, "OB-MTG-1001-v3")

    def test_packet_problems_names_every_missing_field(self):
        meeting = make_meeting()
        brief = make_brief(
            meeting,
            key_questions=(),
            commitments_risks_to_avoid="  ",
            deal_value_usd=None,
            deal_value_range="",
        )
        problems = packet_problems(brief)
        self.assertIn("missing/empty key_questions", problems)
        self.assertIn("missing/blank commitments_risks_to_avoid", problems)
        self.assertTrue(any("deal value" in p for p in problems))
        decision = self.gate.evaluate(meeting, brief, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("brief packet incomplete", decision.reasons[0])

    def test_value_range_alone_satisfies_value_rule(self):
        meeting = make_meeting()
        brief = make_brief(meeting, deal_value_usd=None, deal_value_range="$20k-$30k ARR")
        self.assertEqual(packet_problems(brief), [])
        decision = self.gate.evaluate(meeting, brief, now=START - LEAD_OK)
        self.assertEqual(decision.verdict, VERDICT_PASS)

    # -- lead-time rules -----------------------------------------------------
    def test_brief_generated_after_meeting_start_is_stop(self):
        meeting = make_meeting()
        brief = make_brief(meeting, generated_ts=START + 60, delivered_ts=START + 120)
        decision = self.gate.evaluate(meeting, brief, now=START + 300)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("generated after the meeting starts", decision.reasons[0])

    def test_brief_generated_exactly_at_start_is_stop(self):
        meeting = make_meeting()
        brief = make_brief(meeting, generated_ts=START, delivered_ts=START + 60)
        decision = self.gate.evaluate(meeting, brief, now=START + 300)
        self.assertEqual(decision.verdict, VERDICT_STOP)

    def test_undelivered_brief_is_stop(self):
        meeting = make_meeting()
        brief = make_brief(meeting, delivered_ts=None)
        decision = self.gate.evaluate(meeting, brief, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("never delivered", decision.reasons[0])

    def test_delivery_without_enough_lead_time_is_stop(self):
        meeting = make_meeting()
        brief = make_brief(meeting, delivered_ts=START - 5 * 60)  # 5 min before
        # Evaluate right at delivery: brief exists but Bryce has no real lead time.
        decision = self.gate.evaluate(meeting, brief, now=START - 5 * 60)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("lead time", decision.reasons[0])

    def test_future_delivery_timestamp_is_stop(self):
        meeting = make_meeting()
        brief = make_brief(meeting, delivered_ts=T0 + 600)  # "delivered" in the future
        decision = self.gate.evaluate(meeting, brief, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("in the future", decision.reasons[0])

    def test_generated_after_delivered_is_stop(self):
        meeting = make_meeting()
        brief = make_brief(meeting, generated_ts=START - 3600,
                           delivered_ts=START - 7200)
        decision = self.gate.evaluate(meeting, brief, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("inconsistent timestamps", decision.reasons[0])

    def test_min_lead_time_is_configurable(self):
        meeting = make_meeting()
        brief = make_brief(meeting, delivered_ts=START - 3600)  # 1 h lead
        strict = OwnerBriefGate(min_lead_seconds=2 * 3600)
        self.assertEqual(
            self.gate.evaluate(meeting, brief, now=START - 3600).verdict, VERDICT_PASS)
        decision = strict.evaluate(meeting, brief, now=START - 3600)
        self.assertEqual(decision.verdict, VERDICT_STOP)
        self.assertIn("lead time", decision.reasons[0])

    def test_default_min_lead_is_30_minutes(self):
        self.assertEqual(DEFAULT_MIN_LEAD_SECONDS, 30 * 60)

    # -- gate scope: only confirmed, owner-attended meetings ------------------
    def test_proposed_meeting_is_not_applicable(self):
        meeting = make_meeting(status=STATUS_PROPOSED)
        decision = self.gate.evaluate(meeting, None, now=T0)
        self.assertEqual(decision.verdict, VERDICT_NOT_APPLICABLE)
        self.assertFalse(decision.is_blocked)
        self.assertFalse(decision.confirmed)

    def test_owner_approved_but_not_confirmed_is_not_applicable(self):
        meeting = make_meeting(status=STATUS_OWNER_APPROVED)
        decision = self.gate.evaluate(meeting, None, now=T0)
        self.assertEqual(decision.verdict, VERDICT_NOT_APPLICABLE)
        self.assertFalse(decision.confirmed)

    def test_meeting_owner_does_not_attend_is_not_applicable(self):
        meeting = make_meeting(owner_attends=False)
        decision = self.gate.evaluate(meeting, None, now=T0)
        self.assertEqual(decision.verdict, VERDICT_NOT_APPLICABLE)
        self.assertFalse(decision.is_blocked)


class UrgentPathTests(unittest.TestCase):
    def setUp(self):
        self.gate = OwnerBriefGate()

    def test_high_value_meeting_is_urgent(self):
        meeting = make_meeting(deal_value_usd=50_000.0)
        self.assertEqual(self.gate.classify_urgency(meeting, T0), URGENCY_URGENT)

    def test_time_sensitive_meeting_is_urgent(self):
        meeting = make_meeting(deal_value_usd=100.0, time_sensitive=True)
        self.assertEqual(self.gate.classify_urgency(meeting, T0), URGENCY_URGENT)

    def test_imminent_meeting_is_urgent(self):
        meeting = make_meeting(deal_value_usd=100.0, start_ts=T0 + 2 * 3600)
        self.assertEqual(self.gate.classify_urgency(meeting, T0), URGENCY_URGENT)

    def test_routine_meeting_is_routine(self):
        meeting = make_meeting(deal_value_usd=500.0, time_sensitive=False,
                               start_ts=T0 + 48 * 3600)
        self.assertEqual(self.gate.classify_urgency(meeting, T0), URGENCY_ROUTINE)

    # -- acceptance 5: urgent path records evidence, never sends --------------
    def test_urgent_path_records_delivery_evidence_without_live_send(self):
        meeting = make_meeting(deal_value_usd=50_000.0)
        brief = make_brief(meeting)
        slack = RecordingSurface("slack-dm")
        email = RecordingSurface("email")
        receipts = self.gate.record_urgent_delivery_obligations(
            meeting, brief, (slack, email), now=T0)
        self.assertEqual(len(receipts), 2)
        self.assertEqual({r.surface_channel for r in receipts}, {"slack-dm", "email"})
        for receipt in receipts:
            self.assertFalse(receipt.live_send_performed)
            self.assertFalse(receipt.record.live_send_performed)
            self.assertEqual(receipt.record.status, "recorded-obligation")
            self.assertEqual(receipt.record.urgency, URGENCY_URGENT)
            self.assertEqual(receipt.record.meeting_id, "MTG-1001")
            self.assertEqual(receipt.record.brief_id, "OB-MTG-1001-v3")
            self.assertEqual(receipt.record.attempted_ts, T0)
            self.assertIn("no message", receipt.record.note.lower())
        # The surfaces hold the records as evidence; nothing was dispatched.
        self.assertEqual(len(slack.log), 1)
        self.assertEqual(len(email.log), 1)
        self.assertIsInstance(slack.log[0], DeliveryRecord)

    def test_urgent_path_with_missing_brief_still_records_obligation(self):
        meeting = make_meeting(deal_value_usd=50_000.0)
        surface = RecordingSurface("slack-dm")
        receipts = self.gate.record_urgent_delivery_obligations(
            meeting, None, (surface,), now=T0)
        self.assertEqual(len(receipts), 1)
        self.assertIsNone(receipts[0].record.brief_id)
        self.assertIn("no brief exists yet", receipts[0].record.note)
        self.assertFalse(receipts[0].live_send_performed)

    def test_routine_meeting_records_no_obligations(self):
        meeting = make_meeting(deal_value_usd=500.0, start_ts=T0 + 48 * 3600)
        surface = RecordingSurface("slack-dm")
        receipts = self.gate.record_urgent_delivery_obligations(
            meeting, make_brief(meeting), (surface,), now=T0)
        self.assertEqual(receipts, ())
        self.assertEqual(surface.log, [])

    def test_process_returns_decision_and_urgent_receipts(self):
        meeting = make_meeting(deal_value_usd=50_000.0)
        brief = make_brief(meeting)
        surface = RecordingSurface("slack-dm")
        decision, receipts = self.gate.process(
            meeting, brief, (surface,), now=START - LEAD_OK)
        self.assertEqual(decision.verdict, VERDICT_PASS)
        self.assertEqual(decision.urgency, URGENCY_URGENT)
        self.assertEqual(len(receipts), 1)
        self.assertFalse(receipts[0].live_send_performed)

    def test_process_routine_pass_has_no_receipts(self):
        # A routine meeting evaluated well outside the urgent window: the gate
        # passes and no urgent obligations are recorded.
        far_start = T0 + 7 * 24 * 3600
        meeting = make_meeting(deal_value_usd=500.0, start_ts=far_start)
        brief = make_brief(meeting, meeting_start_ts=far_start,
                           delivered_ts=far_start - 5 * 3600)
        surface = RecordingSurface("slack-dm")
        decision, receipts = self.gate.process(
            meeting, brief, (surface,), now=far_start - 5 * 3600)
        self.assertEqual(decision.verdict, VERDICT_PASS)
        self.assertEqual(decision.urgency, URGENCY_ROUTINE)
        self.assertEqual(receipts, ())

    def test_module_contains_no_network_io_primitives(self):
        source = Path(__file__).with_name("owner_brief_gate.py").read_text()
        lowered = source.lower()
        for token in ("socket", "smtplib", "requests", "urllib",
                      "http.client", "subprocess", "sendmail"):
            self.assertNotIn(token, lowered,
                             "owner_brief_gate.py must not reference %r" % token)


class CommitGateCompositionTests(unittest.TestCase):
    """WO-1 owns the commit state machine; this gate only consumes its signal."""

    class FakeCommitGate:
        def __init__(self, confirmed, state):
            self._confirmed = confirmed
            self._state = state
            self.seen = []

        def externally_confirmed(self, meeting_id):
            self.seen.append(meeting_id)
            return self._confirmed

        def commit_state(self, meeting_id):
            return self._state

    def setUp(self):
        self.gate = OwnerBriefGate()

    def test_wo1_signal_confirms_through_interface_not_local_label(self):
        meeting = make_meeting(status=STATUS_PROPOSED)  # local label says proposed
        adapter = self.FakeCommitGate(True, STATUS_EXTERNALLY_CONFIRMED)
        decision = self.gate.evaluate(meeting, None, now=T0, commit_gate=adapter)
        self.assertEqual(adapter.seen, ["MTG-1001"])
        self.assertTrue(decision.confirmed)
        self.assertEqual(decision.confirmed_via, "wo1-commit-gate")
        # WO-1 says confirmed, so the brief gate applies: no brief => STOP.
        self.assertEqual(decision.verdict, VERDICT_STOP)

    def test_wo1_denial_overrides_local_confirmed_label(self):
        meeting = make_meeting(status=STATUS_EXTERNALLY_CONFIRMED)
        adapter = self.FakeCommitGate(False, STATUS_OWNER_APPROVED)
        decision = self.gate.evaluate(meeting, None, now=T0, commit_gate=adapter)
        self.assertFalse(decision.confirmed)
        self.assertEqual(decision.confirmed_via, "wo1-commit-gate")
        self.assertEqual(decision.verdict, VERDICT_NOT_APPLICABLE)

    def test_without_adapter_local_status_label_is_used(self):
        meeting = make_meeting()
        decision = self.gate.evaluate(meeting, None, now=T0)
        self.assertEqual(decision.confirmed_via, "meeting-status-label")
        self.assertTrue(decision.confirmed)
        self.assertEqual(decision.verdict, VERDICT_STOP)


class BriefTemplateTests(unittest.TestCase):
    def test_template_prefills_binding_and_lists_missing_content(self):
        meeting = make_meeting()
        template = brief_packet_template(meeting, "seat-orchestrator-7", now=T0)
        self.assertEqual(template.meeting_id, "MTG-1001")
        self.assertEqual(template.deal_id, "DEAL-555")
        self.assertEqual(template.meeting_start_ts, START)
        self.assertEqual(template.deal_version, 3)
        self.assertEqual(template.generated_ts, T0)
        self.assertEqual(template.counterparty_name, "Dana Reyes")
        self.assertEqual(template.organization, "Acme Corp")
        self.assertIn("America/New_York", template.scheduled_time_line)
        problems = packet_problems(template)
        self.assertTrue(problems)  # content fields still blank by design
        self.assertIn("missing/blank lead_origin", problems)
        decision = OwnerBriefGate().evaluate(meeting, template, now=T0)
        self.assertEqual(decision.verdict, VERDICT_STOP)


if __name__ == "__main__":
    unittest.main()
