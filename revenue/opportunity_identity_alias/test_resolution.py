from __future__ import annotations

import copy
import inspect
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from revenue.opportunity_identity_alias import resolver as r
from revenue.opportunity_identity_alias import registry as g
from revenue.opportunity_identity_alias import strict as s
from revenue.opportunity_identity_alias.aliases import normalize_alias


def reg(entries, generation=1, prior=None): return {"schema":s.REGISTRY_SCHEMA,"generation":generation,"prior_registry_sha256":prior,"entries":entries}
def entry(key,buyer,aliases): return {"canonical_opportunity_key":key,"buyer_organization_key":buyer,"aliases":aliases}
def oid(v): return {"type":"official_id","value":v}
def url(v): return {"type":"authority_url","value":v}
def obs(buyer,aliases): return {"schema":s.OBSERVATION_SCHEMA,"buyer_organization_key":buyer,"aliases":aliases}

class ResolutionTests(unittest.TestCase):
    def test_two_official_aliases_same_pursuit(self):
        registry=reg([entry("opp-one","buyer-one",[oid("RFP-123"),oid("BPM 00123")])])
        result=r.resolve_against(obs("buyer-one",[oid("bpm 00123"),oid("rfp-123")]),registry)
        self.assertEqual((result["state"],result["canonical_opportunity_key"]),("RESOLVED","opp-one"))

    def test_url_and_official_id_same_pursuit(self):
        registry=reg([entry("opp-one","buyer-one",[oid("RFP-123"),url("https://Procurement.Example.org/events/123/")])])
        result=r.resolve_against(obs("BUYER-ONE",[url("https://procurement.example.org/events/123"),oid("rfp-123")]),registry)
        self.assertEqual(result["state"],"RESOLVED")
        self.assertEqual(next(a["value"] for a in result["normalized_aliases"] if a["type"]=="authority_url"),"https://procurement.example.org/events/123")

    def test_conflicting_alias_ownership_rejected(self):
        registry=reg([entry("opp-one","buyer-one",[oid("RFP-123")]),entry("opp-two","buyer-one",[oid("rfp-123")])])
        with self.assertRaises(s.IdentityAliasError): g.compile_registry(registry)

    def test_same_alias_cross_buyer_is_independent(self):
        registry=reg([entry("opp-one","buyer-one",[oid("RFP-123")]),entry("opp-two","buyer-two",[oid("RFP-123")])])
        self.assertEqual(r.resolve_against(obs("buyer-one",[oid("RFP-123")]),registry)["canonical_opportunity_key"],"opp-one")
        self.assertEqual(r.resolve_against(obs("buyer-two",[oid("RFP-123")]),registry)["canonical_opportunity_key"],"opp-two")

    def test_duplicate_canonical_key_rejected(self):
        with self.assertRaises(s.IdentityAliasError): g.compile_registry(reg([entry("opp-one","buyer-one",[oid("A")]),entry("opp-one","buyer-two",[oid("B")])]))

    def test_ambiguous_alias_set(self):
        registry=reg([entry("opp-one","buyer-one",[oid("A")]),entry("opp-two","buyer-one",[oid("B")])])
        result=r.resolve_against(obs("buyer-one",[oid("A"),oid("B")]),registry)
        self.assertEqual(result["state"],"AMBIGUOUS_ALIAS_SET"); self.assertIsNone(result["canonical_opportunity_key"])
        self.assertEqual(result["candidate_canonical_opportunity_keys"],["opp-one","opp-two"])

    def test_unknown_and_known_plus_unknown_never_mint(self):
        registry=reg([entry("opp-one","buyer-one",[oid("A")])])
        for aliases,candidates in [([oid("UNKNOWN")],[]),([oid("A"),oid("UNKNOWN")],["opp-one"])]:
            result=r.resolve_against(obs("buyer-one",aliases),registry)
            self.assertEqual(result["state"],"UNRESOLVED_ALIAS"); self.assertIsNone(result["canonical_opportunity_key"])
            self.assertEqual(result["candidate_canonical_opportunity_keys"],candidates)

    def test_cross_buyer_transplant_unresolved(self):
        registry=reg([entry("opp-one","buyer-one",[oid("A")])])
        self.assertEqual(r.resolve_against(obs("buyer-two",[oid("A")]),registry)["state"],"UNRESOLVED_ALIAS")

    def test_observation_cannot_supply_canonical_status_or_digest(self):
        base=obs("buyer-one",[oid("A")])
        for field in ("canonical_opportunity_key","state","registry_sha256","result_sha256"):
            forged=dict(base); forged[field]="x"
            with self.assertRaises(s.IdentityAliasError): g.compile_observation(forged)

    def test_registry_result_permutation_invariance(self):
        entries=[entry("opp-two","buyer-one",[url("https://a.example.org/x/"),oid("B")]),entry("opp-one","buyer-one",[oid("A"),url("https://a.example.org/a")])]
        a=reg(entries); b=reg(list(reversed([copy.deepcopy(x) for x in entries])))
        for item in b["entries"]: item["aliases"].reverse()
        oa=obs("buyer-one",[oid("A"),url("https://a.example.org/a")]); ob=obs("buyer-one",list(reversed(oa["aliases"])))
        self.assertEqual(g.registry_sha256(a),g.registry_sha256(b)); self.assertEqual(r.resolve_against(oa,a),r.resolve_against(ob,b))

    def test_result_tamper_fails_exact_verifier(self):
        registry=reg([entry("opp-one","buyer-one",[oid("A")])]); observation=obs("buyer-one",[oid("A")]); result=r.resolve_against(observation,registry)
        self.assertTrue(r.verify_result(observation,registry,result)); forged=copy.deepcopy(result); forged["canonical_opportunity_key"]="opp-other"
        body=dict(forged); body.pop("result_sha256"); forged["result_sha256"]=s.sha256_json(body)
        self.assertFalse(r.verify_result(observation,registry,forged))

    def test_external_authority_is_always_false(self):
        result=r.resolve_against(obs("buyer-one",[oid("A")]),reg([entry("opp-one","buyer-one",[oid("A")])]))
        for field in ("external_action_authorized","buyer_contact_authorized","provider_mutation_authorized","payment_or_revenue_inferred"): self.assertIs(result[field],False)

    def test_duplicate_normalized_alias_rejected(self):
        with self.assertRaises(s.IdentityAliasError): g.compile_registry(reg([entry("opp-one","buyer-one",[oid("RFP  1"),oid("rfp 1")])]))

    def test_authority_url_secret_shapes_refused(self):
        bad=["http://a.example.org/x","https://user:pass@a.example.org/x","https://a.example.org/x?token=secret","https://a.example.org/x#frag","https://a.example.org:8443/x","https://a.example.org/a/../b"]
        for value in bad:
            with self.assertRaises(s.IdentityAliasError,msg=value): normalize_alias(url(value))

    def test_current_api_has_no_registry_selector(self):
        self.assertEqual(list(inspect.signature(r.resolve_current).parameters),["observation"]); self.assertEqual(list(inspect.signature(r.verify_current).parameters),["observation","result"])
        current=json.loads((HERE/"registry.json").read_text()); self.assertEqual(g.compile_registry(current)["entries"],[])
        self.assertEqual(r.resolve_current(obs("buyer-one",[oid("A")]))["state"],"UNRESOLVED_ALIAS")

if __name__=="__main__": unittest.main()
