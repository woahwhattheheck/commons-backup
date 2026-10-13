import copy, json, tempfile, unittest
from pathlib import Path
import post_delivery_acceptance as p

def base():
    m={"id":"ms-1","scope_ref":"scope-1","criteria":[
        {"id":"crit-a","required":True,"description_digest":"a"*64},
        {"id":"crit-b","required":True,"description_digest":"b"*64},
        {"id":"crit-c","required":False,"description_digest":"c"*64}]}
    v={"id":"v-1","milestone_id":"ms-1","ordinal":1,"artifact_ref":"artifact://bundle/v1","artifact_sha256":"d"*64,
       "criteria_ids":["crit-a","crit-b","crit-c"],"scope_agreement_sha256":"e"*64,"delivery_receipt_sha256":"f"*64,"created_at":"2026-09-13T12:00:00Z"}
    return {"schema_version":1,"portfolio":{"name":"Synthetic delivery"},"milestones":[m],"versions":[v],"evidence":[],"events":[]}

def add(pkt, eid, kind, when, authority, *, version="v-1", disposition=None, criteria=None, status="verified"):
    v=next(x for x in pkt["versions"] if x["id"]==version)
    proof="proof-"+eid
    e={"id":eid,"kind":kind,"milestone_id":"ms-1","version_id":version,"version_sha256":p.dig(p._version_core(v)),
       "occurred_at":when,"evidence_id":proof}
    if disposition is not None:e["disposition"]=disposition
    if criteria is not None:e["criterion_ids"]=criteria
    pkt["events"].append(e)
    pkt["evidence"].append({"id":proof,"status":status,"authority":authority,"captured_at":when,"reference":"synthetic://"+proof,"sha256":("%x"%(len(pkt["evidence"])+1))[-1]*64})
    return pkt

