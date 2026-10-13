from copy import deepcopy
import unittest

from revenue.opportunity_portfolio_intake.intake import IntakeError, compile_intake
from revenue.opportunity_portfolio_intake.test_intake import TRUSTED, event, packet, trusted_authority


class PreservedRegressionTests(unittest.TestCase):
    def compile(self, events=None, **kwargs):
        payload = packet(events, **kwargs)
        return compile_intake(
            payload,
            trusted_as_of=TRUSTED,
            trusted_snapshot_authority=trusted_authority(payload),
        )

    @staticmethod
    def item(receipt):
        return receipt["portfolioInput"]["opportunities"][0]

    def blockers(self, receipt):
        return {b["code"]: b["status"] for b in self.item(receipt)["blockers"]}

    def test_generic_event_cannot_resolve_reserved_dnr(self):
        with self.assertRaisesRegex(IntakeError, "reserved blocker DNR"):
            self.compile([event("e1", "BLOCKER_RESOLVED", "2026-09-14T00:55:00Z", code="DNR")])

    def test_generic_blocker_open_then_resolved(self):
        receipt = self.compile([
            event("e1", "BLOCKER_OPEN", "2026-09-14T00:45:00Z", code="NEEDS-SCOPE"),
            event("e2", "BLOCKER_RESOLVED", "2026-09-14T00:55:00Z", code="NEEDS-SCOPE"),
        ])
        self.assertEqual(self.blockers(receipt)["NEEDS-SCOPE"], "RESOLVED")

    def test_same_timestamp_blocker_open_resolve_fails_closed(self):
        receipt = self.compile([
            event("a-resolve", "BLOCKER_RESOLVED", "2026-09-14T00:50:00Z", code="NEEDS-SCOPE"),
            event("z-open", "BLOCKER_OPEN", "2026-09-14T00:50:00Z", code="NEEDS-SCOPE"),
        ])
        self.assertEqual(self.blockers(receipt)["STATUS-HISTORY-CONFLICT"], "OPEN")

    def test_same_timestamp_dnr_reopen_fails_closed(self):
        receipt = self.compile([
            event("a-reopen", "BUYER_REOPEN", "2026-09-14T00:50:00Z", origin="BUYER"),
            event("z-dnr", "DNR", "2026-09-14T00:50:00Z", origin="BUYER"),
        ])
        self.assertEqual(self.blockers(receipt)["STATUS-HISTORY-CONFLICT"], "OPEN")

    def test_unknown_blocker_resolution_marks_history_conflict(self):
        receipt = self.compile([event("e1", "BLOCKER_RESOLVED", "2026-09-14T00:55:00Z", code="NEEDS-SCOPE")])
        self.assertEqual(self.blockers(receipt)["STATUS-HISTORY-CONFLICT"], "OPEN")

    def test_duplicate_opportunity_id_is_rejected(self):
        payload = packet()
        payload["opportunities"].append(deepcopy(payload["opportunities"][0]))
        with self.assertRaisesRegex(IntakeError, "duplicate id"):
            compile_intake(payload, trusted_as_of=TRUSTED)

    def test_facts_are_not_rewritten_by_status_events(self):
        payload = packet([event("e1", "DNR", "2026-09-14T00:55:00Z", origin="BUYER")])
        original = deepcopy(payload["opportunities"][0]["facts"])
        receipt = compile_intake(
            payload,
            trusted_as_of=TRUSTED,
            trusted_snapshot_authority=trusted_authority(payload),
        )
        item = self.item(receipt)
        for key in ("source", "freshUntil", "deadline", "eligibility", "value", "capacity", "dependsOn"):
            self.assertEqual(item[key], original[key])


if __name__ == "__main__":
    unittest.main(verbosity=2)
