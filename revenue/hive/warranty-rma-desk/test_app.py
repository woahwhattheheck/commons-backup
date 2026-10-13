#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures
import hashlib
import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("warranty_rma_app", HERE/"app.py")
app=importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(app)

class Clock:
    def __init__(self): self.n=0
    def __call__(self):
        self.n+=1
        return f"2026-09-13T14:00:{self.n%60:02d}Z"

class Factory:
    def __init__(self,prefix): self.prefix=prefix; self.n=0
    def __call__(self,n):
        self.n+=1
        return (f"{self.n:08x}-{self.prefix}-{self.n:024x}")[:n]

class DeskTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.clock=Clock(); self.tokens=Factory("status"); self.ids=Factory("abcdef")
        self.store=app.Store(Path(self.tmp.name)/"desk.sqlite3",now=self.clock,token_factory=self.tokens,id_factory=self.ids)
        self.product=self.store.create_product({
            "sku":"BREWER-1","model":"Countertop Brewer","serial_required":True,
            "warranty_days":365,"instructions":"Merchant reviews the submitted facts before any decision."
        })
    def tearDown(self):
        self.store.close(); self.tmp.cleanup()
    def intake(self,key="intake-1",serial="SER-1",issue="Pump stops",evidence=True):
        p={"idempotency_key":key,"sku":"BREWER-1","serial":serial,"purchase_ref":"ORD-1","purchase_date":"2026-09-01","issue":issue}
        if evidence:
            p["evidence"]=[{"evidence_id":"photo-1","filename":"photo.jpg","sha256":"a"*64,"mime":"image/jpeg"}]
        return self.store.submit_case(p)
    def err(self,code,fn,*a,**kw):
        with self.assertRaises(app.DeskError) as cm: fn(*a,**kw)
        self.assertEqual(cm.exception.code,code); return cm.exception
    def approve(self,c):
        d=self.store.operator_case(c["case"]["case_id"])
        return self.store.operator_decide(d["case_id"],{
            "idempotency_key":"approve-1","expected_revision":d["revision"],"policy_id":d["policy"]["policy_id"],
            "decision":"APPROVE_RMA","public_message":"Approved for return inspection.","internal_note":"Synthetic approval."
        })
    def full_to_inspected(self):
        c=self.intake(); cid=c["case"]["case_id"]; self.approve(c)
        d=self.store.operator_case(cid)
        self.store.operator_receive(cid,{"idempotency_key":"receive-1","expected_revision":d["revision"],"rma_ref":d["rma_ref"],"receive_ref":"DOCK-1","public_message":"Return received.","internal_note":""})
        d=self.store.operator_case(cid)
        self.store.operator_inspect(cid,{"idempotency_key":"inspect-1","expected_revision":d["revision"],"inspection":"FAULT_CONFIRMED","public_message":"Inspection completed.","internal_note":"Synthetic bench note."})
        return c, self.store.operator_case(cid)

    def test_strict_json_rejects_duplicate_and_nonfinite(self):
        self.err("INVALID_JSON",app.loads_strict,b'{"a":1,"a":2}')
        self.err("INVALID_JSON",app.loads_strict,b'{"a":NaN}')

    def test_intake_creates_private_capability_hash_only(self):
        c=self.intake(); self.assertTrue(c["created"]); token=c["status_token"]; self.assertTrue(token)
        raw=Path(self.tmp.name,"desk.sqlite3").read_bytes()
        self.assertNotIn(token.encode(),raw)
        pub=self.store.customer_status(c["case"]["case_id"],token)
        self.assertEqual(pub["status"],"SUBMITTED"); self.assertFalse(pub["external_authority"])

    def test_exact_intake_retry_is_one_case_and_changed_retry_conflicts(self):
        a=self.intake(); b=self.intake()
        self.assertTrue(a["created"]); self.assertFalse(b["created"]); self.assertIsNone(b["status_token"])
        self.assertEqual(len(self.store.list_cases()),1)
        self.err("IDEMPOTENCY_CONFLICT",self.intake,issue="Different")

    def test_active_duplicate_serial_fails_then_closed_serial_can_reenter(self):
        c,_=self.full_to_inspected(); cid=c["case"]["case_id"]
        d=self.store.operator_case(cid)
        self.store.operator_resolve(cid,{"idempotency_key":"resolve-1","expected_revision":d["revision"],"resolution":"REPLACEMENT","public_message":"Replacement approved for merchant handoff.","internal_note":""})
        d=self.store.operator_case(cid)
        self.store.operator_close(cid,{"idempotency_key":"close-1","expected_revision":d["revision"],"completion_ref":"MERCHANT-1","public_message":"Case closed.","internal_note":""})
        again=self.intake(key="intake-2",serial="SER-1",issue="Separate later incident")
        self.assertTrue(again["created"])
        self.err("ACTIVE_SERIAL_CASE",self.intake,key="intake-3",serial="SER-1",issue="Third while active")

    def test_serial_required_and_unknown_product_fail_closed(self):
        self.err("SERIAL_REQUIRED",self.intake,serial="")
        p={"idempotency_key":"x","sku":"NOPE","purchase_ref":"O","purchase_date":"2026-09-01","issue":"x"}
        self.err("PRODUCT_NOT_FOUND",self.store.submit_case,p)

    def test_cross_case_status_capability_isolation(self):
        a=self.intake(key="a",serial="SER-A"); b=self.intake(key="b",serial="SER-B")
        self.err("INVALID_STATUS_TOKEN",self.store.customer_status,b["case"]["case_id"],a["status_token"])
        self.assertEqual(self.store.customer_status(a["case"]["case_id"],a["status_token"])["case_id"],a["case"]["case_id"])

    def test_customer_status_never_exposes_operator_internal_note(self):
        c=self.intake(); cid=c["case"]["case_id"]
        d=self.store.operator_case(cid)
        self.store.operator_decide(cid,{"idempotency_key":"need-1","expected_revision":d["revision"],"policy_id":d["policy"]["policy_id"],"decision":"REQUEST_INFO","public_message":"Please add the label photo.","internal_note":"PRIVATE OPERATOR NOTE"})
        pub=json.dumps(self.store.customer_status(cid,c["status_token"]))
        self.assertNotIn("PRIVATE OPERATOR NOTE",pub); self.assertIn("label photo",pub)

    def test_request_info_supplement_returns_to_review_and_replay_safe(self):
        c=self.intake(); cid=c["case"]["case_id"]; d=self.store.operator_case(cid)
        self.store.operator_decide(cid,{"idempotency_key":"need-1","expected_revision":d["revision"],"policy_id":d["policy"]["policy_id"],"decision":"REQUEST_INFO","public_message":"More info please.","internal_note":""})
        pub=self.store.customer_status(cid,c["status_token"]); self.assertEqual(pub["status"],"NEEDS_INFO")
        p={"idempotency_key":"supp-1","expected_revision":pub["revision"],"message":"Added detail","evidence":[{"evidence_id":"label","filename":"label.png","sha256":"b"*64,"mime":"image/png"}]}
        a=self.store.customer_supplement(cid,c["status_token"],p); b=self.store.customer_supplement(cid,c["status_token"],p)
        self.assertFalse(a["replayed"]); self.assertTrue(b["replayed"]); self.assertEqual(b["case"]["status"],"SUBMITTED")
        p2=dict(p);p2["message"]="changed";self.err("IDEMPOTENCY_CONFLICT",self.store.customer_supplement,cid,c["status_token"],p2)

    def test_customer_cannot_supplement_without_need_info(self):
        c=self.intake()
        self.err("INVALID_TRANSITION",self.store.customer_supplement,c["case"]["case_id"],c["status_token"],{"idempotency_key":"s","expected_revision":1,"message":"x"})

    def test_policy_revision_cannot_rebind_existing_case(self):
        c=self.intake(); cid=c["case"]["case_id"]; old=self.store.operator_case(cid)
        new=self.store.revise_policy("BREWER-1",{"warranty_days":180,"instructions":"New merchant-authored revision."})
        self.assertNotEqual(new["policy_id"],old["policy"]["policy_id"])
        self.err("POLICY_MISMATCH",self.store.operator_decide,cid,{"idempotency_key":"bad","expected_revision":old["revision"],"policy_id":new["policy_id"],"decision":"APPROVE_RMA","public_message":"x","internal_note":""})
        self.assertEqual(self.store.operator_case(cid)["policy"]["policy_id"],old["policy"]["policy_id"])

    def test_stale_case_revision_blocks_operator_decision(self):
        c=self.intake(); cid=c["case"]["case_id"]; d=self.store.operator_case(cid)
        self.store.operator_decide(cid,{"idempotency_key":"need","expected_revision":1,"policy_id":d["policy"]["policy_id"],"decision":"REQUEST_INFO","public_message":"Need info","internal_note":""})
        self.err("STALE_REVISION",self.store.operator_decide,cid,{"idempotency_key":"old","expected_revision":1,"policy_id":d["policy"]["policy_id"],"decision":"DENY","public_message":"Denied","internal_note":""})

    def test_customer_never_self_approves(self):
        c=self.intake(); pub=self.store.customer_status(c["case"]["case_id"],c["status_token"])
        self.assertEqual(pub["status"],"SUBMITTED"); self.assertIsNone(pub["rma_ref"])
        self.assertNotIn("decision",pub)

    def test_receive_before_rma_and_wrong_rma_fail(self):
        c=self.intake(); cid=c["case"]["case_id"]
        self.err("INVALID_TRANSITION",self.store.operator_receive,cid,{"idempotency_key":"r","expected_revision":1,"rma_ref":"RMA-X","receive_ref":"D-1","public_message":"x","internal_note":""})
        self.approve(c); d=self.store.operator_case(cid)
        self.err("RMA_MISMATCH",self.store.operator_receive,cid,{"idempotency_key":"r2","expected_revision":d["revision"],"rma_ref":"RMA-X","receive_ref":"D-1","public_message":"x","internal_note":""})

    def test_receive_replay_and_changed_replay(self):
        c=self.intake(); cid=c["case"]["case_id"]; self.approve(c); d=self.store.operator_case(cid)
        p={"idempotency_key":"r1","expected_revision":d["revision"],"rma_ref":d["rma_ref"],"receive_ref":"DOCK-1","public_message":"Received","internal_note":""}
        a=self.store.operator_receive(cid,p); b=self.store.operator_receive(cid,p)
        self.assertFalse(a["replayed"]); self.assertTrue(b["replayed"])
        q=dict(p);q["receive_ref"]="DOCK-2";self.err("IDEMPOTENCY_CONFLICT",self.store.operator_receive,cid,q)

    def test_receive_ref_cannot_cross_cases(self):
        a=self.intake(key="a",serial="A"); b=self.intake(key="b",serial="B")
        self.approve(a); da=self.store.operator_case(a["case"]["case_id"])
        self.store.operator_receive(da["case_id"],{"idempotency_key":"ra","expected_revision":da["revision"],"rma_ref":da["rma_ref"],"receive_ref":"DOCK-SAME","public_message":"Received","internal_note":""})
        self.approve(b); db=self.store.operator_case(b["case"]["case_id"])
        self.err("RECEIVE_REF_CONFLICT",self.store.operator_receive,db["case_id"],{"idempotency_key":"rb","expected_revision":db["revision"],"rma_ref":db["rma_ref"],"receive_ref":"DOCK-SAME","public_message":"Received","internal_note":""})

    def test_inspect_before_receive_fails(self):
        c=self.intake(); cid=c["case"]["case_id"]; self.approve(c); d=self.store.operator_case(cid)
        self.err("INVALID_TRANSITION",self.store.operator_inspect,cid,{"idempotency_key":"i","expected_revision":d["revision"],"inspection":"FAULT_CONFIRMED","public_message":"x","internal_note":""})

    def test_resolution_before_inspection_fails(self):
        c=self.intake(); cid=c["case"]["case_id"]; self.approve(c); d=self.store.operator_case(cid)
        self.err("INVALID_TRANSITION",self.store.operator_resolve,cid,{"idempotency_key":"z","expected_revision":d["revision"],"resolution":"REFUND","public_message":"x","internal_note":""})

    def test_full_flow_and_close_handoff_is_not_provider_verification(self):
        c,d=self.full_to_inspected(); cid=d["case_id"]
        r=self.store.operator_resolve(cid,{"idempotency_key":"resolve","expected_revision":d["revision"],"resolution":"REPAIR","public_message":"Repair approved for merchant handoff.","internal_note":"Bench note"})
        d=r["case"]; self.assertEqual(d["status"],"RESOLUTION_APPROVED")
        close=self.store.operator_close(cid,{"idempotency_key":"close","expected_revision":d["revision"],"completion_ref":"MERCHANT-WORK-1","public_message":"Merchant marked the workflow complete.","internal_note":""})
        self.assertEqual(close["case"]["status"],"CLOSED")
        evt=close["case"]["events"][-1]; self.assertFalse(evt["payload"]["provider_verified"])
        self.assertTrue(evt["payload"]["merchant_observed_completion"])

    def test_close_before_resolution_fails(self):
        c=self.intake();cid=c["case"]["case_id"]
        self.err("INVALID_TRANSITION",self.store.operator_close,cid,{"idempotency_key":"c","expected_revision":1,"completion_ref":"X","public_message":"x","internal_note":""})

    def test_export_is_deterministic_and_authority_false(self):
        c=self.intake(); cid=c["case"]["case_id"]
        a=self.store.export_case(cid); b=self.store.export_case(cid); self.assertEqual(a,b)
        doc=json.loads(a); self.assertEqual(doc["schema"],"warranty-rma-case-export/v1")
        self.assertTrue(all(v is False for v in doc["authority"].values()))
        receipt=doc.pop("receipt_sha256"); self.assertEqual(receipt,hashlib.sha256(app.canonical_bytes(doc)).hexdigest())

    def test_db_reopen_preserves_state_and_token(self):
        c=self.intake(); cid=c["case"]["case_id"]; token=c["status_token"]
        self.store.close()
        self.store=app.Store(Path(self.tmp.name)/"desk.sqlite3",now=self.clock,token_factory=self.tokens,id_factory=self.ids)
        self.assertEqual(self.store.customer_status(cid,token)["status"],"SUBMITTED")
        self.assertEqual(len(self.store.list_products()),1)

    def test_same_intake_concurrency_creates_once(self):
        def go(_): return self.intake(key="concurrent",serial="CONCUR")
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            rows=list(ex.map(go,range(6)))
        self.assertEqual(sum(1 for x in rows if x["created"]),1); self.assertEqual(len([c for c in self.store.list_cases() if c["case_id"]==rows[0]["case"]["case_id"]]),1)

    def test_competing_decisions_only_one_revision_wins(self):
        c=self.intake();cid=c["case"]["case_id"];p=self.store.operator_case(cid)["policy"]["policy_id"]
        def go(dec,key):
            try:
                return self.store.operator_decide(cid,{"idempotency_key":key,"expected_revision":1,"policy_id":p,"decision":dec,"public_message":dec,"internal_note":""})["case"]["status"]
            except app.DeskError as e: return e.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            vals=list(ex.map(lambda x:go(*x),[("APPROVE_RMA","a"),("DENY","b")]))
        self.assertEqual(sum(v in {"APPROVED_RMA","DENIED"} for v in vals),1)
        self.assertEqual(sum(v in {"STALE_REVISION","INVALID_TRANSITION"} for v in vals),1)

    def test_operator_auth_is_exact_and_not_customer_token(self):
        auth=app.OperatorAuth("operator-secret-123456")
        self.assertTrue(auth.check("Bearer operator-secret-123456"))
        self.assertFalse(auth.check("Bearer operator-secret-123457"))
        c=self.intake(); self.assertFalse(auth.check("Bearer "+c["status_token"]))

    def test_file_metadata_bounds_and_digest_validation(self):
        p={"idempotency_key":"e","sku":"BREWER-1","serial":"E1","purchase_ref":"O","purchase_date":"2026-09-01","issue":"x","evidence":[{"evidence_id":"x","filename":"x","sha256":"BAD","mime":"image/jpeg"}]}
        self.err("INVALID_FIELD",self.store.submit_case,p)
        p["evidence"][0]["sha256"]="a"*64;p["evidence"][0]["mime"]="text/../../evil";self.err("INVALID_FIELD",self.store.submit_case,p)

    def test_unknown_fields_and_bool_as_int_fail(self):
        p={"sku":"B2","model":"x","serial_required":False,"warranty_days":True,"instructions":"x"}
        self.err("INVALID_FIELD",self.store.create_product,p)
        p={"sku":"B2","model":"x","serial_required":False,"warranty_days":10,"instructions":"x","extra":"no"}
        self.err("UNKNOWN_FIELD",self.store.create_product,p)

    def test_no_external_network_primitives_in_python_or_html(self):
        py=(HERE/"app.py").read_text().lower(); html=(HERE/"index.html").read_text().lower()
        for bad in ["requests.", "urllib.request", "socket.create_connection", "subprocess.", "smtp", "stripe"]:
            self.assertNotIn(bad,py)
        self.assertNotIn("http://",html); self.assertNotIn("https://",html)
        self.assertNotIn(".innerhtml",html)

