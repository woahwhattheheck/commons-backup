from __future__ import annotations
import copy, hashlib, json, unittest
from unittest.mock import patch
from revenue.initial_outreach_slot import slot

ACTOR="Z-PASCALESTUARY-2210-S4Q8"
OP="INITIAL-OUTREACH-ONE-SHOT-ZPE-S4Q8-20260913"
ANCHOR="a"*40
CAP="11"*32
KEY="opp.04254.retained"
KEY_OTHER="opp.09999.retained"

def opportunity(**kw):
    x={"schema":"commercial-opportunity-custody/v1","repo":"woahwhattheheck/commons","buyer_scope":"buyer.example","authority_scope":"rfp.example","opportunity_id":"rfp-04254"}; x.update(kw); return x

def lease(offer="validation-5000", buyer="buyer.example", claimant=ACTOR, repo="woahwhattheheck/commons"):
    seam=hashlib.sha256(json.dumps({"schema":"outbound-send-lease/v2","buyer_scope":buyer,"offer_scope":offer},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    x={"schema":"outbound-send-lease-receipt/v2","repo":repo,"buyer_scope":buyer,"offer_scope":offer,"seam_sha256":seam,"lease_ref":f"refs/tags/outbound-lease-v2/{seam}","claim_id":"rfp-04254-first-contact","claimant":claimant,"claim_started_at":"2026-09-14T02:20:00Z","anchor_sha":ANCHOR,"preflight_sha256":"2"*64,"claim_capability_sha256":hashlib.sha256(bytes.fromhex(CAP)).hexdigest(),"tag_object_sha":"b"*40,"observed_ref_sha":"b"*40,"lease_held_by_claimant":True,"decision":"LEASE_HELD","reason":"ACQUIRED_CREATE_201","external_send_authorized":False}
    x["receipt_sha256"]=hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest(); return x

def custody(opp, generation=3, history="3"*64, check="4"*64, basis="WHOLE"):
    i=slot.coc.Identity.parse(opp)
    return {"schema":"commercial-opportunity-custody-work-check/v1","seam_sha256":i.seam_sha256,"generation":generation,"history_sha256":history,"actor_owner":ACTOR,"actor_operation":OP,"lane":"outreach","internal_work_authorized":True,"basis":basis,"external_send_authorized":False,"proposal_submission_authorized":False,"payment_or_revenue_inferred":False,"check_sha256":check}

def resolved(key=KEY):
    return {"state":"RESOLVED","canonical_opportunity_key":key,"external_action_authorized":False,"provider_mutation_authorized":False,"buyer_contact_authorized":False,"payment_or_revenue_inferred":False}

def unresolved(_obs=None):
    return {"state":"UNRESOLVED_ALIAS","canonical_opportunity_key":None,"external_action_authorized":False,"provider_mutation_authorized":False,"buyer_contact_authorized":False,"payment_or_revenue_inferred":False}

class FakeGit:
    def __init__(self): self.refs={}; self.tags={}; self.ref_status=None; self.create_despite=False; self.pre_status=None; self.calls=[]
    def __call__(self, method,path,body):
        self.calls.append((method,path,copy.deepcopy(body)))
        if method=="POST" and path.endswith("/git/tags"):
            sha=hashlib.sha1((json.dumps(body,sort_keys=True)+str(len(self.tags))).encode()).hexdigest()
            self.tags[sha]={"sha":sha,"tag":body["tag"],"message":body["message"],"object":{"sha":body["object"],"type":"commit"},"tagger":dict(body["tagger"])}; return 201,{"sha":sha}
        if method=="POST" and path.endswith("/git/refs"):
            ref,sha=body["ref"],body["sha"]
            if ref in self.refs: return 422,{"message":"exists"}
            if self.ref_status is not None:
                if self.create_despite: self.refs[ref]=sha
                return self.ref_status, None
            self.refs[ref]=sha; return 201,{"object":{"sha":sha}}
        if method=="GET" and "/git/ref/" in path:
            if self.pre_status is not None and not self.refs:
                s=self.pre_status; self.pre_status=None; return s,None
            ref="refs/"+path.split("/git/ref/",1)[1]
            return (200,{"object":{"sha":self.refs[ref]}}) if ref in self.refs else (404,None)
        if method=="GET" and "/git/tags/" in path:
            sha=path.rsplit("/",1)[-1]; return (200,copy.deepcopy(self.tags[sha])) if sha in self.tags else (404,None)
        raise AssertionError((method,path,body))

class BoomRepr:
    def __init__(self): self.repr_calls=[]
    def __repr__(self):
        self.repr_calls.append("repr")
        raise AssertionError("repr must never run on callback return")
    def __str__(self):
        self.repr_calls.append("str")
        raise AssertionError("str must never run on callback return")

class Tests(unittest.TestCase):
    def run_one(self, git=None, opp=None, lr=None, checks=None, possess=True, sender=None, key=KEY, resolve=None):
        git=git or FakeGit(); opp=opp or opportunity(); lr=lr or lease(); c=custody(opp); checks=checks or [c,c,c]
        sent=[]
        if sender is None: sender=lambda: sent.append("sent") or {"provider":"opaque"}
        if resolve is None: resolve=lambda obs: resolved(key)
        with patch.object(slot.alias_v1,"resolve_current",side_effect=resolve), patch.object(slot.coc,"authorize_internal_work",side_effect=checks), patch.object(slot.lease_v2,"verify_receipt",return_value=True), patch.object(slot.lease_v2,"verify_possession",return_value=possess):
            r=slot.execute_initial_outreach(opp,actor_owner=ACTOR,actor_operation=OP,lease_receipt=lr,claim_capability=CAP,transport=git,send_once=sender)
        return r,git,sent

    def inspect(self, opp, git, key=KEY):
        with patch.object(slot.alias_v1,"resolve_current",return_value=resolved(key)):
            return slot.inspect_initial_outreach(opp,transport=git)

    def test_happy_path_invokes_callback_once_and_never_emits_send_authority(self):
        r,g,s=self.run_one(); self.assertEqual("PROVIDER_CALLBACK_RETURNED",r["decision"]); self.assertEqual(["sent"],s); self.assertTrue(r["slot_consumed"]); self.assertTrue(r["provider_callback_invoked"]); self.assertFalse(r["external_send_authorized"]); self.assertFalse(r["provider_send_completed"]); self.assertNotIn("provider_callback_return_sha256",r); self.assertEqual(r["canonical_opportunity_key"],KEY); self.assertTrue(slot.verify_receipt(r)); self.assertNotIn(CAP,next(iter(g.tags.values()))["message"])

    def test_same_holder_replay_never_invokes_second_callback(self):
        g=FakeGit(); r1,_,s1=self.run_one(git=g); r2,_,s2=self.run_one(git=g); self.assertEqual(["sent"],s1); self.assertEqual([],s2); self.assertEqual("HOLD_ALREADY_CONSUMED",r2["reason"]); self.assertFalse(r2["provider_callback_invoked"])

    def test_price_offer_aliases_race_same_opportunity_slot(self):
        g=FakeGit(); a,_,s1=self.run_one(git=g,lr=lease("validation-5000")); b,_,s2=self.run_one(git=g,lr=lease("validation-7500")); self.assertEqual(["sent"],s1); self.assertEqual([],s2); self.assertEqual(a["slot_ref"],b["slot_ref"]); self.assertEqual("HOLD_ALREADY_CONSUMED",b["reason"])

    def test_slot_seam_is_domain_separated_from_custody_and_ignores_identity_aliases(self):
        i=slot.coc.Identity.parse(opportunity()); seam=slot._slot_seam(i,KEY)
        self.assertNotEqual(i.seam_sha256,seam)
        self.assertEqual(slot.coc._sha256({"schema":slot.SCHEMA,"action":slot.ACTION,"repo":i.repo,"buyer_scope":i.buyer_scope,"canonical_opportunity_key":KEY}),seam)
        alias=slot.coc.Identity.parse(opportunity(opportunity_id="lacsd-04254"))
        self.assertEqual(seam, slot._slot_seam(alias,KEY))
        portal=slot.coc.Identity.parse(opportunity(authority_scope="portal.example"))
        self.assertEqual(seam, slot._slot_seam(portal,KEY))

    def test_wrong_capability_never_touches_slot_or_callback(self):
        r,g,s=self.run_one(possess=False); self.assertEqual([],s); self.assertTrue(r["reason"].startswith("HOLD_LEASE")); self.assertFalse(any(m=="POST" for m,_,_ in g.calls))

    def test_buyer_mismatch_holds(self):
        r,_,s=self.run_one(lr=lease(buyer="other.example")); self.assertEqual([],s); self.assertTrue(r["reason"].startswith("HOLD_LEASE"))

    def test_repo_mismatch_holds(self):
        r,_,s=self.run_one(lr=lease(repo="other/repo")); self.assertEqual([],s); self.assertTrue(r["reason"].startswith("HOLD_LEASE"))

    def test_claimant_mismatch_holds(self):
        r,_,s=self.run_one(lr=lease(claimant="Z-OTHER-WORKER")); self.assertEqual([],s); self.assertTrue(r["reason"].startswith("HOLD_LEASE"))

    def test_custody_change_before_consume_no_callback(self):
        o=opportunity(); c1=custody(o); c2=custody(o,4,"5"*64,"6"*64); r,g,s=self.run_one(opp=o,checks=[c1,c2]); self.assertEqual([],s); self.assertEqual("HOLD_CUSTODY_CHANGED_BEFORE_CONSUME",r["reason"]); self.assertFalse(any(m=="POST" and p.endswith("/git/refs") for m,p,_ in g.calls))

    def test_custody_change_after_consume_burns_slot_without_callback(self):
        o=opportunity(); c1=custody(o); c3=custody(o,4,"5"*64,"6"*64); r,g,s=self.run_one(opp=o,checks=[c1,c1,c3]); self.assertEqual([],s); self.assertTrue(r["slot_consumed"]); self.assertEqual("HOLD_CUSTODY_CHANGED_AFTER_CONSUME",r["reason"]); again,_,s2=self.run_one(git=g,opp=o); self.assertEqual([],s2); self.assertEqual("HOLD_ALREADY_CONSUMED",again["reason"])

    def test_concurrent_existing_slot_no_callback(self):
        g=FakeGit(); i=slot.coc.Identity.parse(opportunity()); g.refs[slot._slot_ref(i,KEY)]="d"*40; r,_,s=self.run_one(git=g); self.assertEqual([],s); self.assertEqual("HOLD_ALREADY_CONSUMED",r["reason"])

    def test_indeterminate_create_self_readback_invokes_once(self):
        g=FakeGit(); g.ref_status=503; g.create_despite=True; r,_,s=self.run_one(git=g); self.assertEqual(["sent"],s); self.assertEqual("PROVIDER_CALLBACK_RETURNED",r["decision"]); self.assertIn("READBACK_SELF_503",r["reason"])

    def test_indeterminate_unproven_never_invokes(self):
        g=FakeGit(); g.ref_status=503; r,_,s=self.run_one(git=g); self.assertEqual([],s); self.assertEqual("HOLD",r["decision"]); self.assertIn("OUTCOME_UNPROVEN",r["reason"])

    def test_preflight_provider_uncertainty_never_invokes(self):
        g=FakeGit(); g.pre_status=503; r,_,s=self.run_one(git=g); self.assertEqual([],s); self.assertEqual("HOLD_SLOT_PREFLIGHT_READ_503",r["reason"])

    def test_callback_exception_burns_slot_and_no_retry(self):
        g=FakeGit(); calls=[]
        def boom(): calls.append(1); raise RuntimeError("ambiguous")
        r,_,_=self.run_one(git=g,sender=boom); self.assertEqual([1],calls); self.assertEqual("SEND_OUTCOME_UNKNOWN",r["decision"]); self.assertTrue(r["slot_consumed"]); again,_,s2=self.run_one(git=g); self.assertEqual([],s2); self.assertEqual("HOLD_ALREADY_CONSUMED",again["reason"])

    def test_repr_hook_on_callback_return_never_executes(self):
        boom=BoomRepr(); hooks=[]
        def sender():
            hooks.append("sent")
            return boom
        r,_,_=self.run_one(sender=sender)
        self.assertEqual(["sent"],hooks)
        self.assertEqual([],boom.repr_calls)
        self.assertEqual("PROVIDER_CALLBACK_RETURNED",r["decision"])
        self.assertNotIn("provider_callback_return_sha256",r)
        self.assertNotIn("BoomRepr",json.dumps(r))
        self.assertFalse(r["external_send_authorized"])
        self.assertTrue(slot.verify_receipt(r))

    def test_internal_double_send_does_not_mint_send_authority(self):
        effects=[]
        def sender():
            effects.append("one"); effects.append("two")
            return {"batch": True}
        r,_,_=self.run_one(sender=sender)
        self.assertEqual(["one","two"],effects)
        self.assertEqual("PROVIDER_CALLBACK_RETURNED",r["decision"])
        self.assertIs(r["external_send_authorized"], False)
        self.assertIs(r["provider_send_completed"], False)
        self.assertIs(r["replay_or_retry_authorized"], False)
        self.assertTrue(slot.verify_receipt(r))

    def test_callback_return_material_is_discarded(self):
        secret={"message_id":"private-123"}
        r,_,_=self.run_one(sender=lambda:secret)
        blob=json.dumps(r)
        self.assertNotIn("private-123",blob)
        self.assertNotIn("provider_callback_return_sha256",r)
        self.assertNotIn("message_id",blob)

    def test_durable_tag_never_contains_send_authority_or_raw_capability(self):
        r,g,_=self.run_one(); m=json.loads(next(iter(g.tags.values()))["message"]); self.assertIs(m["external_send_authorized"],False); self.assertEqual(m["canonical_opportunity_key"],KEY); self.assertNotIn(CAP,json.dumps(m)); self.assertFalse(r["external_send_authorized"])

    def test_inspection_consumed_is_read_only(self):
        r,g,_=self.run_one(); x=self.inspect(opportunity(),g); self.assertEqual("CONSUMED",x["decision"]); self.assertTrue(x["evidence_valid"]); self.assertFalse(x["external_send_authorized"])

    def test_inspection_unconsumed_is_read_only(self):
        x=self.inspect(opportunity(),FakeGit()); self.assertEqual("UNCONSUMED",x["decision"]); self.assertFalse(x["external_send_authorized"])

    def test_inspection_tamper_fails_closed(self):
        _,g,_=self.run_one(); _,b=next(iter(g.tags.items())); d=json.loads(b["message"]); d["lease_offer_scope"]="tampered"; b["message"]=slot.coc.canon_json(d).decode()+"\n"; x=self.inspect(opportunity(),g); self.assertEqual("HOLD",x["decision"]); self.assertFalse(x["evidence_valid"])

    def test_inspection_duplicate_key_fails_closed(self):
        _,g,_=self.run_one(); _,b=next(iter(g.tags.items())); raw=b["message"].strip(); b["message"]=raw[:-1]+',"schema":"initial-outreach-slot/v1"}'; x=self.inspect(opportunity(),g); self.assertEqual("HOLD",x["decision"]); self.assertFalse(x["evidence_valid"])

    def test_receipt_tamper_rejected(self):
        r,_,_=self.run_one(); r["provider_callback_invoked"]=False
        with self.assertRaises(slot.SlotError): slot.verify_receipt(r)

    def test_opportunity_identity_rejects_price_alias_field(self):
        with self.assertRaises(slot.coc.CustodyError): self.run_one(opp=opportunity(price=5000))

    def test_opportunity_id_aliases_same_canonical_key_collide(self):
        g=FakeGit()
        a,_,s1=self.run_one(git=g,opp=opportunity(opportunity_id="rfp-04254"),key=KEY)
        b,_,s2=self.run_one(git=g,opp=opportunity(opportunity_id="lacsd-04254"),key=KEY)
        self.assertEqual(["sent"],s1); self.assertEqual([],s2)
        self.assertEqual(a["slot_ref"],b["slot_ref"])
        self.assertEqual("HOLD_ALREADY_CONSUMED",b["reason"])
        self.assertFalse(b["provider_callback_invoked"])

    def test_authority_scope_aliases_same_canonical_key_collide(self):
        g=FakeGit()
        a,_,s1=self.run_one(git=g,opp=opportunity(authority_scope="buyer.example"),key=KEY)
        b,_,s2=self.run_one(git=g,opp=opportunity(authority_scope="portal.example"),key=KEY)
        self.assertEqual(["sent"],s1); self.assertEqual([],s2)
        self.assertEqual(a["slot_ref"],b["slot_ref"])
        self.assertEqual("HOLD_ALREADY_CONSUMED",b["reason"])

    def test_distinct_canonical_keys_same_buyer_stay_independent(self):
        g=FakeGit()
        def resolve(obs):
            oid=next(a["value"] for a in obs["aliases"] if a["type"]=="official_id")
            return resolved(KEY if oid=="rfp-04254" else KEY_OTHER)
        a,_,s1=self.run_one(git=g,opp=opportunity(opportunity_id="rfp-04254"),resolve=resolve)
        b,_,s2=self.run_one(git=g,opp=opportunity(opportunity_id="rfp-09999"),resolve=resolve)
        self.assertEqual(["sent"],s1); self.assertEqual(["sent"],s2)
        self.assertNotEqual(a["slot_ref"],b["slot_ref"])
        self.assertEqual("PROVIDER_CALLBACK_RETURNED",b["decision"])

    def test_unresolved_canonical_key_fails_closed(self):
        r,g,s=self.run_one(resolve=lambda obs: unresolved())
        self.assertEqual([],s)
        self.assertTrue(r["reason"].startswith("HOLD_UNRESOLVED_ALIAS"))
        self.assertIsNone(r["canonical_opportunity_key"])
        self.assertIsNone(r["slot_ref"])
        self.assertFalse(r["slot_consumed"])
        self.assertFalse(r["external_send_authorized"])
        self.assertFalse(any(m=="POST" for m,_,_ in g.calls))

    def test_empty_live_registry_fails_closed(self):
        git=FakeGit(); opp=opportunity(); lr=lease(); sent=[]
        with patch.object(slot.coc,"authorize_internal_work",return_value=custody(opp)), patch.object(slot.lease_v2,"verify_receipt",return_value=True), patch.object(slot.lease_v2,"verify_possession",return_value=True):
            r=slot.execute_initial_outreach(opp,actor_owner=ACTOR,actor_operation=OP,lease_receipt=lr,claim_capability=CAP,transport=git,send_once=lambda: sent.append("sent"))
        self.assertEqual([],sent)
        self.assertTrue(r["reason"].startswith("HOLD_UNRESOLVED_ALIAS"))
        self.assertFalse(any(m=="POST" for m,_,_ in git.calls))

    def test_self_authored_alias_mapping_cannot_fuse_or_split(self):
        git=FakeGit(); opp=opportunity(); lr=lease(); sent=[]
        mapping={"rfp-04254":KEY,"lacsd-04254":KEY}
        with patch.object(slot.alias_v1,"resolve_current",return_value=resolved(KEY)), patch.object(slot.coc,"authorize_internal_work",return_value=custody(opp)), patch.object(slot.lease_v2,"verify_receipt",return_value=True), patch.object(slot.lease_v2,"verify_possession",return_value=True):
            with self.assertRaises(TypeError):
                slot.execute_initial_outreach(opp,canonical_opportunity_key=KEY,actor_owner=ACTOR,actor_operation=OP,lease_receipt=lr,claim_capability=CAP,transport=git,send_once=lambda: sent.append("sent"))
            with self.assertRaises(TypeError):
                slot.execute_initial_outreach(opp,alias_map=mapping,actor_owner=ACTOR,actor_operation=OP,lease_receipt=lr,claim_capability=CAP,transport=git,send_once=lambda: sent.append("sent"))
        def resolve(obs):
            oid=next(a["value"] for a in obs["aliases"] if a["type"]=="official_id")
            return resolved("alias.one" if oid=="rfp-04254" else "alias.two")
        a,_,s1=self.run_one(git=git,opp=opportunity(opportunity_id="rfp-04254"),resolve=resolve)
        b,_,s2=self.run_one(git=git,opp=opportunity(opportunity_id="lacsd-04254"),resolve=resolve)
        self.assertEqual(["sent"],s1); self.assertEqual(["sent"],s2)
        self.assertNotEqual(a["slot_ref"],b["slot_ref"])
        self.assertEqual([],sent)

    def test_observation_uses_official_id_and_authority_url(self):
        i=slot.coc.Identity.parse(opportunity())
        obs=slot._observation(i)
        self.assertEqual(obs["buyer_organization_key"],"buyer.example")
        kinds={a["type"]:a["value"] for a in obs["aliases"]}
        self.assertEqual(kinds["official_id"],"rfp-04254")
        self.assertEqual(kinds["authority_url"],"https://rfp.example/")

if __name__=="__main__": unittest.main()
