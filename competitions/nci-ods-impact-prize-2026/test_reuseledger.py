import copy,hashlib,json,tempfile,unittest
from pathlib import Path
import reuseledger as r
def fixture():return {'schema':r.MANIFEST_SCHEMA,'project':'Synthetic reuse graph','outputs':[{'id':'https://doi.org/10.5281/zenodo.1234567','kind':'dataset','title':'Synthetic data','access':'open','landing_url':'https://example.org/data','license':'CC-BY-4.0','data_use':'Synthetic only.','fixity':{'sha256':'a'*64,'bytes':12},'depends_on':[]},{'id':'https://github.com/example/code/tree/0123456789abcdef0123456789abcdef01234567','kind':'software','title':'Synthetic code','access':'open','landing_url':'https://github.com/example/code','license':'Apache-2.0','data_use':'No patient data.','fixity':{'sha256':'b'*64,'bytes':34},'depends_on':['https://doi.org/10.5281/zenodo.1234567']},{'id':'https://doi.org/10.1000/example-paper','kind':'publication','title':'Synthetic paper','access':'open','landing_url':'https://example.org/paper','license':'CC-BY-4.0','data_use':'Public article.','fixity':None,'depends_on':['https://github.com/example/code/tree/0123456789abcdef0123456789abcdef01234567']}]}
def packet(m=None):m=fixture() if m is None else m;raw=(json.dumps(m,sort_keys=True)+'\n').encode();return r.compile_packet(m,hashlib.sha256(raw).hexdigest()),raw
class T(unittest.TestCase):
 def test_clean(self):p,_=packet();self.assertEqual(p['summary']['reuse_readiness_score'],100);self.assertEqual(r.verify_packet(p),(True,'ok'))
 def test_order(self):a=fixture();b=copy.deepcopy(a);b['outputs'].reverse();self.assertEqual(r.compile_packet(a,'1'*64),r.compile_packet(b,'1'*64))
 def test_duplicate(self):m=fixture();m['outputs'].append(copy.deepcopy(m['outputs'][0]));self.assertRaisesRegex(r.LedgerError,'duplicate id',r.compile_packet,m,'1'*64)
 def test_missing_dep(self):m=fixture();m['outputs'][0]['depends_on']=['https://example.org/missing'];self.assertRaisesRegex(r.LedgerError,'unknown dependency',r.compile_packet,m,'1'*64)
 def test_cycle(self):m=fixture();m['outputs'][0]['depends_on']=[m['outputs'][2]['id']];self.assertRaisesRegex(r.LedgerError,'dependency cycle',r.compile_packet,m,'1'*64)
 def test_https(self):m=fixture();m['outputs'][0]['landing_url']='http://x';self.assertRaisesRegex(r.LedgerError,'HTTPS required',r.compile_packet,m,'1'*64)
 def test_bool(self):m=fixture();m['outputs'][0]['fixity']['bytes']=True;self.assertRaisesRegex(r.LedgerError,'non-negative integer',r.compile_packet,m,'1'*64)
 def test_extra(self):m=fixture();m['outputs'][0]['x']=1;self.assertRaisesRegex(r.LedgerError,'key mismatch',r.compile_packet,m,'1'*64)
 def test_data_use(self):m=fixture();m['outputs'][0]['access']='controlled';m['outputs'][0]['data_use']=None;p=r.compile_packet(m,'1'*64);self.assertIn('MISSING_DATA_USE',{x['code'] for x in p['findings']})
 def test_license(self):m=fixture();m['outputs'][0]['license']=None;p=r.compile_packet(m,'1'*64);self.assertEqual(p['summary']['reuse_readiness_score'],80)
 def test_fixity(self):m=fixture();m['outputs'][0]['fixity']=None;p=r.compile_packet(m,'1'*64);self.assertIn('MISSING_FIXITY',{x['code'] for x in p['findings']})
 def test_reseal(self):p,_=packet();p['summary']['reuse_readiness_score']=99;u=dict(p);u.pop('semantic_sha256');p['semantic_sha256']=r.sha(r.canon(u));ok,why=r.verify_packet(p);self.assertFalse(ok);self.assertIn('derivation mismatch',why)
 def test_exact_bytes(self):p,raw=packet();ok,why=r.verify_manifest(p,fixture(),raw+b' ');self.assertFalse(ok);self.assertIn('exact supplied manifest bytes',why)
 def test_dup_key(self):
  with tempfile.TemporaryDirectory() as td:
   f=Path(td)/'x';f.write_text('{"x":1,"x":2}');self.assertRaisesRegex(r.LedgerError,'duplicate JSON key',r.load_json,f)
 def test_cli(self):
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);m=td/'m';p=td/'p';q=td/'q';m.write_text(json.dumps(fixture())+'\n');self.assertEqual(r.main(['compile',str(m),'--out',str(p)]),0);self.assertEqual(r.main(['verify',str(p),'--manifest',str(m)]),0);self.assertEqual(r.main(['report',str(p),'--out',str(q)]),0);self.assertIn('100/100',q.read_text())
if __name__=='__main__':unittest.main()