class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=app.Store(Path(self.tmp.name)/"d.sqlite3",now=Clock(),token_factory=Factory("status"),id_factory=Factory("abcdef"))
        self.store.create_product({"sku":"P1","model":"M1","serial_required":False,"warranty_days":30,"instructions":"Review."})
        self.auth=app.OperatorAuth("operator-secret-123456")
        handler=app.make_handler(self.store,self.auth,(HERE/"index.html").read_bytes())
        self.server=ThreadingHTTPServer(("127.0.0.1",0),handler); self.th=threading.Thread(target=self.server.serve_forever,daemon=True);self.th.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.th.join(2);self.store.close();self.tmp.cleanup()
    def req(self,method,path,body=None,token=None,headers=None):
        c=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5);h={"Accept":"application/json"}
        if body is not None:
            raw=json.dumps(body,separators=(",",":")).encode();h["Content-Type"]="application/json";h["Content-Length"]=str(len(raw))
        else: raw=None
        if token:h["Authorization"]="Bearer "+token
        if headers:h.update(headers)
        c.request(method,path,body=raw,headers=h);r=c.getresponse();data=r.read();hdr=dict(r.getheaders());c.close();return r.status,data,hdr
    def test_browser_root_and_customer_operator_boundary(self):
        s,raw,h=self.req("GET","/");self.assertEqual(s,200);self.assertIn(b"Warranty &amp; RMA",raw);self.assertEqual(h.get("Cache-Control"),"no-store")
        body={"idempotency_key":"h1","sku":"P1","purchase_ref":"O","purchase_date":"2026-09-01","issue":"Synthetic"}
        s,raw,_=self.req("POST","/api/customer/cases",body);self.assertEqual(s,201);doc=json.loads(raw);cid=doc["case"]["case_id"];tok=doc["status_token"]
        s,raw,_=self.req("GET","/api/customer/cases/"+cid,token=tok);self.assertEqual(s,200)
        s,raw,_=self.req("GET","/api/operator/cases");self.assertEqual(s,403)
        s,raw,_=self.req("GET","/api/operator/cases",token="operator-secret-123456");self.assertEqual(s,200)
    def test_http_rejects_transfer_encoding_and_invalid_token(self):
        # Raw handler contract via direct request with both TE and content length.
        c=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        c.putrequest("POST","/api/customer/cases");c.putheader("Transfer-Encoding","chunked");c.putheader("Content-Length","2");c.endheaders();c.send(b"{}")
        r=c.getresponse();self.assertEqual(r.status,400);doc=json.loads(r.read());self.assertEqual(doc["error"],"TRANSFER_ENCODING_UNSUPPORTED");c.close()
        s,raw,_=self.req("GET","/api/customer/cases/NOPE",token="bad");self.assertIn(s,{401,403,404})

if __name__=="__main__":
    unittest.main()
