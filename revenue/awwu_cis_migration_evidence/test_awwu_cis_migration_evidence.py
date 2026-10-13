import copy
import pathlib
import tempfile
import unittest
from revenue.awwu_cis_migration_evidence import compiler as c
HERE = pathlib.Path(__file__).resolve().parent

def sample(): return c.load_json(HERE / 'sample_input.json')
def at(text='2026-09-14T02:00:00Z'): return c.parse_time(text, 'test')

class ContractTests(unittest.TestCase):
    def test_all_pass_self_asserted_packet_still_holds(self):
        r=c.compile_receipt(sample(),trusted_as_of=at()); self.assertEqual(r['state'],'HOLD'); self.assertEqual(r['evidence_state'],c.EVIDENCE_CONSISTENT); self.assertEqual(r['metrics']['verified_required_interface_count'],2); self.assertTrue(set(c.INDEPENDENT_AUTHORITY_BLOCKERS).issubset(r['blockers'])); self.assertTrue(all(v is False for v in r['authority'].values()))
    def test_deadline_closed(self):
        r=c.compile_receipt(sample(),trusted_as_of=at('2026-10-02T00:00:00Z')); self.assertEqual(r['state'],'HOLD'); self.assertIn('DEADLINE_CLOSED',r['blockers'])
    def test_source_future(self):
        p=sample(); p['opportunity']['source']['observed_at']='2026-09-15T00:00:00Z'; self.assertIn('SOURCE_OBSERVED_IN_FUTURE',c.compile_receipt(p,trusted_as_of=at())['blockers'])
    def test_source_stale(self):
        p=sample(); p['opportunity']['source']['observed_at']='2026-01-01T00:00:00Z'; self.assertIn('SOURCE_STALE',c.compile_receipt(p,trusted_as_of=at())['blockers'])
    def test_bad_hash_rejected(self):
        p=sample(); p['opportunity']['source']['source_sha256']='nope'; self.assertRaises(c.ContractError,c.compile_receipt,p,trusted_as_of=at())
    def test_unknown_key_rejected(self):
        p=sample(); p['surprise']=1; self.assertRaises(c.ContractError,c.compile_receipt,p,trusted_as_of=at())
    def test_authority_escalation_refused(self):
        p=sample(); p['authority']['external_send_authorized']=True; r=c.compile_receipt(p,trusted_as_of=at()); self.assertIn('AUTHORITY_ESCALATION_REFUSED',r['blockers']); self.assertFalse(r['authority']['external_send_authorized'])
    def test_workshare_must_remain_proposed(self):
        p=sample(); p['workshare']['status']='ACCEPTED'; self.assertRaises(c.ContractError,c.compile_receipt,p,trusted_as_of=at())
    def test_zero_price_rejected(self):
        p=sample(); p['workshare']['amount_cents']=0; self.assertRaises(c.ContractError,c.compile_receipt,p,trusted_as_of=at())
    def test_duplicate_deliverable_rejected(self):
        p=sample(); p['workshare']['deliverables']=['same','same']; self.assertRaises(c.ContractError,c.compile_receipt,p,trusted_as_of=at())
    def test_row_mismatch_holds(self):
        p=sample(); p['migration']['datasets'][0]['target_rows']-=1; r=c.compile_receipt(p,trusted_as_of=at()); self.assertIn('MIGRATION_RECONCILIATION_FAILED',r['blockers']); self.assertIn('customer_accounts:ROW_COUNT',r['migration_failures'])
    def test_key_mismatch_holds(self):
        p=sample(); p['migration']['datasets'][0]['target_key_digest']='0'*64; self.assertIn('customer_accounts:KEY_SET',c.compile_receipt(p,trusted_as_of=at())['migration_failures'])
    def test_control_total_mismatch_holds(self):
        p=sample(); p['migration']['datasets'][1]['target_control_total_microunits']+=1; self.assertIn('open_balances:CONTROL_TOTAL',c.compile_receipt(p,trusted_as_of=at())['migration_failures'])
    def test_row_anomalies_hold(self):
        for key,suffix in [('duplicate_key_count','DUPLICATE_KEYS'),('missing_key_count','MISSING_KEYS'),('unexpected_key_count','UNEXPECTED_KEYS'),('rejected_row_count','REJECTED_ROWS')]:
            with self.subTest(key=key):
                p=sample(); p['migration']['datasets'][0][key]=1; self.assertIn('customer_accounts:'+suffix,c.compile_receipt(p,trusted_as_of=at())['migration_failures'])
    def test_duplicate_dataset_id_rejected(self):
        p=sample(); p['migration']['datasets'].append(copy.deepcopy(p['migration']['datasets'][0])); self.assertRaises(c.ContractError,c.compile_receipt,p,trusted_as_of=at())
    def test_missing_required_interface_holds(self):
        p=sample(); p['interfaces']=p['interfaces'][:1]; self.assertIn('payment_posting:MISSING_INTERFACE',c.compile_receipt(p,trusted_as_of=at())['interface_failures'])
    def test_interface_failure_holds(self):
        p=sample(); p['interfaces'][0]['retry_idempotency_status']='FAIL'; self.assertIn('meter_reads:retry_idempotency_status',c.compile_receipt(p,trusted_as_of=at())['interface_failures'])
    def test_duplicate_interface_id_rejected(self):
        p=sample(); p['interfaces'].append(copy.deepcopy(p['interfaces'][0])); self.assertRaises(c.ContractError,c.compile_receipt,p,trusted_as_of=at())
    def test_cutover_failure_holds(self):
        p=sample(); p['cutover']['restart_test_status']='MISSING'; r=c.compile_receipt(p,trusted_as_of=at()); self.assertIn('CUTOVER_EVIDENCE_INCOMPLETE',r['blockers']); self.assertIn('restart_test_status',r['cutover_failures'])
    def test_receipt_tamper_rejected(self):
        p=sample(); r=c.compile_receipt(p,trusted_as_of=at()); r['metrics']['target_rows']+=1; self.assertRaises(c.ContractError,c.verify_receipt,p,r,trusted_as_of=at())
    def test_receipt_transplant_rejected(self):
        p=sample(); r=c.compile_receipt(p,trusted_as_of=at()); p2=sample(); p2['opportunity']['opportunity_id']='OTHER'; self.assertRaises(c.ContractError,c.verify_receipt,p2,r,trusted_as_of=at())
    def test_historical_hold_current_deadline_hold(self):
        p=sample(); r=c.compile_receipt(p,trusted_as_of=at()); v=c.verify_receipt(p,r,trusted_as_of=at('2026-10-02T00:00:00Z')); self.assertEqual(v['historical_state'],'HOLD'); self.assertEqual(v['current_state'],'HOLD'); self.assertIn('DEADLINE_CLOSED',v['current_blockers']); self.assertTrue(set(c.INDEPENDENT_AUTHORITY_BLOCKERS).issubset(v['current_blockers']))
    def test_render_authority_boundary(self):
        p=sample(); r=c.compile_receipt(p,trusted_as_of=at()); md=c.render_markdown(p,r); self.assertIn('PROPOSED_NOT_ACCEPTED',md); self.assertIn('Candidate packet bytes cannot authorize READY',md); self.assertIn('Independent authority challenge',md)
    def test_authority_challenge_binds_declared_universe(self):
        p=sample(); a=c.build_authority_challenge(p); p2=sample(); p2['migration']['required_interface_ids']=['meter_reads']; b=c.build_authority_challenge(p2); self.assertNotEqual(a['requirements_binding_sha256'],b['requirements_binding_sha256']); self.assertNotEqual(a['challenge_sha256'],b['challenge_sha256'])
    def test_fake_independent_root_field_is_rejected(self):
        p=sample(); p['independent_authority']={'source_root':'0'*64}; self.assertRaises(c.ContractError,c.compile_receipt,p,trusted_as_of=at())
    def test_fabricated_pass_hashes_cannot_clear_authority_hold(self):
        p=sample(); p['interfaces'][0]['test_receipt_sha256']='1'*64; r=c.compile_receipt(p,trusted_as_of=at()); self.assertEqual(r['state'],'HOLD'); self.assertIn('INDEPENDENT_EVIDENCE_AUTHORITY_REQUIRED',r['blockers'])
    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/'x.json'; path.write_text('{"schema":"x","schema":"y"}'); self.assertRaises(c.ContractError,c.load_json,path)
    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/'x.json'; path.write_text('{"x":NaN}'); self.assertRaises(c.ContractError,c.load_json,path)
    def test_write_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td)/'receipt.json'; c.write_exclusive(out,b'first'); self.assertRaises(FileExistsError,c.write_exclusive,out,b'second')
    def test_verification_never_authorizes_external_action(self):
        p=sample(); r=c.compile_receipt(p,trusted_as_of=at()); v=c.verify_receipt(p,r,trusted_as_of=at()); self.assertTrue(v['historical_receipt_valid']); self.assertFalse(v['external_action_authorized'])

if __name__=='__main__': unittest.main()