class T(unittest.TestCase):
    def test_delivery_not_acceptance(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport")
        self.assertEqual(p.evaluate(q)["milestones"][0]["state"],"DELIVERED_PENDING_BUYER_ACCEPTANCE")
    def test_internal_cannot_accept(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport")
        add(q,"acc","BUYER_DISPOSITION","2026-09-13T12:20:00Z","owner_approved",disposition="ACCEPTED",criteria=["crit-a","crit-b"])
        r=p.evaluate(q)["milestones"][0]; self.assertEqual(r["state"],"HOLD"); self.assertIn("acc:AUTHORITY_MISMATCH",r["blockers"])
    def test_partial_then_full(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport")
        add(q,"a","BUYER_DISPOSITION","2026-09-13T12:20:00Z","counterparty_evidence",disposition="ACCEPTED",criteria=["crit-a"])
        self.assertEqual(p.evaluate(q)["milestones"][0]["state"],"PARTIALLY_ACCEPTED_EVIDENCE")
        add(q,"b","BUYER_DISPOSITION","2026-09-13T12:30:00Z","counterparty_evidence",disposition="ACCEPTED",criteria=["crit-b"])
        self.assertEqual(p.evaluate(q)["milestones"][0]["state"],"BUYER_ACCEPTED_EVIDENCE")
    def test_optional_not_required(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport")
        add(q,"a","BUYER_DISPOSITION","2026-09-13T12:20:00Z","counterparty_evidence",disposition="ACCEPTED",criteria=["crit-a","crit-b"])
        r=p.evaluate(q)["milestones"][0]; self.assertEqual(r["state"],"BUYER_ACCEPTED_EVIDENCE"); self.assertEqual(r["pending_required"],[])
    def test_revision_and_rejection(self):
        for disp,state in [("REVISION_REQUESTED","REVISION_REQUIRED"),("REJECTED","REJECTED")]:
            q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport")
            add(q,"d","BUYER_DISPOSITION","2026-09-13T12:20:00Z","counterparty_evidence",disposition=disp,criteria=["crit-a","crit-b","crit-c"])
            self.assertEqual(p.evaluate(q)["milestones"][0]["state"],state)
    def test_acceptance_before_delivery_holds(self):
        q=base(); add(q,"a","BUYER_DISPOSITION","2026-09-13T12:20:00Z","counterparty_evidence",disposition="ACCEPTED",criteria=["crit-a","crit-b"])
        self.assertIn("a:ACCEPTANCE_BEFORE_DELIVERY",p.evaluate(q)["milestones"][0]["blockers"])
    def test_new_version_does_not_inherit_acceptance(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport"); add(q,"a","BUYER_DISPOSITION","2026-09-13T12:20:00Z","counterparty_evidence",disposition="ACCEPTED",criteria=["crit-a","crit-b"])
        v2=copy.deepcopy(q["versions"][0]); v2.update({"id":"v-2","ordinal":2,"artifact_ref":"artifact://bundle/v2","artifact_sha256":"1"*64,"created_at":"2026-09-13T13:00:00Z"}); q["versions"].append(v2)
        r=p.evaluate(q)["milestones"][0]; self.assertEqual(r["current_version_id"],"v-2"); self.assertEqual(r["state"],"HOLD"); self.assertEqual(r["accepted_required"],[])
    def test_version_digest_transplant_fails(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport"); q["events"][0]["version_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"version digest mismatch"):p.evaluate(q)
    def test_wrong_delivery_authority_holds(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","internal_record")
        self.assertIn("deliver:AUTHORITY_MISMATCH",p.evaluate(q)["milestones"][0]["blockers"])
    def test_pending_counterparty_evidence_holds(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport"); add(q,"a","BUYER_DISPOSITION","2026-09-13T12:20:00Z","counterparty_evidence",disposition="ACCEPTED",criteria=["crit-a"],status="pending")
        self.assertIn("a:EVIDENCE_NOT_VERIFIED",p.evaluate(q)["milestones"][0]["blockers"])
    def test_criterion_set_bound_exactly(self):
        q=base(); q["versions"][0]["criteria_ids"]=["crit-a","crit-b"]
        with self.assertRaisesRegex(ValueError,"criteria_ids"):p.evaluate(q)
    def test_revision_must_bind_full_set(self):
        q=base()
        with self.assertRaisesRegex(ValueError,"must bind all criteria"):
            add(q,"d","BUYER_DISPOSITION","2026-09-13T12:20:00Z","counterparty_evidence",disposition="REVISION_REQUESTED",criteria=["crit-a"]); p.evaluate(q)
    def test_bool_ordinal_rejected(self):
        q=base(); q["versions"][0]["ordinal"]=True
        with self.assertRaisesRegex(ValueError,"ordinal"):p.evaluate(q)
    def test_order_deterministic_and_verify(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport"); add(q,"a","BUYER_DISPOSITION","2026-09-13T12:20:00Z","counterparty_evidence",disposition="ACCEPTED",criteria=["crit-a"])
        x=p.evaluate(q); z=copy.deepcopy(q); z["events"].reverse(); z["evidence"].reverse(); self.assertEqual(x,p.evaluate(z)); self.assertTrue(p.verify(q,x)[0]); x["summary"]["revenue_recognized"]=True; self.assertFalse(p.verify(q,x)[0])
    def test_cli_roundtrip_and_create_exclusive(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport")
        with tempfile.TemporaryDirectory() as t:
            r=Path(t); inp=r/"in.json"; out=r/"out.json"; md=r/"out.md"; csvp=r/"out.csv"; inp.write_text(json.dumps(q))
            self.assertEqual(p.main(["compile","--input",str(inp),"--json-out",str(out),"--markdown-out",str(md),"--csv-out",str(csvp)]),0)
            self.assertEqual(p.main(["verify","--input",str(inp),"--ledger",str(out)]),0)
            with self.assertRaises(FileExistsError):p.main(["compile","--input",str(inp),"--json-out",str(out)])
    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            x=Path(t)/"x.json"; x.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(ValueError,"duplicate JSON key"):p.load(x)
    def test_superseded_current_holds(self):
        q=base(); add(q,"deliver","DELIVERED","2026-09-13T12:10:00Z","delivery_transport"); add(q,"s","SUPERSEDED","2026-09-13T12:20:00Z","owner_approved")
        self.assertEqual(p.evaluate(q)["milestones"][0]["state"],"HOLD")
    def test_authority_ceiling(self):
        q=base(); x=p.evaluate(q); self.assertFalse(x["summary"]["fulfillment_authorized"]); self.assertFalse(x["summary"]["payment_authorized"]); self.assertFalse(x["summary"]["revenue_recognized"]); self.assertTrue(x["authority_boundary"]["technical_pass_is_not_buyer_acceptance"])

if __name__=="__main__":unittest.main()
