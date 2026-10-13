from __future__ import annotations
import json,os,pathlib,subprocess,sys,tempfile,unittest
HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from revenue.opportunity_identity_alias import registry as g
from revenue.opportunity_identity_alias import strict as s

def oid(v): return {"type":"official_id","value":v}
def obs(): return {"schema":s.OBSERVATION_SCHEMA,"buyer_organization_key":"buyer-one","aliases":[oid("A")]}
def entry(k,b,a): return {"canonical_opportunity_key":k,"buyer_organization_key":b,"aliases":a}
def reg(e,n=1,p=None): return {"schema":s.REGISTRY_SCHEMA,"generation":n,"prior_registry_sha256":p,"entries":e}

class IoTests(unittest.TestCase):
    def test_cli_current_roundtrip_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            d=pathlib.Path(td); observation=d/"observation.json"; result=d/"result.json"; observation.write_text(json.dumps(obs())+"\n")
            env=dict(os.environ); env["PYTHONPATH"]=str(ROOT); cmd=[sys.executable,"-m","revenue.opportunity_identity_alias.cli"]
            proc=subprocess.run(cmd+["resolve-current",str(observation)],env=env,text=True,capture_output=True); self.assertEqual(proc.returncode,0,proc.stderr); result.write_text(proc.stdout)
            verify=subprocess.run(cmd+["verify-current",str(observation),str(result)],env=env,text=True,capture_output=True); self.assertEqual(verify.returncode,0,verify.stderr); self.assertIn('"verified":true',verify.stdout)
            if hasattr(os,"symlink"):
                link=d/"link.json"
                try: link.symlink_to(observation)
                except OSError: return
                refused=subprocess.run(cmd+["resolve-current",str(link)],env=env,text=True,capture_output=True); self.assertEqual(refused.returncode,2); self.assertIn("ordinary non-symlink",refused.stderr)
    def test_cli_transition(self):
        old=reg([entry("opp-one","buyer-one",[oid("A")])]); new=reg([entry("opp-one","buyer-one",[oid("A"),oid("B")])],2,g.registry_sha256(old))
        with tempfile.TemporaryDirectory() as td:
            d=pathlib.Path(td); a=d/"a.json"; b=d/"b.json"; a.write_text(json.dumps(old)); b.write_text(json.dumps(new)); env=dict(os.environ); env["PYTHONPATH"]=str(ROOT)
            p=subprocess.run([sys.executable,"-m","revenue.opportunity_identity_alias.cli","validate-transition",str(a),str(b)],env=env,text=True,capture_output=True); self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(json.loads(p.stdout)["generation"],2)

if __name__=="__main__": unittest.main()
