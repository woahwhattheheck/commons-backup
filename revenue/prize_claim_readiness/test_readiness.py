import copy, json, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
import readiness
NOW=datetime(2026,9,17,4,30,tzinfo=timezone.utc)
def H(c): return c*64
def base():
    return {'schema':readiness.INPUT_SCHEMA,'opportunity_id':'test-prize','synthetic_fixture':True,
      'source':{'source_type':'FIXTURE_DERIVED','source_url':'https://example.org/rules','source_sha256':H('a'),'capture_receipt_sha256':H('b'),'captured_at':'2026-09-16T04:30:00Z','source_complete':True,'currency':'USD','advertised_amount_minor':100000,'deadline_utc':'2026-10-01T23:59:00Z','deliverable_kind':'PUBLISHED_PROOF','deliverable_requirement':'Published proof accepted by sponsor.'},
      'work':{'carrier_repo':'woahwhattheheck/commons','carrier_ref':'main','carrier_sha256':H('c'),'result_level':'PARTIAL','independent_review':'PASS','evidence_sha256':[H('d')]},
      'entry':{'account_required':False,'registration_required':False,'registration_evidence_sha256':'NONE','submission_required':True,'submission_evidence_sha256':'NONE','submitted_at':'NONE','submission_route':'Sponsor route.'},
      'award':{'award_evidence_sha256':'NONE','amount_minor':0,'currency':'USD','provider_ref':'NONE'},
      'payment':{'payment_evidence_sha256':'NONE','amount_minor':0,'currency':'USD','provider_ref':'NONE'},
      'ownership':{'owner_key':'z-test','duplicate_state':'UNIQUE'}}
class T(unittest.TestCase):
    def c(self,d): return readiness.compile_readiness(d,trusted_now=NOW)
    def test_ladder(self):
        d=base(); self.assertEqual(self.c(d)['state'],'RESEARCH_IN_PROGRESS')
        d['work']['result_level']='QUALIFYING'; d['work']['independent_review']='UNKNOWN'; self.assertEqual(self.c(d)['state'],'QUALIFYING_RESULT_REVIEW_REQUIRED')
        d['work']['independent_review']='PASS'; self.assertEqual(self.c(d)['state'],'OWNER_SUBMISSION_REQUIRED')
        d['entry']['submission_evidence_sha256']=H('e'); d['entry']['submitted_at']='2026-09-17T04:00:00Z'; self.assertEqual(self.c(d)['state'],'SUBMITTED_AWAITING_DECISION')
        d['award']={'award_evidence_sha256':H('f'),'amount_minor':100000,'currency':'USD','provider_ref':'award-1'}; self.assertEqual(self.c(d)['state'],'AWARDED_UNPAID')
        d['payment']={'payment_evidence_sha256':H('1'),'amount_minor':100000,'currency':'USD','provider_ref':'settlement-1'}; p=self.c(d); self.assertEqual(p['state'],'PAID'); self.assertTrue(p['authority']['can_claim_paid']); self.assertFalse(p['authority']['payout_request_authorized'])
    def test_deadline_and_source_holds(self):
        d=base(); d['source']['deadline_utc']='2026-09-15T23:59:00Z'; self.assertEqual(self.c(d)['state'],'EXPIRED_NOT_SUBMITTED')
        d=base(); d['source']['source_complete']=False; self.assertEqual(self.c(d)['state'],'HOLD_SOURCE_INCOMPLETE')
        d=base(); d['ownership']['duplicate_state']='CONFLICT'; self.assertEqual(self.c(d)['state'],'HOLD_OWNERSHIP_CONFLICT')
    def test_review_red(self):
        d=base(); d['work']['independent_review']='RED'; self.assertEqual(self.c(d)['state'],'HOLD_REVIEW_RED')
    def test_provider_chronology(self):
        d=base(); d['award']={'award_evidence_sha256':H('f'),'amount_minor':100000,'currency':'USD','provider_ref':'award'}
        with self.assertRaises(readiness.ReadinessError): self.c(d)
        d=base(); d['payment']={'payment_evidence_sha256':H('1'),'amount_minor':1,'currency':'USD','provider_ref':'pay'}
        with self.assertRaises(readiness.ReadinessError): self.c(d)
    def test_disjoint_roots(self):
        d=base(); d['work']['evidence_sha256']=[H('b')]
        with self.assertRaises(readiness.ReadinessError): self.c(d)
    def test_verify_recompiles(self):
        d=base(); p=self.c(d); self.assertTrue(readiness.verify_readiness(d,p,trusted_now=NOW))
        forged=copy.deepcopy(p); forged['state']='PAID'; forged['reasons']=['forged']; u=dict(forged); u.pop('receipt_sha256'); forged['receipt_sha256']=readiness.sha256_hex(readiness.canonical_json(u)); self.assertFalse(readiness.verify_readiness(d,forged,trusted_now=NOW))
    def test_duplicate_and_nonfinite(self):
        with self.assertRaises(readiness.ReadinessError): readiness.strict_loads('{"a":1,"a":2}')
        with self.assertRaises(readiness.ReadinessError): readiness.strict_loads('{"a":NaN}')
    def test_production_first_party(self):
        d=base(); d['synthetic_fixture']=False
        with self.assertRaises(readiness.ReadinessError): self.c(d)
    def test_fixtures(self):
        expected={'ridgway_rigorous_partial.json':'RESEARCH_IN_PROGRESS','learn2design_built_not_submitted.json':'OWNER_SUBMISSION_REQUIRED','cuhkx_expired_unsubmitted.json':'EXPIRED_NOT_SUBMITTED','settled_paid_unit.json':'PAID'}
        for name,state in expected.items():
            with self.subTest(name=name): self.assertEqual(self.c(readiness.strict_load(Path('fixtures')/name))['state'],state)
    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            i=Path(td)/'i.json'; o=Path(td)/'o.json'; i.write_text(json.dumps(base())); o.write_text('existing')
            self.assertEqual(readiness.main(['compile',str(i),str(o)]),2); self.assertEqual(o.read_text(),'existing')
if __name__=='__main__': unittest.main()
