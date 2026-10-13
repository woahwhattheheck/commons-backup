import json,unittest
from .engine import FilingQualityError,compile_packet,outputs,verify_outputs
from .test_support import b,src,pol
class CheckTests(unittest.TestCase):
    def test_check_fail(self):
        s=src();s['facts']['us-gaap']['StockholdersEquity']['units']['USD'][0]['val']=39;self.assertIn('CHECK_FAIL',[f['code'] for f in compile_packet(b(s),b(pol()))['findings']])
    def test_incompatible(self):
        p=pol();p['checks'][0]['lhs']=['liabilities','revenue'];self.assertIn('CHECK_INCOMPATIBLE',[f['code'] for f in compile_packet(b(src()),b(p))['findings']])
    def test_negative_tolerance(self):
        p=pol();p['checks'][0]['tolerance']=-1
        with self.assertRaises(FilingQualityError):compile_packet(b(src()),b(p))
    def test_tamper(self):
        s,p=b(src()),b(pol());o=outputs(s,p);verify_outputs(s,p,o);o['report.html']+=b'x'
        with self.assertRaises(FilingQualityError):verify_outputs(s,p,o)
    def test_html_escape(self):self.assertNotIn(b'<QA>',outputs(b(src()),b(pol()))['report.html'])
    def test_semantic_sha(self):self.assertEqual(len(compile_packet(b(src()),b(pol()))['semantic_sha256']),64)
    def test_key_order_semantics(self):
        s=src();p=pol();a=compile_packet(b(s),b(p));bb=compile_packet(json.dumps(s).encode(),json.dumps(p).encode())
        for k in ('source_sha256','policy_sha256','semantic_sha256'):a.pop(k);bb.pop(k)
        self.assertEqual(a,bb)
