from __future__ import annotations
import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from .vault import *

T0 = "2026-09-13T20:00:00Z"
T1 = "2026-09-13T21:00:00Z"

def h(ch: str) -> str: return ch * 64

def fixture():
    items = [
        ("entity", "ENTITY_STANDING", h("1"), {"jurisdiction":"US-IN","standing":"GOOD"}, "2027-01-01"),
        ("past1", "CORPORATE_PAST_PERFORMANCE", h("2"), {"engagement_type":"software-engineering","completed_on":"2026-06-01","corporate_history":True}, None),
        ("past2", "CORPORATE_PAST_PERFORMANCE", h("3"), {"engagement_type":"software-engineering","completed_on":"2026-07-01","corporate_history":True}, None),
        ("reference", "CLIENT_REFERENCE", h("4"), {"organization_sha256":h("a"),"release":"CONTACT"}, None),
        ("credential", "STAFF_CREDENTIAL", h("5"), {"staff_id":"staff-1","credential":"systems-engineer","status":"CURRENT"}, None),
        ("availability", "STAFF_AVAILABILITY", h("6"), {"staff_id":"staff-1","available_from":"2026-09-01","available_through":"2026-12-31"}, None),
        ("insurance", "INSURANCE_ARTIFACT", h("7"), {"coverage":"technology-eo","currency":"USD","limit_minor":500000000,"status":"ACTIVE"}, "2026-12-31"),
        ("security", "SECURITY_ARTIFACT", h("8"), {"artifact":"security-questionnaire","status":"CURRENT"}, "2026-12-31"),
        ("financial", "FINANCIAL_DOCUMENT", h("9"), {"document_type":"annual-report","period_start":"2025-01-01","period_end":"2025-12-31"}, None),
        ("signer", "SIGNER_AUTHORITY", h("b"), {"staff_id":"staff-1","scope":"proposal-signature","delegation_status":"ACTIVE"}, "2026-12-31"),
        ("form", "VENDOR_FORM", h("c"), {"form_type":"w9","status":"CURRENT"}, "2027-01-01"),
    ]
    authority = {"schema":AUTHORITY_SCHEMA,"authority_id":"owner-facts","generation":1,"previous_authority_sha256":None,"issued_at":T0,
                 "evidence":[{"evidence_id":eid,"kind":kind,"source_sha256":sha} for eid,kind,sha,_,_ in items]}
    registry = {"schema":REGISTRY_SCHEMA,"registry_id":"snapshot-1","authority_id":"owner-facts","authority_generation":1,"generated_at":T0,
                "items":[{"evidence_id":eid,"kind":kind,"source_sha256":sha,"observed_at":T0,"max_age_seconds":86400*30,"valid_through":valid,"state":"EVIDENCED","metadata":meta} for eid,kind,sha,meta,valid in items]}
    reqs = [
        ("entity","ENTITY_STANDING",1,{"standing":"GOOD"}),
        ("past","CORPORATE_PAST_PERFORMANCE",2,{"engagement_type":"software-engineering"}),
        ("ref","CLIENT_REFERENCE",1,{"release_at_least":"CONTACT"}),
        ("staff","STAFF_AVAILABILITY",1,{"staff_id":"staff-1"}),
        ("ins","INSURANCE_ARTIFACT",1,{"coverage":"technology-eo","status":"ACTIVE"}),
        ("sec","SECURITY_ARTIFACT",1,{"artifact":"security-questionnaire","status":"CURRENT"}),
        ("fin","FINANCIAL_DOCUMENT",1,{"document_type":"annual-report"}),
        ("sign","SIGNER_AUTHORITY",1,{"staff_id":"staff-1","scope":"proposal-signature","delegation_status":"ACTIVE"}),
    ]
    query={"schema":QUERY_SCHEMA,"query_id":"synthetic-rfp","subject_id":"synthetic-bidder","authority_id":"owner-facts","authority_generation":1,
           "registry_id":"snapshot-1","registry_max_age_seconds":86400*7,"requirements":[{"requirement_id":rid,"kind":kind,"min_count":count,"exact":exact} for rid,kind,count,exact in reqs]}
    return authority, registry, query

def compile_fx(at=T1):
    a,r,q=fixture(); ar,rr=roots(a,r); return compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=at)

