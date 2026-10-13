"""Executable regression tests for the owner-calendar-commit gate (WO-1).

Acceptance coverage:
  1. propose-without-approval: proposing is allowed, binding is blocked.
  2. free-but-unapproved: calendar free does not imply consent.
  3. stale approval: old approval does not cover a new time.
  4. wrong-deal approval: approval for deal A does not cover deal B.
  5. reschedule without approval: blocked.
  6. owner-approved happy path: PROPOSED -> OWNER_APPROVED -> EXTERNALLY_CONFIRMED.
"""

import os
import tempfile
import unittest

from integrations.command_center.owner_commit_gate import (
    BINDING_ACTIONS,
    EXTERNALLY_CONFIRMED,
    NON_CONSENT_SIGNALS,
    OWNER_APPROVED,
    PROPOSED,
    AmbiguousApprovalError,
    MeetingIdentity,
    OwnerApproval,
    OwnerCommitDenied,
    OwnerCommitGate,
    OwnerDirectRequest,
    consent_from_signal,
    guard_owner_commit,
)

T1_START = "2026-09-22T10:00:00-04:00"
T1_END = "2026-09-22T10:30:00-04:00"
T2_START = "2026-09-22T14:00:00-04:00"
T2_END = "2026-09-22T14:30:00-04:00"
APPROVED_AT = "2026-09-19T15:00:00-04:00"


def make_gate():
    store_path = os.path.join(tempfile.mkdtemp(), "evidence.json")
    return OwnerCommitGate(store_path=store_path), store_path


def meeting(mid="mtg-1", deal="deal-A", start=T1_START, end=T1_END):
    return MeetingIdentity(meeting_id=mid, deal_id=deal,
                           starts_at=start, ends_at=end)


def approval(mid="mtg-1", deal="deal-A", start=T1_START, end=T1_END,
             source="owner_chat_msg:msg-1", approved_at=APPROVED_AT,
             explicit=True):
    return OwnerApproval(meeting_id=mid, deal_id=deal, starts_at=start,
                         ends_at=end, source=source, approved_at=approved_at,
                         explicit=explicit)


