# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from integration_contract import ContractError, Message, evaluate_trace


def trace():
    return [
        Message("m1", "case-001", "BEAKER_TO_IMS", "CASE_ORDER", {"accession_token": "syn-001", "specimen_type": "synthetic"}),
        Message("m2", "case-001", "IMS_TO_BEAKER", "IMAGE_READY", {"image_ref": "sha256:" + "1"*64}),
        Message("m3", "case-001", "IMS_TO_BEAKER", "AI_RESULT", {"model": "synthetic-model", "result_ref": "sha256:" + "2"*64}),
        Message("m4", "case-002", "BEAKER_TO_IMS", "CASE_ORDER", {"accession_token": "syn-002"}),
        Message("m5", "case-002", "IMS_TO_BEAKER", "CASE_STATUS", {"status": "SYNTHETIC_COMPLETE"}),
    ]


class IntegrationContractTests(unittest.TestCase):
    def test_bidirectional_trace_passes(self):
        r = evaluate_trace(trace())
        self.assertEqual(r["decision"], "PASS")
        self.assertFalse(r["contains_phi"])
        self.assertIn("NO_CLINICAL_INTEROPERABILITY_CLAIM", r["authority"])

    def test_exact_replay_collapses(self):
        t = trace(); t.append(t[0])
        r = evaluate_trace(t)
        self.assertEqual(r["decision"], "PASS")
        self.assertEqual(r["exact_replays_collapsed"], 1)
        self.assertEqual(r["message_count"], 5)

    def test_conflicting_message_id_rejected(self):
        t = trace(); t.append(Message("m1", "case-001", "BEAKER_TO_IMS", "CASE_ORDER", {"accession_token": "different"}))
        with self.assertRaisesRegex(ContractError, "reused"):
            evaluate_trace(t)

    def test_missing_reverse_direction_holds(self):
        r = evaluate_trace([trace()[0]])
        self.assertEqual(r["decision"], "HOLD")
        self.assertEqual(r["broken_bidirectional_correlations"], ["case-001"])

    def test_reverse_without_order_holds_incomplete(self):
        r = evaluate_trace([Message("x", "case-x", "IMS_TO_BEAKER", "IMAGE_READY", {"image_ref": "synthetic"}), Message("y", "case-x", "BEAKER_TO_IMS", "CASE_STATUS", {"status": "ack"})])
        self.assertEqual(r["decision"], "HOLD")
        self.assertEqual(r["incomplete_correlations"], ["case-x"])

    def test_direct_identifier_forbidden(self):
        t = trace(); t[0] = Message("m1", "case-001", "BEAKER_TO_IMS", "CASE_ORDER", {"mrn": "123"})
        with self.assertRaisesRegex(ContractError, "direct patient identifiers"):
            evaluate_trace(t)

    def test_invalid_direction_rejected(self):
        with self.assertRaisesRegex(ContractError, "invalid direction"):
            evaluate_trace([Message("m", "c", "SIDEWAYS", "CASE_ORDER", {})])

    def test_invalid_kind_rejected(self):
        with self.assertRaisesRegex(ContractError, "invalid kind"):
            evaluate_trace([Message("m", "c", "BEAKER_TO_IMS", "DIAGNOSIS", {})])

    def test_empty_trace_rejected(self):
        with self.assertRaisesRegex(ContractError, "must not be empty"):
            evaluate_trace([])

    def test_receipt_is_order_stable_only_for_same_sequence(self):
        a = evaluate_trace(trace())
        b = evaluate_trace(copy.deepcopy(trace()))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
