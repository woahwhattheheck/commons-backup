from __future__ import annotations
import unittest
from .gate import GateInputError, digest, evaluate
from .test_gate import NOW, policy, snapshot

class TestTemporalHardening(unittest.TestCase):
    def test_buyer_after_snapshot_capture_rejected(self):
        s=snapshot(); s["buyer_approval"]["approved_at"]="2026-09-13T09:32:00Z"
        self.assertRaises(GateInputError,evaluate,policy(),s,evaluated_at=NOW)
    def test_funding_after_snapshot_capture_rejected(self):
        s=snapshot(); s["funding"]["observed_at"]="2026-09-13T09:32:00Z"
        self.assertRaises(GateInputError,evaluate,policy(),s,evaluated_at=NOW)
    def test_owner_after_snapshot_capture_rejected(self):
        s=snapshot(); s["owner_approval"]["approved_at"]="2026-09-13T09:32:00Z"
        self.assertRaises(GateInputError,evaluate,policy(),s,evaluated_at=NOW)
    def test_zero_price_rejected_for_paid_pilot(self):
        s=snapshot(); s["scope"]["price_minor"]=0
        self.assertRaises(GateInputError,evaluate,policy(),s,evaluated_at=NOW)
    def test_funding_expiry_must_follow_observation(self):
        s=snapshot(); s["funding"]["expires_at"]="2026-09-13T09:19:59Z"
        self.assertRaises(GateInputError,evaluate,policy(),s,evaluated_at=NOW)
    def test_explicit_owner_rejection_holds_even_if_owner_not_required(self):
        s=snapshot(); s["scope"]["owner_approval_required"]=False; h=digest(s["scope"])
        s["buyer_approval"]["scope_sha256"]=h; s["funding"]["scope_sha256"]=h; s["intake"]["scope_sha256"]=h
        s["owner_approval"]["scope_sha256"]=h; s["owner_approval"]["decision"]="REJECT"
        r=evaluate(policy(),s,evaluated_at=NOW)
        self.assertIn("OWNER_DID_NOT_APPROVE",r["receipt"]["holds"])

if __name__ == "__main__":
    unittest.main()
