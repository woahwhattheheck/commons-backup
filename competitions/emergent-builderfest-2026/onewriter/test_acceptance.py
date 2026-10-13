#!/usr/bin/env python3
from __future__ import annotations
import copy, hashlib, importlib.util, json, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
A=HERE/"acceptance.py"; M=HERE/"state_machine.json"; E=HERE/"demo_events.json"
spec=importlib.util.spec_from_file_location("onewriter_acceptance",A)
if spec is None or spec.loader is None: raise RuntimeError("could not load acceptance")
a=importlib.util.module_from_spec(spec); sys.modules[spec.name]=a; spec.loader.exec_module(a)

class OneWriterTests(unittest.TestCase):
    def setUp(self): self.m=a.load_json(M); self.d=a.load_json(E)
    def replay(self,d=None): return a.replay(copy.deepcopy(self.m),copy.deepcopy(d or self.d))
    def evaluate(self,d=None): return a.evaluate(copy.deepcopy(self.m),copy.deepcopy(d or self.d))
    def receipts(self,d=None): return {r["event_id"]:r for r in self.replay(d)["receipts"]}
    def eval_receipts(self,d=None): return {r["event_id"]:r for r in self.evaluate(d)["receipts"]}
    def test_baseline(self):
        s=self.replay()["summary"]; self.assertEqual((s["status"],s["event_count"],s["lane_count"]),("OK",14,3)); self.assertEqual(s["metrics"]["duplicate_touches_prevented"],4)
    def test_cross_route_parallel_claim_collides(self):
        r=self.receipts(); self.assertNotEqual(r["evt-001"]["event_route"],r["evt-002"]["event_route"]); self.assertEqual(r["evt-001"]["decision"],"GRANTED"); self.assertEqual(r["evt-002"]["decision"],"DENIED_ACTIVE_LEASE"); self.assertEqual(r["evt-001"]["collision_key"],r["evt-002"]["collision_key"])
    def test_sent_fence_and_human_reopen_can_select_new_route(self):
        r=self.receipts(); self.assertEqual(r["evt-003"]["state"],"HARD_DNR"); self.assertEqual(r["evt-004"]["decision"],"DENIED_HARD_DNR"); self.assertEqual(r["evt-005"]["decision"],"REOPENED_HUMAN_EVENT"); self.assertEqual(r["evt-006"]["decision"],"GRANTED_AFTER_HUMAN_EVENT"); self.assertNotEqual(r["evt-003"]["lane_route"],r["evt-006"]["lane_route"])
    def test_human_reopen_expired_lease_refences_instead_of_stale_recovering(self):
        d=copy.deepcopy(self.d); d["events"][5]["lease_seconds"]=30
        probe=copy.deepcopy(d["events"][3]); probe.update({"id":"evt-006b","actor":"agent-after-expiry","at_utc":"2026-09-17T12:02:50Z","route":"email:another@northstar.invalid","reason":"attempt stale recovery after the one human-authorized lease expired","expect":{"decision":"DENIED_HARD_DNR","state":"HARD_DNR"}})
        d["events"].insert(6,probe); r=self.eval_receipts(d)["evt-006b"]
        self.assertEqual((r["prior_state"],r["decision"],r["state"]),("HARD_DNR","DENIED_HARD_DNR","HARD_DNR")); self.assertTrue(r["reopen_expiry_refenced"]); self.assertEqual(r["lane_route"],"email:ops@northstar.invalid")
    def test_provider_outcome_must_match_leased_route(self):
        d=copy.deepcopy(self.d); d["events"][2]["route"]="email:founder@northstar.invalid"
        with self.assertRaisesRegex(a.ContractError,"does not match current leased route"): a.replay(self.m,d)
    def test_equivalent_domain_variants_share_key(self):
        e1=copy.deepcopy(self.d["events"][0]); e2=copy.deepcopy(e1); e2["domain"]="HTTPS://WWW.NORTHSTAR.INVALID./ignored/path?x=1"
        self.assertEqual(a.collision_key(e1),a.collision_key(e2))
    def test_stale_recovery_and_dead_route(self):
        r=self.receipts(); self.assertEqual(r["evt-008"]["decision"],"GRANTED_STALE_RECOVERY"); self.assertEqual(r["evt-009"]["state"],"DEAD_ROUTE"); self.assertEqual(r["evt-010"]["decision"],"DENIED_DEAD_ROUTE")
    def test_hold(self):
        r=self.receipts(); self.assertEqual(r["evt-012"]["decision"],"DENIED_HOLD"); self.assertEqual(r["evt-013"]["decision"],"REOPENED_HUMAN_EVENT")
    def test_all_receipts_deny_external_authority(self): self.assertTrue(all(x["external_send_authorized"] is False for x in self.replay()["receipts"]))
    def test_receipt_binds_complete_accepted_event(self):
        base=self.eval_receipts(); d=copy.deepcopy(self.d); d["events"][2]["provider_receipt"]="provider-sent-replacement"; changed=self.eval_receipts(d)
        self.assertNotEqual(base["evt-003"]["receipt_sha256"],changed["evt-003"]["receipt_sha256"]); self.assertNotEqual(base["evt-003"]["accepted_event_sha256"],changed["evt-003"]["accepted_event_sha256"]); self.assertEqual(changed["evt-003"]["accepted_event"]["provider_receipt"],"provider-sent-replacement")
        q=copy.deepcopy(self.d); q["events"][0]["lease_seconds"]=301; q["events"][0]["reason"]="different admitted reason"; qchanged=self.eval_receipts(q)
        self.assertNotEqual(base["evt-001"]["receipt_sha256"],qchanged["evt-001"]["receipt_sha256"])
    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x"; p.write_text('{"x":1,"x":2}')
            with self.assertRaisesRegex(a.ContractError,"duplicate JSON key"): a.load_json(p)
    def test_nonfinite(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x"; p.write_text('{"x":NaN}')
            with self.assertRaisesRegex(a.ContractError,"non-finite"): a.load_json(p)
    def test_machine_remint(self):
        m=copy.deepcopy(self.m); m["lease"]["max_ttl_seconds"]=86400; m["contract_digest_sha256"]=hashlib.sha256(a.canonical_bytes(a.machine_semantic(m))).hexdigest()
        with self.assertRaisesRegex(a.ContractError,"lease policy changed|semantic digest"): a.validate_machine(m)
    def test_authority_escalation(self):
        m=copy.deepcopy(self.m); m["authority"]["email_send_authorized"]=True
        with self.assertRaisesRegex(a.ContractError,"all-false"): a.validate_machine(m)
    def test_duplicate_event(self):
        d=copy.deepcopy(self.d); d["events"][2]["id"]=d["events"][1]["id"]
        with self.assertRaisesRegex(a.ContractError,"workspace identifier reused"): a.replay(self.m,d)
    def test_reused_provider_receipt(self):
        d=copy.deepcopy(self.d); d["events"][8]["provider_receipt"]=d["events"][2]["provider_receipt"]
        with self.assertRaisesRegex(a.ContractError,"workspace identifier reused"): a.replay(self.m,d)
    def test_reused_human_evidence(self):
        d=copy.deepcopy(self.d); d["events"][12]["human_evidence_id"]=d["events"][4]["human_evidence_id"]
        with self.assertRaisesRegex(a.ContractError,"workspace identifier reused"): a.replay(self.m,d)
    def test_provider_evidence_cannot_be_reused_as_human_evidence(self):
        d=copy.deepcopy(self.d); d["events"][4]["human_evidence_id"]=d["events"][2]["provider_receipt"]
        with self.assertRaisesRegex(a.ContractError,"workspace identifier reused"): a.evaluate(self.m,d)
    def test_human_evidence_cannot_be_reused_as_provider_evidence(self):
        d=copy.deepcopy(self.d); d["events"][8]["provider_receipt"]=d["events"][4]["human_evidence_id"]
        with self.assertRaisesRegex(a.ContractError,"workspace identifier reused"): a.evaluate(self.m,d)
    def test_event_id_cannot_reuse_evidence_id(self):
        d=copy.deepcopy(self.d); d["events"][3]["id"]=d["events"][2]["provider_receipt"]
        with self.assertRaisesRegex(a.ContractError,"workspace identifier reused"): a.evaluate(self.m,d)
    def test_nonmonotone_time(self):
        d=copy.deepcopy(self.d); d["events"][1]["at_utc"]=d["events"][0]["at_utc"]
        with self.assertRaisesRegex(a.ContractError,"strictly monotone"): a.replay(self.m,d)
    def test_nonholder_sent(self):
        d=copy.deepcopy(self.d); d["events"][2]["actor"]="agent-beta"
        with self.assertRaisesRegex(a.ContractError,"not current lease holder"): a.replay(self.m,d)
    def test_expired_holder(self):
        d=copy.deepcopy(self.d); d["events"][2]["at_utc"]="2026-09-17T12:05:01Z"
        for i,e in enumerate(d["events"][3:],start=3): e["at_utc"]=f"2026-09-17T12:{6+i:02d}:00Z"
        with self.assertRaisesRegex(a.ContractError,"lease expired"): a.replay(self.m,d)
    def test_bool_lease(self):
        d=copy.deepcopy(self.d); d["events"][0]["lease_seconds"]=True
        with self.assertRaisesRegex(a.ContractError,"bool forbidden|CLAIM lease"): a.replay(self.m,d)
    def test_extra_event_authority_field(self):
        d=copy.deepcopy(self.d); d["events"][0]["send_authorized"]=True
        with self.assertRaisesRegex(a.ContractError,"key set changed"): a.replay(self.m,d)
    def test_domain_credentials_and_ports_rejected(self):
        for domain in ("https://user@example.invalid","example.invalid:443"):
            d=copy.deepcopy(self.d); d["events"][0]["domain"]=domain
            with self.subTest(domain=domain), self.assertRaisesRegex(a.ContractError,"credentials forbidden|port forbidden"): a.replay(self.m,d)
    def test_whitespace_provider_evidence_rejected(self):
        for index in (2,8):
            d=copy.deepcopy(self.d); d["events"][index]["provider_receipt"]="   "
            with self.subTest(event=d["events"][index]["kind"]), self.assertRaisesRegex(a.ContractError,"provider_receipt must be trimmed nonempty"): a.replay(self.m,d)
    def test_whitespace_human_evidence_cannot_reopen(self):
        d=copy.deepcopy(self.d); d["events"][4]["human_evidence_id"]="   "
        with self.assertRaisesRegex(a.ContractError,"human_evidence_id must be trimmed nonempty"): a.replay(self.m,d)
    def test_padded_overlong_and_control_evidence_rejected(self):
        cases=((2,"provider_receipt"," padded"),(2,"provider_receipt","x"*241),(4,"human_evidence_id","human\nthread"))
        for index,field,value in cases:
            d=copy.deepcopy(self.d); d["events"][index][field]=value
            with self.subTest(field=field,value=repr(value)), self.assertRaisesRegex(a.ContractError,"trimmed nonempty|control characters"): a.replay(self.m,d)
    def test_invisible_unicode_evidence_rejected(self):
        cases=((4,"human_evidence_id","\u200b","non-visible Unicode"),(4,"human_evidence_id","human-thread-001\u034f","Default_Ignorable"),(2,"provider_receipt","provider-sent-001\ufe0f","Default_Ignorable"),(8,"provider_receipt","provider-bounce-001\u115f","Default_Ignorable"),(4,"human_evidence_id","\u0301","visible base"))
        for index,field,value,pattern in cases:
            d=copy.deepcopy(self.d); d["events"][index][field]=value
            with self.subTest(field=field,value=value.encode("unicode_escape")), self.assertRaisesRegex(a.ContractError,pattern): a.replay(self.m,d)
    def test_event_ids_use_same_strict_unicode_admission(self):
        cases=(("\u200b","non-visible Unicode"),("evt-001\u034f","Default_Ignorable"),("evt-001\ufe0f","Default_Ignorable"),("evt-001\u115f","Default_Ignorable"),("\u0301","visible base"),(" padded-event","trimmed nonempty"))
        for value,pattern in cases:
            d=copy.deepcopy(self.d); d["events"][0]["id"]=value
            with self.subTest(value=value.encode("unicode_escape")), self.assertRaisesRegex(a.ContractError,pattern): a.evaluate(self.m,d)
    def test_visible_combining_unicode_evidence_remains_admitted(self):
        value="provider-cafe\u0301-001"; self.assertEqual(a.evidence_id(value,"provider_receipt"),value); self.assertEqual(a.evidence_id("evt-cafe\u0301-001","event id"),"evt-cafe\u0301-001")
    def test_real_cli_normal_and_optimized(self):
        for optimized in (False,True):
            cmd=[sys.executable]+(["-O"] if optimized else [])+[str(A),"replay",str(M),str(E)]; run=subprocess.run(cmd,cwd=HERE,text=True,capture_output=True,check=False)
            with self.subTest(optimized=optimized): self.assertEqual(run.returncode,0,run.stderr); self.assertEqual(json.loads(run.stdout)["receipt_chain_sha256"],self.d["expected_summary"]["receipt_chain_sha256"])
    def test_hostile_cli_normal_and_optimized(self):
        d=copy.deepcopy(self.d); d["events"][0]["send_authorized"]=True
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"h.json"; p.write_text(json.dumps(d))
            for optimized in (False,True):
                cmd=[sys.executable]+(["-O"] if optimized else [])+[str(A),"replay",str(M),str(p)]; run=subprocess.run(cmd,cwd=HERE,text=True,capture_output=True,check=False)
                with self.subTest(optimized=optimized): self.assertEqual(run.returncode,2); self.assertIn("key set changed",run.stderr)
if __name__=="__main__": unittest.main()