class OwnerCommitGateTests(unittest.TestCase):

    # 1. propose-without-approval: proposing is allowed, binding is blocked.
    def test_1_propose_without_approval(self):
        gate, _ = make_gate()
        out = gate.propose(meeting())
        self.assertEqual(out["state"], PROPOSED)
        self.assertEqual(gate.state("mtg-1"), PROPOSED)
        for action in ("represent_attending", "confirm_time", "send_invite",
                       "accept_invite"):
            with self.assertRaises(OwnerCommitDenied, msg=action):
                gate.require_owner_commit("mtg-1", action)
        with self.assertRaises(OwnerCommitDenied):
            gate.external_confirm("mtg-1")

    # 2. free-but-unapproved: calendar free does not imply consent.
    def test_2_free_but_unapproved(self):
        gate, _ = make_gate()
        gate.propose(meeting())
        gate.prepare("check_freebusy")  # free/busy check itself is allowed
        self.assertFalse(consent_from_signal("calendar_free"))
        self.assertFalse(consent_from_signal("freebusy_open"))
        # Availability, silence, and prior general autonomy are never consent.
        for signal in NON_CONSENT_SIGNALS:
            self.assertFalse(consent_from_signal(signal), msg=signal)
        with self.assertRaises(OwnerCommitDenied):
            gate.require_owner_commit("mtg-1", "send_invite")
        # A purported approval sourced from a non-consent signal is rejected.
        bad = approval(source="calendar_free")
        with self.assertRaises(AmbiguousApprovalError):
            gate.record_owner_approval(bad)
        with self.assertRaises(OwnerCommitDenied):
            gate.require_owner_commit("mtg-1", "send_invite")

    # 3. stale approval: old approval does not cover a new time.
    def test_3_stale_approval(self):
        gate, _ = make_gate()
        gate.propose(meeting())
        gate.record_owner_approval(approval())
        self.assertEqual(gate.state("mtg-1"), OWNER_APPROVED)
        # A new time re-proposed without fresh approval: the old approval does
        # not carry over, binding is blocked.
        gate.propose(meeting(start=T2_START, end=T2_END))
        self.assertEqual(gate.state("mtg-1"), PROPOSED)
        with self.assertRaises(OwnerCommitDenied):
            gate.require_owner_commit("mtg-1", "confirm_time")
        with self.assertRaises(OwnerCommitDenied):
            gate.external_confirm("mtg-1")
        # Fresh approval for the NEW time unblocks the new time only.
        gate.record_owner_approval(approval(start=T2_START, end=T2_END))
        gate.require_owner_commit("mtg-1", "confirm_time")
        gate.external_confirm("mtg-1")
        self.assertEqual(gate.state("mtg-1"), EXTERNALLY_CONFIRMED)

    # 4. wrong-deal approval: approval for deal A does not cover deal B.
    def test_4_wrong_deal_approval(self):
        gate, _ = make_gate()
        gate.propose(meeting(mid="mtg-1", deal="deal-A"))
        gate.propose(meeting(mid="mtg-2", deal="deal-B"))
        gate.record_owner_approval(approval(mid="mtg-1", deal="deal-A"))
        # Deal-B meeting must not inherit deal-A approval.
        with self.assertRaises(OwnerCommitDenied):
            gate.require_owner_commit("mtg-2", "send_invite")
        with self.assertRaises(OwnerCommitDenied):
            gate.external_confirm("mtg-2")
        # Recording a mismatched approval against mtg-2 fails closed.
        with self.assertRaises(OwnerCommitDenied):
            gate.record_owner_approval(approval(mid="mtg-2", deal="deal-A"))
        self.assertEqual(gate.state("mtg-2"), PROPOSED)
        # Deal-A's own binding still works.
        gate.require_owner_commit("mtg-1", "confirm_time")

    # 5. reschedule without approval: blocked.
    def test_5_reschedule_without_approval(self):
        gate, _ = make_gate()
        gate.propose(meeting())
        gate.record_owner_approval(approval())
        with self.assertRaises(OwnerCommitDenied):
            gate.reschedule("mtg-1", meeting(start=T2_START, end=T2_END))
        # Cancel and RSVP changes are likewise blocked without fresh approval.
        with self.assertRaises(OwnerCommitDenied):
            gate.cancel("mtg-1")
        with self.assertRaises(OwnerCommitDenied):
            gate.require_owner_commit("mtg-1", "rsvp_change")
        # Still bound to the original approved time, not the new one.
        self.assertEqual(gate.state("mtg-1"), OWNER_APPROVED)
        # The only reschedule/cancel bypass: Bryce directly requesting it.
        direct = OwnerDirectRequest(action="reschedule", meeting_id="mtg-1",
                                    source="owner_chat_msg:msg-9",
                                    requested_at=APPROVED_AT)
        gate.reschedule("mtg-1", meeting(start=T2_START, end=T2_END),
                        owner_direct_request=direct)
        self.assertEqual(gate.state("mtg-1"), PROPOSED)
        # But the new time still cannot be externally confirmed without
        # explicit owner approval of the new time.
        with self.assertRaises(OwnerCommitDenied):
            gate.external_confirm("mtg-1")

    # 6. owner-approved happy path.
    def test_6_happy_path(self):
        gate, _ = make_gate()
        gate.propose(meeting(), proposed_by="agent-1")
        self.assertEqual(gate.state("mtg-1"), PROPOSED)
        gate.record_owner_approval(approval(source="owner_slack_ts:1234.5"))
        self.assertEqual(gate.state("mtg-1"), OWNER_APPROVED)
        evidence = gate.approval_evidence("mtg-1")
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.source, "owner_slack_ts:1234.5")
        self.assertEqual(evidence.approved_at, APPROVED_AT)
        gate.require_owner_commit("mtg-1", "send_invite")
        gate.require_owner_commit("mtg-1", "represent_attending")
        out = gate.external_confirm("mtg-1")
        self.assertEqual(out["state"], EXTERNALLY_CONFIRMED)

    # Evidence survives reload: a later agent cannot infer it from context.
    def test_evidence_persists_across_reloads(self):
        gate, store_path = make_gate()
        gate.propose(meeting())
        gate.record_owner_approval(approval())
        fresh = OwnerCommitGate(store_path=store_path)
        self.assertEqual(fresh.state("mtg-1"), OWNER_APPROVED)
        evidence = fresh.approval_evidence("mtg-1")
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.source, "owner_chat_msg:msg-1")
        fresh.require_owner_commit("mtg-1", "confirm_time")

    # Ambiguous approval evidence fails closed.
    def test_ambiguous_approval_fails_closed(self):
        gate, _ = make_gate()
        gate.propose(meeting())
        for bad in (
            approval(explicit=False),          # inferred consent
            approval(source=""),               # missing source
            approval(approved_at=""),          # missing timestamp
            approval(source="silence"),        # silence is not consent
        ):
            with self.assertRaises(OwnerCommitDenied):
                gate.record_owner_approval(bad)
        self.assertEqual(gate.state("mtg-1"), PROPOSED)

    def test_novel_verb_is_not_a_calendar_bind(self):
        gate, _ = make_gate()
        gate.propose(meeting())
        # A novel verb is not a calendar send: it does not bind the owner's time.
        self.assertTrue(gate.prepare("time_travel")["allowed"])
        self.assertTrue(gate.require_owner_commit("mtg-1", "time_travel")["allowed"])
        # Named calendar-bind operations still need owner commit.
        with self.assertRaises(OwnerCommitDenied):
            gate.require_owner_commit("mtg-1", "send_invite")

    # Decorator integration point: wrapped send path is gated.
    def test_guard_decorator(self):
        gate, _ = make_gate()
        gate.propose(meeting())

        @guard_owner_commit("send_invite", gate=gate)
        def send_invite(meeting_id):
            return "sent:" + meeting_id

        with self.assertRaises(OwnerCommitDenied):
            send_invite("mtg-1")
        gate.record_owner_approval(approval())
        self.assertEqual(send_invite("mtg-1"), "sent:mtg-1")

    # Every binding action is a recognized gate action.
    def test_binding_action_coverage(self):
        self.assertEqual(
            BINDING_ACTIONS,
            {"represent_attending", "confirm_time", "send_invite",
             "accept_invite", "reschedule", "cancel", "rsvp_change"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
