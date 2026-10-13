#!/usr/bin/env python3
from copy import deepcopy
import csv,hashlib,io,json,subprocess,sys,tempfile,threading,unittest,zipfile
from pathlib import Path
import campaign_desk as d
ROOT=Path(__file__).resolve().parent; SAMPLE=json.loads((ROOT/'sample_campaign.json').read_text())
class Tests(unittest.TestCase):
    def unzip(self,raw):
        with zipfile.ZipFile(io.BytesIO(raw)) as z: return {n:z.read(n) for n in z.namelist()}
    def test_exact_campaign_size(self): d.valid(SAMPLE); self.assertEqual((len(SAMPLE['creators']),sum(len(x['videos']) for x in SAMPLE['creators'])),(5,10))
    def test_deterministic_manifest(self):
        a=d.build_zip(SAMPLE); self.assertEqual(a,d.build_zip(deepcopy(SAMPLE))); f=self.unzip(a); m=json.loads(f['manifest.json']); self.assertEqual({x['path'] for x in m['files']},set(f)-{'manifest.json'}); [self.assertEqual(hashlib.sha256(f[x['path']]).hexdigest(),x['sha256']) for x in m['files']]
    def test_truth_boundary(self):
        p=json.loads(self.unzip(d.build_zip(SAMPLE))['campaign-packet.json']); self.assertEqual(p['counts'],{'creators':5,'videos':10}); self.assertEqual(p['truth_boundary'],{'fictional_demo':True,'creator_contacted':False,'samples_shipped':False,'usage_rights_granted':False,'customer_delivery_accepted':False,'cash_usd':0})
    def test_shipping_rows(self):
        r=list(csv.DictReader(io.StringIO(self.unzip(d.build_zip(SAMPLE))['shipping-plan.csv'].decode()))); self.assertEqual(len(r),5); self.assertEqual({x['shipping_state'] for x in r},{d.SHIP})
    def test_rights_rows(self):
        r=list(csv.DictReader(io.StringIO(self.unzip(d.build_zip(SAMPLE))['rights-disclosures.csv'].decode()))); self.assertEqual(len(r),10); self.assertEqual({x['usage_permission'] for x in r},{d.RIGHTS}); self.assertEqual({x['disclosure_required'] for x in r},{'YES'})
    def test_revision_tracker(self):
        r=list(csv.DictReader(io.StringIO(self.unzip(d.build_zip(SAMPLE))['delivery-tracker.csv'].decode()))); self.assertEqual(len(r),10); self.assertEqual({x['revision_count'] for x in r},{'0'}); self.assertEqual({x['revision_limit'] for x in r},{'2'}); self.assertEqual({x['revision_status'] for x in r},{'NOT_REQUESTED'})
    def test_five_briefs_two_videos_each(self):
        f=self.unzip(d.build_zip(SAMPLE)); self.assertEqual(len([x for x in f if x.startswith('creator-briefs/')]),5)
        for c in SAMPLE['creators']:
            s=f[f"creator-briefs/{c['id']}.md"].decode(); [self.assertIn(v['id'],s) for v in c['videos']]; self.assertIn('not a creator agreement',s)
    def test_duplicate_ids_rejected(self):
        bad=deepcopy(SAMPLE); bad['creators'][1]['id']=bad['creators'][0]['id']; self.assertRaises(d.CampaignError,d.valid,bad); bad=deepcopy(SAMPLE); bad['creators'][1]['videos'][0]['id']=bad['creators'][0]['videos'][0]['id']; self.assertRaises(d.CampaignError,d.valid,bad)
    def test_real_effect_states_rejected(self):
        bad=deepcopy(SAMPLE); bad['campaign']['sample']['shipping_state']='SHIPPED'; self.assertRaises(d.CampaignError,d.valid,bad); bad=deepcopy(SAMPLE); bad['creators'][0]['videos'][0]['usage_permission']='GRANTED'; self.assertRaises(d.CampaignError,d.valid,bad)
    def test_real_name_rejected(self):
        bad=deepcopy(SAMPLE); bad['creators'][0]['display_name']='Real Person'; self.assertRaises(d.CampaignError,d.valid,bad)
    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            o=Path(td)/'p.zip'; cmd=[sys.executable,'-B',str(ROOT/'campaign_desk.py'),str(ROOT/'sample_campaign.json'),str(o)]; a=subprocess.run(cmd,text=True,capture_output=True,timeout=10); self.assertEqual(a.returncode,0,a.stderr); rec=json.loads(a.stdout); self.assertEqual((rec['creators'],rec['videos']),(5,10)); raw=o.read_bytes(); b=subprocess.run(cmd,text=True,capture_output=True,timeout=10); self.assertEqual(b.returncode,1); self.assertIn('refusing to overwrite',b.stderr); self.assertEqual(o.read_bytes(),raw)
    def test_invalid_cli_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            i=Path(td)/'bad.json'; o=Path(td)/'x.zip'; i.write_text('{}'); r=subprocess.run([sys.executable,'-B',str(ROOT/'campaign_desk.py'),str(i),str(o)],text=True,capture_output=True,timeout=10); self.assertEqual(r.returncode,1); self.assertEqual(r.stdout,''); self.assertIn('UGC CAMPAIGN INVALID:',r.stderr); self.assertNotIn('Traceback',r.stderr); self.assertFalse(o.exists())
    def test_simultaneous_distinct_publishers_are_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            o=Path(td)/'race.zip'; a=deepcopy(SAMPLE); b=deepcopy(SAMPLE); a['campaign']['id']='fictional-race-alpha'; b['campaign']['id']='fictional-race-beta'; raws=[d.build_zip(a),d.build_zip(b)]; gate=threading.Barrier(2); results=[None,None]
            def run(i):
                gate.wait()
                try: d.publish_zip(o,raws[i]); results[i]='published'
                except d.CampaignError as e: results[i]=str(e)
            threads=[threading.Thread(target=run,args=(i,)) for i in range(2)]
            [x.start() for x in threads]; [x.join(10) for x in threads]; self.assertTrue(all(not x.is_alive() for x in threads)); self.assertEqual(results.count('published'),1); self.assertEqual(sum('refusing to overwrite' in str(x) for x in results),1); self.assertIn(o.read_bytes(),raws); self.unzip(o.read_bytes()); self.assertEqual(list(Path(td).glob('.race.zip.*.tmp')),[])
    def test_broken_output_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            o=Path(td)/'broken.zip'; target=Path(td)/'missing-target.zip'; o.symlink_to(target)
            with self.assertRaisesRegex(d.CampaignError,'refusing to overwrite'): d.publish_zip(o,d.build_zip(SAMPLE))
            self.assertTrue(o.is_symlink()); self.assertFalse(target.exists()); self.assertEqual(list(Path(td).glob('.broken.zip.*.tmp')),[])
if __name__=='__main__': unittest.main()
