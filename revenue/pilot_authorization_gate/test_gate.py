from __future__ import annotations
import copy, unittest
from .gate import GateInputError, HOLD, PROPOSAL_READY, READY, digest, evaluate, verify

NOW="2026-09-13T10:00:00Z"

def policy():
    return {"schema":"paid-pilot-authorization-policy/v1","accepted_funding_states":{"INVOICE":["PAID"],"ESCROW":["FUNDED"],"PO":["APPROVED"]},"max_proposal_age_seconds":86400,"owner_approval_default_required":False}

def scope():
    return {"schema":"paid-pilot-scope/v1","scope_id":"hyperagent-pilot","version":"v1","deliverables":["event-normalizer","slack-receipts"],"exclusions":["production-credentials","unbounded-support"],"acceptance":["30-event-fixture","zero-duplicate-replay"],"required_inputs":["backend-list","workspace-sandbox"],"price_minor":250000,"currency":"USD","owner_approval_required":True,"prepared_at":"2026-09-13T09:00:00Z","expires_at":"2026-09-14T09:00:00Z"}

def snapshot(*, buyer=True, funding=True, intake=True, owner=True):
    s=scope(); h=digest(s)
    return {"schema":"paid-pilot-authorization-snapshot/v1","capture_complete":True,"scope":s,
      "buyer_approval":({"buyer_id":"buyer-1","decision":"YES","scope_sha256":h,"approved_at":"2026-09-13T09:10:00Z"} if buyer else None),
      "funding":({"funding_id":"fund-1","funding_type":"INVOICE","state":"PAID","scope_sha256":h,"amount_minor":250000,"currency":"USD","observed_at":"2026-09-13T09:20:00Z","expires_at":None} if funding else None),
      "intake":({"scope_sha256":h,"received_inputs":["backend-list","workspace-sandbox"]} if intake else None),
      "owner_approval":({"owner_id":"bryce","decision":"APPROVE","scope_sha256":h,"approved_at":"2026-09-13T09:30:00Z"} if owner else None),
      "captured_at":"2026-09-13T09:31:00Z"}

