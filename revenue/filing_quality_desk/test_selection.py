import unittest
from .engine import FilingQualityError,compile_packet
from .test_support import b,src,pol
class SelectionTests(unittest.TestCase):
    def packet(self,**kw):return compile_packet(b(src(**kw)),b(pol()))
    def test_ready(self):
        p=self.packet();self.assertEqual(p['status'],'READY_FOR_ANALYST_QA');self.assertEqual({x['selector_id']:x['value'] for x in p['observations']}['revenue'],'25.5');self.assertEqual([f['code'] for f in p['findings']],['CHECK_PASS'])
    def test_history(self):self.assertIn('VALUE_CHANGED_PRIOR_FILING',[f['code'] for f in self.packet(changed=True)['findings']])
    def test_ambiguity(self):self.assertEqual(self.packet(amb=True)['status'],'HOLD')
    def test_cutoff(self):self.assertEqual(compile_packet(b(src()),b(pol('2026-07-01')))['status'],'HOLD')
    def test_cik(self):
        with self.assertRaises(FilingQualityError):compile_packet(b(src(cik='9')),b(pol()))
    def test_duplicate_key(self):
        with self.assertRaises(FilingQualityError):compile_packet(b'{"cik":"1","cik":"1","facts":{}}',b(pol()))
    def test_nonfinite(self):
        with self.assertRaises(FilingQualityError):compile_packet(b'{"cik":"123456","facts":{},"x":NaN}',b(pol()))
    def test_bool_hold(self):
        s=src();s['facts']['us-gaap']['Assets']['units']['USD'][0]['val']=True;self.assertEqual(compile_packet(b(s),b(pol()))['status'],'HOLD')
    def test_unknown_policy(self):
        p=pol();p['x']=1
        with self.assertRaises(FilingQualityError):compile_packet(b(src()),b(p))
    def test_duration_start(self):
        p=pol();del p['selectors'][3]['start']
        with self.assertRaises(FilingQualityError):compile_packet(b(src()),b(p))
    def test_instant_start(self):
        p=pol();p['selectors'][0]['start']='2026-01-01'
        with self.assertRaises(FilingQualityError):compile_packet(b(src()),b(p))
    def test_missing_fact(self):
        p=pol();p['selectors'][0]['concept']='Nope';self.assertEqual(compile_packet(b(src()),b(p))['status'],'HOLD')
