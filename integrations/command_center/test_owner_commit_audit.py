"""Tests for owner_commit_audit: never-invent-consent classification.

Run: python3 -m unittest integrations.command_center.test_owner_commit_audit -v
from the repo root.
"""
import unittest

from integrations.command_center.owner_commit_audit import (
    ALL_STATES,
    EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL,
    NEEDS_OWNER_ACTION,
    OWNER_APPROVED,
    PROPOSED_NOT_CONFIRMED,
    ApprovalEvidence,
    Commitment,
    ExternalConfirmation,
    Proposal,
    audit,
    classify,
    looks_like_mistaken_consent,
    owner_decision_for,
)


def base_commitment(**kw):
    args = dict(commitment_id="deal-1",
                kind="meeting",
                summary="Acme demo",
                counterpart="Acme Corp",
                event_time="2026-09-22T14:00:00-04:00")
    args.update(kw)
    return Commitment(**args)


class TestCoreClassification(unittest.TestCase):
    def test_binding_owner_approval_approves(self):
        c = base_commitment(approval_evidence=[
            ApprovalEvidence(source="Bryce", at="2026-09-19T15:00:00-04:00",
                             commitment_id="deal-1",
                             event_time="2026-09-22T14:00:00-04:00",
                             text="Yes, set the Acme demo for Monday 2pm")])
        r = classify(c)
        self.assertEqual(r.state, OWNER_APPROVED)
        self.assertIsNotNone(r.approving_evidence)
        self.assertEqual(r.approving_evidence.source, "Bryce")

    def test_externally_confirmed_without_approval_never_defaults_approved(self):
        # The central invariant: external confirmation is not owner consent.
        c = base_commitment(external_confirmation=[
            ExternalConfirmation(kind="counterpart_confirmed",
                                 detail="Acme replied 'see you Monday'"),
            ExternalConfirmation(kind="seat_confirmed_to_external",
                                 detail="seat Z told Acme the time is set"),
        ])
        r = classify(c)
        self.assertEqual(r.state, EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL)
        self.assertNotEqual(r.state, OWNER_APPROVED)
        self.assertIsNone(r.approving_evidence)

    def test_proposal_only_is_not_confirmed(self):
        c = base_commitment(proposals=[Proposal(detail="seat offered Monday 2pm")])
        r = classify(c)
        self.assertEqual(r.state, PROPOSED_NOT_CONFIRMED)
        self.assertNotEqual(r.state, OWNER_APPROVED)
        self.assertNotEqual(r.state, EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL)

    def test_bare_item_needs_owner_action(self):
        r = classify(base_commitment())
        self.assertEqual(r.state, NEEDS_OWNER_ACTION)

    def test_approval_beats_external_confirmation(self):
        # Both signals present and the owner really approved -> approved.
        c = base_commitment(
            approval_evidence=[ApprovalEvidence(
                source="bryce", at="2026-09-19T15:00:00-04:00",
                commitment_id="deal-1")],
            external_confirmation=[ExternalConfirmation(
                kind="counterpart_confirmed", detail="Acme confirmed")])
        r = classify(c)
        self.assertEqual(r.state, OWNER_APPROVED)


class TestNeverInventConsent(unittest.TestCase):
    def test_agent_claimed_approval_is_nothing(self):
        # "he said yes" from a seat is not owner approval.
        c = base_commitment(approval_evidence=[
            ApprovalEvidence(source="seat-Zeta", at="2026-09-19T15:00:00-04:00",
                             commitment_id="deal-1",
                             text="Configuration specifies yes (per seat)")])
        r = classify(c)
        self.assertEqual(r.state, NEEDS_OWNER_ACTION)
        self.assertIsNone(r.approving_evidence)

    def test_wrong_deal_evidence_does_not_approve(self):
        # Approval for a different commitment id approves nothing here.
        c = base_commitment(
            commitment_id="deal-1",
            approval_evidence=[ApprovalEvidence(
                source="bryce", at="2026-09-19T15:00:00-04:00",
                commitment_id="deal-2",  # wrong deal
                text="yes to the deal-2 call")],
            external_confirmation=[ExternalConfirmation(
                kind="counterpart_confirmed", detail="Acme confirmed deal-1")])
        r = classify(c)
        self.assertEqual(r.state, EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL)
        self.assertIsNone(r.approving_evidence)

    def test_stale_time_evidence_does_not_approve(self):
        # Owner approved Monday 2pm; the meeting then moved to Tuesday 2pm.
        # The old approval is stale and approves nothing.
        c = base_commitment(
            event_time="2026-09-23T14:00:00-04:00",  # moved
            approval_evidence=[ApprovalEvidence(
                source="bryce", at="2026-09-19T15:00:00-04:00",
                commitment_id="deal-1",
                event_time="2026-09-22T14:00:00-04:00",  # old time
                text="yes to Monday 2pm")],
            external_confirmation=[ExternalConfirmation(
                kind="counterpart_confirmed", detail="Acme confirmed Tuesday")])
        r = classify(c)
        self.assertEqual(r.state, EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL)
        self.assertIsNone(r.approving_evidence)

    def test_stale_time_with_no_external_still_needs_owner(self):
        c = base_commitment(
            event_time="2026-09-23T14:00:00-04:00",
            approval_evidence=[ApprovalEvidence(
                source="bryce", at="2026-09-19T15:00:00-04:00",
                commitment_id="deal-1",
                event_time="2026-09-22T14:00:00-04:00")])
        r = classify(c)
        self.assertEqual(r.state, NEEDS_OWNER_ACTION)

    def test_custom_owner_identity_honored(self):
        c = base_commitment(approval_evidence=[
            ApprovalEvidence(source="FleetRoot", at="2026-09-19T15:00:00-04:00",
                             commitment_id="deal-1", text="approved")])
        r = classify(c, owner_identities=frozenset({"fleetroot"}))
        self.assertEqual(r.state, OWNER_APPROVED)