class VaultTests(unittest.TestCase):
    def test_ready(self):
        b=compile_fx(); self.assertEqual(b["result"]["status"],"EVIDENCE_READY"); self.assertEqual(b["result"]["counts"],{"EVIDENCE_READY":8,"HOLD":0})
    def test_deterministic(self): self.assertEqual(compile_fx(),compile_fx())
    def test_order_independent(self):
        a,r,q=fixture(); a["evidence"].reverse(); r["items"].reverse(); q["requirements"].reverse(); ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1),compile_fx())
    def test_authority_bits_false(self): self.assertTrue(all(v is False for v in compile_fx()["result"]["authority"].values()))
    def test_verify_exact_and_current(self):
        a,r,q=fixture(); ar,rr=roots(a,r); b=compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)
        p=verify_bundle(a,r,q,b,expected_authority_sha256=ar,expected_registry_sha256=rr,verified_at=T1); self.assertTrue(p["verified"]); self.assertEqual(p["current_status"],"EVIDENCE_READY")
    def test_expiry_becomes_current_hold(self):
        a,r,q=fixture(); r["items"][6]["valid_through"]="2026-09-13"; ar,rr=roots(a,r)
        b=compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)
        p=verify_bundle(a,r,q,b,expected_authority_sha256=ar,expected_registry_sha256=rr,verified_at="2026-09-14T01:00:00Z"); self.assertEqual(p["historical_status"],"EVIDENCE_READY"); self.assertEqual(p["current_status"],"HOLD")
    def test_wrong_authority_root(self):
        a,r,q=fixture(); _,rr=roots(a,r)
        with self.assertRaises(VaultError): compile_vault(a,r,q,expected_authority_sha256=h("f"),expected_registry_sha256=rr,evaluated_at=T1)
    def test_wrong_registry_root(self):
        a,r,q=fixture(); ar,_=roots(a,r)
        with self.assertRaises(VaultError): compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=h("f"),evaluated_at=T1)
    def test_authority_transplant(self):
        a,r,q=fixture(); a["evidence"][0]["source_sha256"]=h("f"); ar,rr=roots(a,r)
        with self.assertRaises(VaultError): compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)
    def test_evidence_set_mismatch(self):
        a,r,q=fixture(); r["items"].pop(); ar,rr=roots(a,r)
        with self.assertRaises(VaultError): compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)
    def test_query_authority_mismatch(self):
        a,r,q=fixture(); q["authority_generation"]=2; ar,rr=roots(a,r)
        with self.assertRaises(VaultError): compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)
    def test_generation_one_predecessor_rejected(self):
        a,_,_=fixture(); a["previous_authority_sha256"]=h("d")
        with self.assertRaises(VaultError): normalize_authority(a)
    def test_later_generation_requires_predecessor(self):
        a,_,_=fixture(); a["generation"]=2
        with self.assertRaises(VaultError): normalize_authority(a)
    def test_future_authority_rejected(self):
        a,r,q=fixture(); a["issued_at"]="2026-09-14T00:00:00Z"; ar,rr=roots(a,r)
        with self.assertRaises(VaultError): compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)
    def test_future_registry_rejected(self):
        a,r,q=fixture(); r["generated_at"]="2026-09-14T00:00:00Z"; ar,rr=roots(a,r)
        with self.assertRaises(VaultError): compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)
    def test_future_observation_holds(self):
        a,r,q=fixture(); r["items"][0]["observed_at"]="2026-09-14T00:00:00Z"; ar,rr=roots(a,r)
        b=compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1); self.assertEqual(b["result"]["status"],"HOLD")
    def test_stale_item_holds(self):
        a,r,q=fixture(); r["items"][0]["max_age_seconds"]=1; ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)["result"]["status"],"HOLD")
    def test_stale_registry_holds(self):
        a,r,q=fixture(); q["registry_max_age_seconds"]=1; ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)["result"]["status"],"HOLD")
    def test_withdrawn_holds(self):
        a,r,q=fixture(); r["items"][0]["state"]="WITHDRAWN"; ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)["result"]["status"],"HOLD")
    def test_individual_history_not_corporate(self):
        a,r,q=fixture(); r["items"][1]["metadata"]["corporate_history"]=False; ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)["result"]["status"],"HOLD")
    def test_reference_release_enforced(self):
        a,r,q=fixture(); r["items"][3]["metadata"]["release"]="NAMING"; ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)["result"]["status"],"HOLD")
    def test_insurance_status_enforced(self):
        a,r,q=fixture(); r["items"][6]["metadata"]["status"]="OTHER"; ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)["result"]["status"],"HOLD")
    def test_security_status_enforced(self):
        a,r,q=fixture(); r["items"][7]["metadata"]["status"]="OTHER"; ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)["result"]["status"],"HOLD")
    def test_signer_status_enforced(self):
        a,r,q=fixture(); r["items"][9]["metadata"]["delegation_status"]="OTHER"; ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)["result"]["status"],"HOLD")
    def test_subject_change_changes_result(self):
        a,r,q=fixture(); ar,rr=roots(a,r); one=compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1); q["subject_id"]="other"
        two=compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1); self.assertNotEqual(one["receipt"]["query_sha256"],two["receipt"]["query_sha256"])
    def test_min_count(self):
        a,r,q=fixture(); next(x for x in q["requirements"] if x["requirement_id"]=="past")["min_count"]=3; ar,rr=roots(a,r)
        self.assertEqual(compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1)["result"]["status"],"HOLD")
    def test_bundle_tamper_result(self):
        a,r,q=fixture(); ar,rr=roots(a,r); b=compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1); b["result"]["status"]="HOLD"
        with self.assertRaises(VaultError): verify_bundle(a,r,q,b,expected_authority_sha256=ar,expected_registry_sha256=rr,verified_at=T1)
    def test_bundle_tamper_markdown(self):
        a,r,q=fixture(); ar,rr=roots(a,r); b=compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1); b["markdown"] += "tamper"
        with self.assertRaises(VaultError): verify_bundle(a,r,q,b,expected_authority_sha256=ar,expected_registry_sha256=rr,verified_at=T1)
    def test_bundle_tamper_receipt(self):
        a,r,q=fixture(); ar,rr=roots(a,r); b=compile_vault(a,r,q,expected_authority_sha256=ar,expected_registry_sha256=rr,evaluated_at=T1); b["receipt"]["decision"]="HOLD"
        with self.assertRaises(VaultError): verify_bundle(a,r,q,b,expected_authority_sha256=ar,expected_registry_sha256=rr,verified_at=T1)
    def test_duplicate_json_key(self):
        with self.assertRaises(VaultError): load_json(b'{"x":1,"x":2}')
    def test_float_json(self):
        with self.assertRaises(VaultError): load_json(b'{"x":1.2}')
    def test_nonfinite_json(self):
        with self.assertRaises(VaultError): load_json(b'{"x":NaN}')
    def test_bom_json(self):
        with self.assertRaises(VaultError): load_json(b'\xef\xbb\xbf{}')
    def test_unknown_registry_field(self):
        _,r,_=fixture(); r["oops"]=1
        with self.assertRaises(VaultError): normalize_registry(r)
    def test_duplicate_evidence_id(self):
        _,r,_=fixture(); r["items"].append(deepcopy(r["items"][0]))
        with self.assertRaises(VaultError): normalize_registry(r)
    def test_duplicate_requirement_id(self):
        _,_,q=fixture(); q["requirements"].append(deepcopy(q["requirements"][0]))
        with self.assertRaises(VaultError): normalize_query(q)
    def test_bad_currency(self):
        _,r,_=fixture(); r["items"][6]["metadata"]["currency"]="usd"
        with self.assertRaises(VaultError): normalize_registry(r)
    def test_bad_availability_range(self):
        _,r,_=fixture(); r["items"][5]["metadata"]["available_from"]="2027-01-01"
        with self.assertRaises(VaultError): normalize_registry(r)
    def test_bad_financial_period(self):
        _,r,_=fixture(); r["items"][8]["metadata"]["period_start"]="2026-01-01"
        with self.assertRaises(VaultError): normalize_registry(r)
    def test_unknown_selector(self):
        _,_,q=fixture(); q["requirements"][0]["exact"]["buyer"]="x"
        with self.assertRaises(VaultError): normalize_query(q)
    def test_bool_as_integer(self):
        _,r,_=fixture(); r["items"][6]["metadata"]["limit_minor"]=True
        with self.assertRaises(VaultError): normalize_registry(r)
    def test_markdown_boundary(self):
        md=compile_fx()["markdown"]; self.assertIn("All action-authority flags",md); self.assertIn("never authorizes contacting",md)
    def test_reference_org_is_digest_only(self):
        _,r,_=fixture(); raw=json.dumps(r); self.assertNotIn("example.com",raw); self.assertNotIn("Synthetic Reference Org",raw)

if __name__ == "__main__": unittest.main()
