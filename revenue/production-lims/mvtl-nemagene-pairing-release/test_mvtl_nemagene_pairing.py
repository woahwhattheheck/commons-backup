import copy, json, tempfile, unittest
from pathlib import Path
import mvtl_nemagene_pairing as m

class MvtlTests(unittest.TestCase):
    def setUp(self): self.records,self.manifest=m.load_fixture()
    def test_exact_counts(self):
        s=m.MvtlNemageneShadow(); r=s.replay(self.records,self.manifest)
        self.assertEqual((400,100,250),(r.valid,r.hold,r.fertility_scn))
        self.assertEqual({c:25 for c in m.HOLD_CODES},r.hold_counts)
        self.assertEqual((400,250,400,100,500),(r.accessions_added,r.scn_jobs_added,r.reports_added,r.holds_added,r.events_added))
    def test_scn_binding_no_orphans_duplicates(self):
        s=m.MvtlNemageneShadow(); s.replay(self.records,self.manifest)
        self.assertEqual(250,len(s.scn_jobs)); self.assertEqual(250,len({j['scn_result_id'] for j in s.scn_jobs.values()}))
        for oid,j in s.scn_jobs.items():
            self.assertEqual(s.accessions[oid]['sample_id'],j['scn_sample_id']); self.assertEqual(s.accessions[oid]['fertility_accession'],j['fertility_accession'])
    def test_sla_two_business_days(self):
        for r in self.records[:400]: self.assertEqual(m._plus_business_days(r['signed_receipt_date']),r['sla_due_date'])
    def test_holds_create_no_work(self):
        s=m.MvtlNemageneShadow(); s.replay(self.records,self.manifest)
        self.assertEqual(100,len(s.holds))
        for oid,h in s.holds.items(): self.assertNotIn(oid,s.accessions); self.assertNotIn(oid,s.scn_jobs); self.assertNotIn(oid,s.reports); self.assertEqual((0,0),(h['jobs_created'],h['report_created']))
    def test_combined_digest_lineage(self):
        s=m.MvtlNemageneShadow(); s.replay(self.records,self.manifest)
        for oid,r in s.reports.items():
            if oid in s.scn_jobs: self.assertIsNotNone(r['scn_lineage_sha256']); self.assertEqual(s.scn_jobs[oid]['scn_result_digest'],r['scn_result_digest'])
            else: self.assertIsNone(r['scn_lineage_sha256']); self.assertIsNone(r['scn_result_digest'])
            core=dict(r); got=core.pop('combined_result_digest'); self.assertEqual(m._sha(m._canon(core)),got)
    def test_replay_zero_add(self):
        s=m.MvtlNemageneShadow(); a=s.replay(self.records,self.manifest); b=s.replay(self.records,self.manifest)
        self.assertEqual(500,b.replayed); self.assertEqual((0,0,0,0,0),(b.accessions_added,b.scn_jobs_added,b.reports_added,b.holds_added,b.events_added)); self.assertEqual(a.state_digest,b.state_digest); self.assertEqual(a.combined_manifest_sha256,b.combined_manifest_sha256)
    def test_read_only_snapshot(self):
        auth={'lims':{'rows':12},'mode':'read-only'}; before=copy.deepcopy(auth); s=m.MvtlNemageneShadow(auth); fp=s.authoritative_fingerprint; s.replay(self.records,self.manifest); self.assertEqual(before,auth); self.assertEqual(fp,s.authoritative_fingerprint)
    def test_human_release_copy_only(self):
        s=m.MvtlNemageneShadow(); s.replay(self.records,self.manifest); oid=next(iter(s.reports)); before=copy.deepcopy(s.reports[oid])
        for bad in ('','auto','system','bot','Jordan','System Reviewer','Bot Operator','Automation Service','Jordan System'):
            with self.assertRaises(PermissionError): s.release_report(oid,bad)
            self.assertEqual(before,s.reports[oid])
        out=s.release_report(oid,'Jordan Reviewer'); self.assertEqual('RELEASED_BY_NAMED_HUMAN',out['state']); self.assertFalse(out['sent']); self.assertEqual(before,s.reports[oid])
        with self.assertRaises(PermissionError): s.automatic_release(oid)
    def test_tamper_fail_closed(self):
        base=Path(m.__file__).resolve().parent; fixture=base/'fixtures'/'mvtl_500_soil_orders.json'; manifest=base/'fixtures'/'manifest.json'; mm=json.loads(manifest.read_text())
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); bad=td/'f.json'; bad.write_text(fixture.read_text().replace('"valid_count":400','"valid_count":399'))
            with self.assertRaises(m.IntegrityError): m.load_fixture(bad,manifest)
            mm['expected_valid']=399; bm=td/'m.json'; bm.write_text(json.dumps(mm,sort_keys=True))
            with self.assertRaises(m.IntegrityError): m.load_fixture(fixture,bm)
    def test_cli_summary(self):
        r=m.run_acceptance(); self.assertEqual((400,100,250),(r['valid'],r['hold'],r['fertility_scn'])); self.assertEqual((400,250,400),(r['accessions'],r['scn_jobs'],r['reports'])); self.assertTrue(r['replay_zero_add']); self.assertFalse(r['sent'])

if __name__=='__main__': unittest.main()
