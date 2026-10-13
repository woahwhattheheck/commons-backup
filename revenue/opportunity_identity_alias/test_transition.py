from __future__ import annotations
import pathlib,sys,unittest
HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from revenue.opportunity_identity_alias import registry as g
from revenue.opportunity_identity_alias import strict as s

def reg(entries,generation=1,prior=None): return {"schema":s.REGISTRY_SCHEMA,"generation":generation,"prior_registry_sha256":prior,"entries":entries}
def entry(key,buyer,aliases): return {"canonical_opportunity_key":key,"buyer_organization_key":buyer,"aliases":aliases}
def oid(v): return {"type":"official_id","value":v}

class TransitionTests(unittest.TestCase):
    def test_add_alias_and_new_opportunity(self):
        old=reg([entry("opp-one","buyer-one",[oid("A")])]); new=reg([entry("opp-one","buyer-one",[oid("A"),oid("A-ALT")]),entry("opp-two","buyer-one",[oid("B")])],2,g.registry_sha256(old))
        compiled=g.validate_transition(old,new); self.assertEqual((compiled["generation"],len(compiled["entries"])),(2,2))
    def test_generation_skip_rejected(self):
        old=reg([entry("opp-one","buyer-one",[oid("A")])]); new=reg([entry("opp-one","buyer-one",[oid("A")])],3,g.registry_sha256(old))
        with self.assertRaises(s.IdentityAliasError): g.validate_transition(old,new)
    def test_prior_digest_mismatch_rejected(self):
        old=reg([entry("opp-one","buyer-one",[oid("A")])]); new=reg([entry("opp-one","buyer-one",[oid("A")])],2,"0"*64)
        with self.assertRaises(s.IdentityAliasError): g.validate_transition(old,new)
    def test_alias_removal_rejected(self):
        old=reg([entry("opp-one","buyer-one",[oid("A"),oid("B")])]); new=reg([entry("opp-one","buyer-one",[oid("A")])],2,g.registry_sha256(old))
        with self.assertRaises(s.IdentityAliasError): g.validate_transition(old,new)
    def test_canonical_removal_rejected(self):
        old=reg([entry("opp-one","buyer-one",[oid("A")])]); new=reg([],2,g.registry_sha256(old))
        with self.assertRaises(s.IdentityAliasError): g.validate_transition(old,new)
    def test_buyer_reassignment_rejected(self):
        old=reg([entry("opp-one","buyer-one",[oid("A")])]); new=reg([entry("opp-one","buyer-two",[oid("A")])],2,g.registry_sha256(old))
        with self.assertRaises(s.IdentityAliasError): g.validate_transition(old,new)
    def test_historical_bytes_unchanged(self):
        old=reg([entry("opp-one","buyer-one",[oid("A")])]); before=s.canonical_json(g.compile_registry(old)); new=reg([entry("opp-one","buyer-one",[oid("A"),oid("B")])],2,g.registry_sha256(old))
        g.validate_transition(old,new); self.assertEqual(s.canonical_json(g.compile_registry(old)),before)
    def test_strict_json_and_bool_generation(self):
        for raw in ('{"x":1,"x":2}','{"x":1.2}','{"x":NaN}'):
            with self.assertRaises(s.IdentityAliasError): s.strict_json_loads(raw)
        with self.assertRaises(s.IdentityAliasError): g.compile_registry(reg([],True,None))

if __name__=="__main__": unittest.main()