class TestFailClosed(unittest.TestCase):
    def test_ambiguous_evidence_fails_closed(self):
        c = base_commitment(
            external_confirmation=[ExternalConfirmation(
                kind="counterpart_confirmed", detail="Acme said Monday")],
            ambiguity=["seat claims approval but no owner text on record",
                       "two different times mentioned (Mon 2pm vs Tue 10am)"])
        r = classify(c)
        self.assertEqual(r.state, NEEDS_OWNER_ACTION)
        self.assertIsNone(r.approving_evidence)

    def test_ambiguity_beats_even_real_looking_approval(self):
        # When evidence conflicts, we do not guess: fail closed.
        c = base_commitment(
            approval_evidence=[ApprovalEvidence(
                source="bryce", at="2026-09-19T15:00:00-04:00",
                commitment_id="deal-1", text="yes")],
            ambiguity=["approval text may belong to a different thread"])
        r = classify(c)
        self.assertEqual(r.state, NEEDS_OWNER_ACTION)

    def test_ambiguity_without_any_signal_still_closed(self):
        c = base_commitment(ambiguity=["unclear whether owner was expected"])
        r = classify(c)
        self.assertEqual(r.state, NEEDS_OWNER_ACTION)


class TestExhaustive(unittest.TestCase):
    def test_every_kind_classifies_exactly_once(self):
        for kind in ("meeting", "call", "demo", "interview",
                     "customer_commitment", "rsvp"):
            r = classify(base_commitment(kind=kind))
            self.assertIn(r.state, ALL_STATES)
            self.assertEqual(len([s for s in ALL_STATES if s == r.state]), 1)

    def test_invalid_kind_rejected(self):
        with self.assertRaises(ValueError):
            classify(base_commitment(kind="birthday_party"))

    def test_audit_partitions_all_items(self):
        items = [
            base_commitment(commitment_id="a", approval_evidence=[
                ApprovalEvidence(source="bryce", at="t", commitment_id="a")]),
            base_commitment(commitment_id="b", proposals=[Proposal("offered")]),
            base_commitment(commitment_id="c", external_confirmation=[
                ExternalConfirmation(kind="counterpart_confirmed")]),
            base_commitment(commitment_id="d",
                            ambiguity=["conflicting times"]),
        ]
        results, by_state = audit(items)
        self.assertEqual(len(results), 4)
        self.assertEqual(
            {s: [c.commitment_id for c, _ in by_state[s]] for s in ALL_STATES},
            {OWNER_APPROVED: ["a"],
             PROPOSED_NOT_CONFIRMED: ["b"],
             EXTERNALLY_CONFIRMED_WITHOUT_OWNER_APPROVAL: ["c"],
             NEEDS_OWNER_ACTION: ["d"]})


class TestDecisionPacket(unittest.TestCase):
    def test_approved_needs_no_decision(self):
        c = base_commitment(approval_evidence=[
            ApprovalEvidence(source="bryce", at="t", commitment_id="deal-1")])
        self.assertEqual(owner_decision_for(c, classify(c)), "")

    def test_external_confirmation_gets_approve_or_cancel(self):
        c = base_commitment(external_confirmation=[
            ExternalConfirmation(kind="counterpart_confirmed", detail="x")])
        d = owner_decision_for(c, classify(c))
        self.assertIn("APPROVE or CANCEL", d)
        self.assertIn("without your approval", d)

    def test_proposal_gets_approve_or_decline(self):
        c = base_commitment(proposals=[Proposal("offered Mon 2pm")])
        d = owner_decision_for(c, classify(c))
        self.assertIn("APPROVE or DECLINE", d)

    def test_needs_action_gets_decide(self):
        c = base_commitment()
        d = owner_decision_for(c, classify(c))
        self.assertIn("DECIDE", d)


class TestMistakenConsentSignals(unittest.TestCase):
    def test_flags_agent_assumption_language(self):
        for text in ("Bryce is good with it", "he said yes, probably fine",
                     "no objection from him", "thumbs up on the thread"):
            self.assertTrue(looks_like_mistaken_consent(text), text)

    def test_does_not_flag_explicit_approval_text(self):
        self.assertFalse(looks_like_mistaken_consent(
            "Bryce: approved, set the Acme demo for Monday 2pm"))


if __name__ == "__main__":
    unittest.main()
