from __future__ import annotations
from copy import deepcopy
import hashlib, json, subprocess, sys, tempfile, unittest
from pathlib import Path
from revenue.oss_grant_eligibility_packet.compiler import GrantPacketError, REFERENCE_GENERATION_MAX_AGE_SECONDS, canon, compile_packet, digest, load, verify
ROOT=Path(__file__).resolve().parents[2]; PROGRAMS=Path(__file__).resolve().parent/'reference_programs.json'; FIXTURE=Path(__file__).resolve().parent/'fixtures'/'synthetic_project.json'
def docs(): return load(PROGRAMS.read_bytes(),'refs'), load(FIXTURE.read_bytes(),'input')
def bind(refs,doc): doc['reference_programs_sha256']=digest(canon(refs)); doc['route_map_git_blob_sha1']=refs['route_map']['git_blob_sha1']; return canon(refs),canon(doc)
def compile_docs(refs,doc): return compile_packet(*bind(refs,doc))
def packet_obj(outputs): return load(outputs[0],'packet')
def evidence(eid,key,value,sha='c'*64,at='2026-09-17T01:30:00Z'): return {'evidence_id':eid,'key':key,'value':value,'source_ref':'fixture://'+eid,'source_sha256':sha,'observed_at':at,'authority':'PROJECT_OWNER'}
def refresh_factsets(refs):
    for p in refs['programs']: p['source_factset_sha256']=digest(canon(p['source_facts']))
def retime_project(doc, at):
    for row in doc['project']['evidence']: row['observed_at']=at

def program_doc(pid):
    refs,doc=docs(); doc['program_id']=pid; doc['project']['evidence']=[]; return refs,doc
