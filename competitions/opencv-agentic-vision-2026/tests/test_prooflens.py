import copy
import hashlib
import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prooflens import ALGORITHM, Policy, decide, sha256_json, validate_evidence, verify_receipt


def evidence(**overrides):
    base = {
        "algorithm": ALGORITHM,
        "source_ref": "s3://prooflens/example#baseline=v1&current=v2",
        "baseline_sha256": hashlib.sha256(b"baseline").hexdigest(),
        "current_sha256": hashlib.sha256(b"current").hexdigest(),
        "width": 640,
        "height": 480,
        "changed_fraction": 0.01,
        "edge_delta": 0.005,
        "mean_delta": 2.0,
        "quality_score": 0.90,
        "alignment_confidence": 0.80,
        "opencv_version": "5.0.0",
    }
    base.update(overrides)
    base["event_id"] = sha256_json({k: base[k] for k in sorted(base)})
    return base


class EvidenceValidationTests(unittest.TestCase):
    def test_valid_packet(self):
        packet = evidence()
        self.assertEqual(validate_evidence(packet)["event_id"], packet["event_id"])

    def test_unknown_key_rejected(self):
        packet = evidence()
        packet["authority"] = "SAFETY_CLEAR"
        with self.assertRaises(ValueError):
            validate_evidence(packet)

    def test_bool_numeric_rejected(self):
        packet = evidence(changed_fraction=True)
        with self.assertRaises(ValueError):
            validate_evidence(packet)

    def test_nonfinite_rejected(self):
        packet = evidence(mean_delta=math.inf)
        with self.assertRaises(ValueError):
            validate_evidence(packet)

    def test_opencv4_rejected_even_with_resealed_event(self):
        packet = evidence(opencv_version="4.12.0")
        with self.assertRaises(ValueError):
            validate_evidence(packet)

    def test_semantic_tamper_rejected(self):
        packet = evidence()
        packet["mean_delta"] = 80.0
        with self.assertRaisesRegex(ValueError, "event_id"):
            validate_evidence(packet)


class DecisionTests(unittest.TestCase):
    def test_no_action_below_thresholds(self):
        receipt = decide(evidence())
        self.assertEqual(receipt.decision, "NO_ACTION")
        self.assertFalse(receipt.external_action_authorized)

    def test_change_requests_human_review(self):
        receipt = decide(evidence(changed_fraction=0.20, edge_delta=0.10, mean_delta=50.0))
        self.assertEqual(receipt.decision, "REQUEST_HUMAN_REVIEW")
        self.assertIn("CHANGED_FRACTION_THRESHOLD", receipt.reason_codes)
        self.assertFalse(receipt.external_action_authorized)

    def test_low_quality_holds_even_when_change_is_large(self):
        receipt = decide(evidence(quality_score=0.10, alignment_confidence=0.05, changed_fraction=0.80, mean_delta=200.0))
        self.assertEqual(receipt.decision, "HOLD_LOW_QUALITY")
        self.assertIn("ALIGNMENT_WEAK", receipt.reason_codes)

    def test_replay_is_ignored(self):
        packet = evidence(changed_fraction=0.20)
        receipt = decide(packet, seen_event_ids={packet["event_id"]})
        self.assertEqual(receipt.decision, "REPLAY_IGNORED")
        self.assertTrue(verify_receipt(packet, receipt.to_dict(), seen_event_ids={packet["event_id"]}))
        self.assertFalse(verify_receipt(packet, receipt.to_dict()))

    def test_seen_event_id_must_be_canonical_hex(self):
        with self.assertRaises(ValueError):
            decide(evidence(), seen_event_ids={"z" * 64})

    def test_policy_changes_receipt_identity(self):
        packet = evidence(changed_fraction=0.02)
        a = decide(packet, policy=Policy(review_changed_fraction=0.01))
        b = decide(packet, policy=Policy(review_changed_fraction=0.03))
        self.assertNotEqual(a.policy_id, b.policy_id)
        self.assertNotEqual(a.receipt_sha256, b.receipt_sha256)

    def test_receipt_verifier_rejects_authority_upgrade(self):
        packet = evidence(changed_fraction=0.20)
        raw = decide(packet).to_dict()
        self.assertTrue(verify_receipt(packet, raw))
        forged = copy.deepcopy(raw)
        forged["external_action_authorized"] = True
        self.assertFalse(verify_receipt(packet, forged))

    def test_receipt_verifier_rejects_reason_tamper(self):
        packet = evidence(changed_fraction=0.20)
        raw = decide(packet).to_dict()
        raw["reason_codes"] = ["MADE_UP_REASON"]
        self.assertFalse(verify_receipt(packet, raw))

    def test_receipt_verifier_rejects_resealed_wrong_decision(self):
        packet = evidence(changed_fraction=0.20, edge_delta=0.10, mean_delta=50.0)
        forged = decide(packet).to_dict()
        forged["decision"] = "NO_ACTION"
        forged["reason_codes"] = ["BELOW_REVIEW_THRESHOLDS"]
        unsigned = {k: forged[k] for k in (
            "decision", "reason_codes", "event_id", "policy_id", "external_action_authorized"
        )}
        forged["receipt_sha256"] = sha256_json(unsigned)
        self.assertFalse(verify_receipt(packet, forged))


if __name__ == "__main__":
    unittest.main()