class TestGate(unittest.TestCase):
    def test_ready(self):
        s=snapshot(); r=evaluate(policy(),s,evaluated_at=NOW); self.assertEqual(READY,r["receipt"]["decision"]); self.assertTrue(verify(r,policy=policy(),snapshot=s))
    def test_missing_buyer_is_proposal_ready(self):
        self.assertEqual(PROPOSAL_READY,evaluate(policy(),snapshot(buyer=False),evaluated_at=NOW)["receipt"]["decision"])
    def test_missing_funding_is_proposal_ready(self):
        self.assertEqual(PROPOSAL_READY,evaluate(policy(),snapshot(funding=False),evaluated_at=NOW)["receipt"]["decision"])
    def test_missing_intake_is_proposal_ready(self):
        r=evaluate(policy(),snapshot(intake=False),evaluated_at=NOW); self.assertEqual(PROPOSAL_READY,r["receipt"]["decision"]); self.assertTrue(any(x.startswith("INTAKE_") for x in r["receipt"]["blockers"]))
    def test_missing_owner_is_proposal_ready(self):
        self.assertEqual(PROPOSAL_READY,evaluate(policy(),snapshot(owner=False),evaluated_at=NOW)["receipt"]["decision"])
    def test_buyer_no_holds(self):
        s=snapshot(); s["buyer_approval"]["decision"]="NO"; self.assertEqual(HOLD,evaluate(policy(),s,evaluated_at=NOW)["receipt"]["decision"])
    def test_scope_change_after_buyer_approval_holds(self):
        s=snapshot(); s["scope"]["version"]="v2"; r=evaluate(policy(),s,evaluated_at=NOW); self.assertIn("BUYER_SCOPE_MISMATCH",r["receipt"]["holds"])
    def test_scope_change_after_funding_holds(self):
        s=snapshot(); s["scope"]["acceptance"].append("new-test"); r=evaluate(policy(),s,evaluated_at=NOW); self.assertIn("FUNDING_SCOPE_MISMATCH",r["receipt"]["holds"])
    def test_amount_mismatch_holds(self):
        s=snapshot(); s["funding"]["amount_minor"]=249999; self.assertIn("FUNDING_AMOUNT_MISMATCH",evaluate(policy(),s,evaluated_at=NOW)["receipt"]["holds"])
    def test_currency_mismatch_holds(self):
        s=snapshot(); s["funding"]["currency"]="EUR"; self.assertIn("FUNDING_CURRENCY_MISMATCH",evaluate(policy(),s,evaluated_at=NOW)["receipt"]["holds"])
    def test_refunded_or_pending_funding_holds(self):
        for state in ("REFUNDED","PENDING","VOID"):
            s=snapshot(); s["funding"]["state"]=state
            with self.subTest(state=state): self.assertIn("FUNDING_STATE_NOT_EXECUTION_READY",evaluate(policy(),s,evaluated_at=NOW)["receipt"]["holds"])
    def test_funding_type_unaccepted_holds(self):
        s=snapshot(); s["funding"]["funding_type"]="CRYPTO_AWARD"; s["funding"]["state"]="PAID"; self.assertIn("FUNDING_TYPE_NOT_ACCEPTED",evaluate(policy(),s,evaluated_at=NOW)["receipt"]["holds"])
    def test_expired_funding_holds(self):
        s=snapshot(); s["funding"]["expires_at"]="2026-09-13T09:59:59Z"; self.assertIn("FUNDING_EXPIRED",evaluate(policy(),s,evaluated_at=NOW)["receipt"]["holds"])
    def test_expired_scope_holds(self):
        s=snapshot(); s["scope"]["expires_at"]="2026-09-13T09:59:59Z"; self.assertIn("SCOPE_EXPIRED",evaluate(policy(),s,evaluated_at=NOW)["receipt"]["holds"])
    def test_incomplete_capture_holds(self):
        s=snapshot(); s["capture_complete"]=False; self.assertIn("CAPTURE_INCOMPLETE",evaluate(policy(),s,evaluated_at=NOW)["receipt"]["holds"])
    def test_undeclared_intake_holds(self):
        s=snapshot(); s["intake"]["received_inputs"].append("production-secret"); self.assertTrue(any(x.startswith("UNDECLARED_INTAKE_INPUT") for x in evaluate(policy(),s,evaluated_at=NOW)["receipt"]["holds"]))
    def test_owner_reject_holds(self):
        s=snapshot(); s["owner_approval"]["decision"]="REJECT"; self.assertIn("OWNER_DID_NOT_APPROVE",evaluate(policy(),s,evaluated_at=NOW)["receipt"]["holds"])
    def test_future_approval_rejected(self):
        s=snapshot(); s["buyer_approval"]["approved_at"]="2026-09-13T10:00:01Z"; self.assertRaises(GateInputError,evaluate,policy(),s,evaluated_at=NOW)
    def test_bool_not_int(self):
        s=snapshot(); s["scope"]["price_minor"]=True; self.assertRaises(GateInputError,evaluate,policy(),s,evaluated_at=NOW)
    def test_unknown_field_rejected(self):
        s=snapshot(); s["funding"]["cash_available"]=True; self.assertRaises(GateInputError,evaluate,policy(),s,evaluated_at=NOW)
    def test_tamper_breaks_verify(self):
        s=snapshot(); r=evaluate(policy(),s,evaluated_at=NOW); r["receipt"]["decision"]="HOLD"; self.assertFalse(verify(r,policy=policy(),snapshot=s))
    def test_self_rehashed_forgery_breaks_verify(self):
        s=snapshot(); r=evaluate(policy(),s,evaluated_at=NOW); r["receipt"]["production_access_authorized"]=True
        core=dict(r["receipt"]); core.pop("receipt_sha256"); r["receipt"]["receipt_sha256"]=digest(core); self.assertFalse(verify(r,policy=policy(),snapshot=s))
    def test_wrong_bound_snapshot_breaks_verify(self):
        s=snapshot(); r=evaluate(policy(),s,evaluated_at=NOW); s2=copy.deepcopy(s); s2["scope"]["version"]="v2"; self.assertFalse(verify(r,policy=policy(),snapshot=s2))
    def test_no_revenue_or_cash_inference(self):
        r=evaluate(policy(),snapshot(),evaluated_at=NOW)["receipt"]
        for f in ("contract_legally_enforceable_inferred","funds_collected_cash_inferred","production_access_authorized","scope_expansion_authorized","revenue_recognized_inferred","provider_mutation_performed"): self.assertFalse(r[f])

if __name__=="__main__": unittest.main()