class GrantTests(unittest.TestCase):
    def test_complete_github_mechanical_packet_ready_with_selectors_held(self):
        refs,doc=docs(); p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'PACKET_READY'); selectors=[g for g in p['gates'] if g['scope']=='SELECTOR']; self.assertTrue(selectors); self.assertTrue(all(g['status']=='HOLD' for g in selectors)); self.assertTrue(p['selector_holds_do_not_imply_ineligibility']); self.assertTrue(all(v is False for v in p['authority'].values())); self.assertTrue(p['program']['currentness']['current']); self.assertEqual(p['program']['currentness']['policy_max_age_seconds'],REFERENCE_GENERATION_MAX_AGE_SECONDS)
    def test_missing_mechanical_fact_requires_owner(self):
        refs,doc=docs(); doc['project']['evidence']=[x for x in doc['project']['evidence'] if x['key']!='clear_governance']; p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'OWNER_FACTS_REQUIRED'); self.assertIn('gh-governance',{x['rule_id'] for x in p['owner_fact_gaps']})
    def test_false_mechanical_fact_holds(self):
        refs,doc=docs(); next(x for x in doc['project']['evidence'] if x['key']=='clear_open_source_license')['value']=False; p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_SOURCE_CONFLICT')
    def test_contradictory_evidence_holds(self):
        refs,doc=docs(); doc['project']['evidence'].append(evidence('e-license-conflict','clear_open_source_license',False)); p=packet_obj(compile_docs(refs,doc)); row=next(g for g in p['gates'] if g['rule_id']=='gh-license'); self.assertEqual(row['reason'],'PROJECT_EVIDENCE_CONTRADICTORY'); self.assertEqual(p['status'],'HOLD_SOURCE_CONFLICT')
    def test_stale_evidence_holds(self):
        refs,doc=docs(); doc['project_evidence_max_age_seconds']=60; next(x for x in doc['project']['evidence'] if x['key']=='clear_open_source_license')['observed_at']='2026-09-17T00:00:00Z'; p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_SOURCE_CONFLICT')
    def test_future_evidence_holds(self):
        refs,doc=docs(); next(x for x in doc['project']['evidence'] if x['key']=='clear_open_source_license')['observed_at']='2026-09-17T02:00:00Z'; p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_SOURCE_CONFLICT')
    def test_stale_reference_bundle_holds_even_with_fresh_project_evidence(self):
        refs,doc=docs(); doc['evaluated_at']='2026-09-25T01:45:01Z'; retime_project(doc,'2026-09-25T01:45:00Z'); p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_PROGRAM_CURRENTNESS'); self.assertEqual(p['program']['currentness']['reason'],'REFERENCE_GENERATION_STALE'); self.assertFalse(p['program']['currentness']['current']); self.assertGreater(p['program']['currentness']['reference_age_seconds'],REFERENCE_GENERATION_MAX_AGE_SECONDS)
    def test_stale_selected_program_holds_even_when_bundle_generation_is_fresh(self):
        refs,doc=docs(); doc['evaluated_at']='2026-09-25T01:45:00Z'; refs['generated_at']='2026-09-25T01:45:00Z'; retime_project(doc,'2026-09-25T01:44:59Z'); selected=next(x for x in refs['programs'] if x['program_id']==doc['program_id']); selected['observed_at']='2026-09-17T01:45:00Z'; p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_PROGRAM_CURRENTNESS'); self.assertEqual(p['program']['currentness']['reason'],'REFERENCE_GENERATION_STALE'); self.assertGreater(p['program']['currentness']['program_age_seconds'],REFERENCE_GENERATION_MAX_AGE_SECONDS)
    def test_future_reference_generation_holds(self):
        refs,doc=docs(); refs['generated_at']='2026-09-17T01:46:00Z'; p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_PROGRAM_CURRENTNESS'); self.assertEqual(p['program']['currentness']['reason'],'REFERENCE_GENERATION_FUTURE'); self.assertLess(p['program']['currentness']['reference_age_seconds'],0)
    def test_future_selected_program_observation_holds(self):
        refs,doc=docs(); selected=next(x for x in refs['programs'] if x['program_id']==doc['program_id']); selected['observed_at']='2026-09-17T01:46:00Z'; p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_PROGRAM_CURRENTNESS'); self.assertEqual(p['program']['currentness']['reason'],'REFERENCE_GENERATION_FUTURE'); self.assertLess(p['program']['currentness']['program_age_seconds'],0)
    def test_subjective_self_assertion_never_verifies_selector(self):
        refs,doc=docs(); doc['project']['evidence'].append(evidence('e-fit','security_impact_fit',True)); p=packet_obj(compile_docs(refs,doc)); row=next(g for g in p['gates'] if g['rule_id']=='gh-security-impact'); self.assertEqual(row['status'],'HOLD'); self.assertEqual(row['reason'],'SUBJECTIVE_REVIEW_REQUIRED')
    def test_otf_foss_not_accepting_precedence(self):
        refs,doc=program_doc('otf-foss-sustainability'); p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_PROGRAM_CURRENTNESS'); self.assertEqual(p['program']['program_state'],'NOT_ACCEPTING')
    def test_otf_surge_source_conflict_precedence(self):
        refs,doc=program_doc('otf-surge-sustain'); p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_PROGRAM_CURRENTNESS'); self.assertTrue(p['program']['source_conflicts'])
    def test_nlnet_owner_authored_only_emits_no_outline_prompts(self):
        refs,doc=program_doc('nlnet-open-internet-stack'); p=packet_obj(compile_docs(refs,doc)); self.assertFalse(p['draft_application_outline']['allowed']); self.assertEqual(p['draft_application_outline']['prompts'],[]); self.assertIn('OWNER MUST AUTHOR',p['draft_application_outline']['owner_instruction'])
    def test_stf_cost_must_exceed_50000(self):
        refs,doc=program_doc('sovereign-tech-fund'); doc['project']['evidence']=[evidence('cost','project_cost_eur',50000)]; p=packet_obj(compile_docs(refs,doc)); row=next(g for g in p['gates'] if g['rule_id']=='stf-cost'); self.assertEqual(row['status'],'HOLD')
    def test_iff_advertised_range_is_mechanical_reference_not_award(self):
        refs,doc=program_doc('otf-internet-freedom'); doc['project']['evidence']=[evidence('request','requested_usd',50000),evidence('duration','duration_months',12),evidence('sanction','applicant_in_restricted_or_sanctioned_country',False),evidence('budget','budget_artifact_available',True)]; p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'PACKET_READY'); self.assertEqual(p['program']['reference_value']['truth'],'REFERENCE_ONLY_NOT_AWARD'); self.assertFalse(p['authority']['selection_or_award_claim_authorized'])
    def test_reference_value_never_sets_award_or_payment_authority(self):
        refs,doc=docs(); p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['program']['reference_value']['truth'],'REFERENCE_ONLY_NOT_AWARD'); self.assertFalse(p['authority']['selection_or_award_claim_authorized']); self.assertFalse(p['authority']['payment_or_cash_claim_authorized']); self.assertFalse(p['authority']['revenue_recognition_authorized'])
    def test_reference_factset_tamper_fails(self):
        refs,doc=docs(); refs['programs'][0]['source_facts'][0]+=' tamper';
        with self.assertRaisesRegex(GrantPacketError,'factset digest'): compile_docs(refs,doc)
    def test_reference_bytes_digest_mismatch_fails(self):
        refs,doc=docs(); doc['reference_programs_sha256']='0'*64
        with self.assertRaisesRegex(GrantPacketError,'reference program bytes'): compile_packet(canon(refs),canon(doc))
    def test_route_map_generation_mismatch_fails(self):
        refs,doc=docs(); doc['route_map_git_blob_sha1']='0'*40; doc['reference_programs_sha256']=digest(canon(refs))
        with self.assertRaisesRegex(GrantPacketError,'route-map generation'): compile_packet(canon(refs),canon(doc))
    def test_unknown_program_fails(self):
        refs,doc=docs(); doc['program_id']='unknown'
        with self.assertRaisesRegex(GrantPacketError,'unknown program'): compile_docs(refs,doc)
    def test_duplicate_key_float_and_bom_fail(self):
        with self.assertRaisesRegex(GrantPacketError,'duplicate JSON key'): load(b'{"a":1,"a":2}')
        with self.assertRaisesRegex(GrantPacketError,'non-integer'): load(b'{"a":1.5}')
        with self.assertRaisesRegex(GrantPacketError,'BOM'): load(b'\xef\xbb\xbf{}')
    def test_duplicate_evidence_id_fails(self):
        refs,doc=docs(); doc['project']['evidence'].append(deepcopy(doc['project']['evidence'][0]))
        with self.assertRaisesRegex(GrantPacketError,'duplicate evidence_id'): compile_docs(refs,doc)
    def test_unsupported_evidence_type_fails(self):
        refs,doc=docs(); doc['project']['evidence'][0]['value']={'bad':'object'}
        with self.assertRaisesRegex(GrantPacketError,'unsupported evidence value'): compile_docs(refs,doc)
    def test_verifier_rejects_tampering(self):
        refs,doc=docs(); rb,ib=bind(refs,doc); packet,md,receipt=compile_packet(rb,ib); verify(rb,ib,packet,md,receipt)
        for i in range(3):
            parts=[packet,md,receipt]; parts[i]+=b'x'
            with self.assertRaises(GrantPacketError): verify(rb,ib,*parts)
    def test_semantic_output_deterministic_but_receipt_binds_exact_input(self):
        refs,doc=docs(); first=compile_docs(refs,doc); other=deepcopy(doc); other['project']['evidence'].reverse(); second=compile_docs(refs,other); self.assertEqual(first[0],second[0]); self.assertEqual(first[1],second[1]); self.assertNotEqual(first[2],second[2])
    def test_program_source_conflict_precedes_missing_project_facts(self):
        refs,doc=program_doc('otf-surge-sustain'); p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['status'],'HOLD_PROGRAM_CURRENTNESS')
    def test_true_reference_authority_fails(self):
        refs,doc=docs(); refs['authority']['application_submission_authorized']=True; refresh_factsets(refs)
        with self.assertRaisesRegex(GrantPacketError,'hard-false'): compile_docs(refs,doc)
    def test_repository_retained_but_no_contact_authority(self):
        refs,doc=docs(); p=packet_obj(compile_docs(refs,doc)); self.assertEqual(p['project']['repository_url'],doc['project']['repository_url']); self.assertFalse(p['authority']['sponsor_contact_authorized']); self.assertFalse(p['authority']['email_or_dm_authorized'])
    def test_cli_compile_verify_and_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); refs,doc=docs(); rb,ib=bind(refs,doc); rp=root/'refs.json'; ip=root/'input.json'; rp.write_bytes(rb); ip.write_bytes(ib); out=root/'out'; cmd=[sys.executable,'-m','revenue.oss_grant_eligibility_packet','compile','--programs',str(rp),'--input',str(ip),'--out-dir',str(out)]; first=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True); self.assertEqual(first.returncode,0,first.stderr); check=subprocess.run([sys.executable,'-m','revenue.oss_grant_eligibility_packet','verify','--programs',str(rp),'--input',str(ip),'--packet',str(out/'packet.json'),'--markdown',str(out/'packet.md'),'--receipt',str(out/'receipt.json')],cwd=ROOT,capture_output=True,text=True); self.assertEqual(check.returncode,0,check.stderr); second=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True); self.assertEqual(second.returncode,2)
if __name__=='__main__': unittest.main()
