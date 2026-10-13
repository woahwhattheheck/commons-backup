from __future__ import annotations

import unittest

from revenue.travelers_agent_toolcall_evidence.fixtures import acceptance_envelopes
from revenue.travelers_agent_toolcall_evidence.gate import compile_one


class TraceStateTest(unittest.TestCase):
    def test_dispatched_success_without_completion_is_unknown_hold(self):
        envelope = acceptance_envelopes()[0]
        envelope["trace"].update(
            {
                "dispatched_at": "2026-09-17T11:56:00-04:00",
                "observed_at": "2026-09-17T11:57:00-04:00",
                "completed_at": None,
                "outcome": "SUCCESS",
            }
        )
        receipt = compile_one(envelope)
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertIn("UNKNOWN_OUTCOME", receipt["reasons"])

    def test_dispatched_not_dispatched_label_is_still_unknown_hold(self):
        envelope = acceptance_envelopes()[0]
        envelope["trace"].update(
            {
                "dispatched_at": "2026-09-17T11:56:00-04:00",
                "observed_at": None,
                "completed_at": None,
                "outcome": "NOT_DISPATCHED",
            }
        )
        receipt = compile_one(envelope)
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertIn("UNKNOWN_OUTCOME", receipt["reasons"])

    def test_completion_without_observation_is_unsafe(self):
        envelope = acceptance_envelopes()[0]
        envelope["trace"].update(
            {
                "dispatched_at": "2026-09-17T11:56:00-04:00",
                "observed_at": None,
                "completed_at": "2026-09-17T11:58:00-04:00",
                "outcome": "SUCCESS",
            }
        )
        receipt = compile_one(envelope)
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertIn("UNSAFE_LIFECYCLE", receipt["reasons"])

    def test_observed_completed_known_outcome_can_remain_allowed(self):
        envelope = acceptance_envelopes()[0]
        envelope["trace"].update(
            {
                "dispatched_at": "2026-09-17T11:56:00-04:00",
                "observed_at": "2026-09-17T11:57:00-04:00",
                "completed_at": "2026-09-17T11:58:00-04:00",
                "outcome": "SUCCESS",
            }
        )
        receipt = compile_one(envelope)
        self.assertEqual(receipt["decision"], "EXECUTE_ALLOWED")
        self.assertEqual(receipt["reasons"], [])


if __name__ == "__main__":
    unittest.main()
