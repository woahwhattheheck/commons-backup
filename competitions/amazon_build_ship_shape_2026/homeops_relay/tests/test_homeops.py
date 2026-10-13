from __future__ import annotations

import copy
import unittest

from homeops_relay.homeops import HomeOpsLedger, ValidationError, _digest


class LedgerTests(unittest.TestCase):
    def make_issue(self, ledger: HomeOpsLedger, severity: str = "HIGH") -> str:
        return ledger.intake_issue(
            title="Water under sink",
            area="kitchen",
            severity=severity,
            details="Leak appears while faucet runs",
            evidence=["photo:one"],
        )["issue_id"]

    def test_deterministic_receipt_for_same_sequence(self) -> None:
        a, b = HomeOpsLedger(), HomeOpsLedger()
        ia = self.make_issue(a)
        ib = self.make_issue(b)
        self.assertEqual(ia, ib)
        a.record_quote(issue_id=ia, provider="A", amount_minor=10000, scope="Inspect", source="demo")
        b.record_quote(issue_id=ib, provider="A", amount_minor=10000, scope="Inspect", source="demo")
        self.assertEqual(a.receipt, b.receipt)
        self.assertEqual(a.snapshot(), b.snapshot())

    def test_tamper_is_detected(self) -> None:
        ledger = HomeOpsLedger()
        self.make_issue(ledger)
        events = ledger.export_events()
        events[0]["payload"]["title"] = "tampered"
        with self.assertRaisesRegex(ValidationError, "hash mismatch"):
            HomeOpsLedger.verify_events(events)

    def test_chain_reordering_is_detected(self) -> None:
        ledger = HomeOpsLedger()
        issue = self.make_issue(ledger)
        ledger.record_quote(issue_id=issue, provider="A", amount_minor=10000, scope="Inspect", source="demo")
        events = ledger.export_events()
        events.reverse()
        with self.assertRaises(ValidationError):
            HomeOpsLedger.verify_events(events)

    def test_bool_is_not_money(self) -> None:
        ledger = HomeOpsLedger()
        issue = self.make_issue(ledger)
        with self.assertRaisesRegex(ValidationError, "integer"):
            ledger.record_quote(issue_id=issue, provider="A", amount_minor=True, scope="Inspect", source="demo")

    def test_unknown_issue_rejected(self) -> None:
        ledger = HomeOpsLedger()
        with self.assertRaisesRegex(ValidationError, "unknown issue_id"):
            ledger.propose_plan(issue_id="ISS-missing")

    def test_urgent_plan_starts_with_safety(self) -> None:
        ledger = HomeOpsLedger()
        issue = self.make_issue(ledger, "URGENT")
        plan = ledger.propose_plan(issue_id=issue)
        self.assertIn("safe", plan["steps"][0].lower())
        self.assertFalse(plan["authority"]["external_effect"])

    def test_quote_comparison_is_deterministic(self) -> None:
        ledger = HomeOpsLedger()
        issue = self.make_issue(ledger)
        ledger.record_quote(issue_id=issue, provider="Expensive", amount_minor=30000, scope="B", source="demo")
        ledger.record_quote(issue_id=issue, provider="Lower", amount_minor=20000, scope="A", source="demo")
        plan = ledger.propose_plan(issue_id=issue)
        self.assertEqual([q["provider"] for q in plan["quotes"]], ["Lower", "Expensive"])
        self.assertTrue(all(q["verification"] == "CALLER_SUPPLIED_UNVERIFIED" for q in plan["quotes"]))

    def test_action_is_proposal_only(self) -> None:
        ledger = HomeOpsLedger()
        issue = self.make_issue(ledger)
        action = ledger.request_action(issue_id=issue, action_type="CONTACT_PROVIDER", target="Plumber", note="ask", max_amount_minor=10000)
        self.assertEqual(action["state"], "PENDING_OWNER_REVIEW")
        self.assertFalse(action["external_effect"])
        reviewed = ledger.record_owner_decision(action_id=action["action_id"], decision="APPROVE", evidence_note="demo Configuration specifies yes")
        self.assertEqual(reviewed["state"], "APPROVED_NOT_EXECUTED")
        self.assertFalse(reviewed["external_effect"])
        self.assertFalse(ledger.snapshot()["authority"]["provider_contact"])

    def test_action_cannot_be_reviewed_twice(self) -> None:
        ledger = HomeOpsLedger()
        issue = self.make_issue(ledger)
        action = ledger.request_action(issue_id=issue, action_type="SCHEDULE_VISIT", target="Provider")
        ledger.record_owner_decision(action_id=action["action_id"], decision="REJECT", evidence_note="not now")
        with self.assertRaisesRegex(ValidationError, "not pending"):
            ledger.record_owner_decision(action_id=action["action_id"], decision="APPROVE", evidence_note="changed")

    def test_unknown_argument_fails_closed(self) -> None:
        ledger = HomeOpsLedger()
        with self.assertRaisesRegex(ValidationError, "unknown keys"):
            ledger.call_tool("homeops.intake_issue", {"title": "x", "area": "x", "severity": "LOW", "details": "x", "execute": True})

    def test_evidence_cap(self) -> None:
        ledger = HomeOpsLedger()
        with self.assertRaisesRegex(ValidationError, "at most"):
            ledger.intake_issue(title="x", area="x", severity="LOW", details="x", evidence=["e"] * 17)

    def test_snapshot_digest_changes_with_event(self) -> None:
        ledger = HomeOpsLedger()
        before = ledger.snapshot()["snapshot_digest"]
        self.make_issue(ledger)
        self.assertNotEqual(before, ledger.snapshot()["snapshot_digest"])

    def test_replay_preserves_state_exactly(self) -> None:
        ledger = HomeOpsLedger()
        issue = self.make_issue(ledger)
        ledger.record_quote(issue_id=issue, provider="A", amount_minor=10000, scope="Inspect", source="demo")
        replayed = HomeOpsLedger.replay(copy.deepcopy(ledger.export_events()))
        self.assertEqual(ledger.snapshot(), replayed.snapshot())

    def test_invalid_event_kind_rejected_even_with_rehashed_event(self) -> None:
        ledger = HomeOpsLedger()
        self.make_issue(ledger)
        events = ledger.export_events()
        # A consumer must never silently accept a new event semantic, even
        # when an attacker recomputes a syntactically valid hash.
        events[0]["kind"] = "UNKNOWN"
        core = {key: events[0][key] for key in ("seq", "kind", "payload", "prev_hash")}
        events[0]["hash"] = _digest(core)
        with self.assertRaises(ValidationError):
            HomeOpsLedger.replay(events)


if __name__ == "__main__":
    unittest.main()
