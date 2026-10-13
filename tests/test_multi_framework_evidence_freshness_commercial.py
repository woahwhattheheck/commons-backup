import copy, importlib.util, json, pathlib, tempfile, unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
MOD=ROOT/"revenue/multi_framework_evidence_freshness/commercial/verify_commercial.py"
spec=importlib.util.spec_from_file_location("verify_commercial", MOD)
vc=importlib.util.module_from_spec(spec); spec.loader.exec_module(vc)
OFFER=ROOT/"revenue/multi_framework_evidence_freshness/commercial/offer.json"
SAMPLE=ROOT/"revenue/multi_framework_evidence_freshness/commercial/sample_report.json"

class CommercialPacketTests(unittest.TestCase):
    def setUp(self):
        self.offer=json.loads(OFFER.read_text())
        self.sample=json.loads(SAMPLE.read_text())
    def write(self, td, offer=None, sample=None):
        op=pathlib.Path(td)/"o.json"; sp=pathlib.Path(td)/"s.json"
        op.write_text(json.dumps(self.offer if offer is None else offer))
        sp.write_text(json.dumps(self.sample if sample is None else sample))
        return op,sp
    def reseal_offer(self, offer):
        offer["offer_sha256"]=vc._sha(offer["offer"])
        sample=copy.deepcopy(self.sample)
        sample["sample"]["offer_sha256"]=offer["offer_sha256"]
        sample["sample_sha256"]=vc._sha(sample["sample"])
        return sample
    def test_canonical_packet_verifies(self):
        od,sd=vc.verify(OFFER,SAMPLE); self.assertEqual(od,self.offer["offer_sha256"]); self.assertEqual(sd,self.sample["sample_sha256"])
        self.assertEqual(od,vc.EXPECTED_OFFER_SHA256); self.assertEqual(sd,vc.EXPECTED_SAMPLE_SHA256)
    def test_price_reseal_rejected(self):
        x=copy.deepcopy(self.offer); x["offer"]["price"]["amount_cents"]=1; x["offer_sha256"]=vc._sha(x["offer"])
        with tempfile.TemporaryDirectory() as td:
            op,sp=self.write(td,offer=x)
            with self.assertRaisesRegex(vc.CommercialPacketError,"diagnostic_price"): vc.verify(op,sp)
    def test_authority_reseal_rejected(self):
        x=copy.deepcopy(self.offer); x["offer"]["authority"]["audit_opinion"]=True; x["offer_sha256"]=vc._sha(x["offer"])
        y=copy.deepcopy(self.sample); y["sample"]["offer_sha256"]=x["offer_sha256"]; y["sample_sha256"]=vc._sha(y["sample"])
        with tempfile.TemporaryDirectory() as td:
            op,sp=self.write(td,offer=x,sample=y)
            with self.assertRaisesRegex(vc.CommercialPacketError,"authority_escalation"): vc.verify(op,sp)
    def test_sample_must_bind_offer(self):
        x=copy.deepcopy(self.sample); x["sample"]["offer_sha256"]="0"*64; x["sample_sha256"]=vc._sha(x["sample"])
        with tempfile.TemporaryDirectory() as td:
            op,sp=self.write(td,sample=x)
            with self.assertRaisesRegex(vc.CommercialPacketError,"sample_offer_binding"): vc.verify(op,sp)
    def test_sample_cannot_claim_buyer_data(self):
        x=copy.deepcopy(self.sample); x["sample"]["contains_buyer_data"]=True; x["sample_sha256"]=vc._sha(x["sample"])
        with tempfile.TemporaryDirectory() as td:
            op,sp=self.write(td,sample=x)
            with self.assertRaisesRegex(vc.CommercialPacketError,"sample_data_posture"): vc.verify(op,sp)
    def test_engine_provenance_reseal_rejected(self):
        x=copy.deepcopy(self.offer); x["offer"]["acceptance"]["engine_provenance"]["merge_commit"]="f"*40; x["offer_sha256"]=vc._sha(x["offer"])
        with tempfile.TemporaryDirectory() as td:
            op,sp=self.write(td,offer=x)
            with self.assertRaisesRegex(vc.CommercialPacketError,"engine_merge"): vc.verify(op,sp)
    def test_duplicate_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            op=pathlib.Path(td)/"o.json"; sp=pathlib.Path(td)/"s.json"
            op.write_text('{"offer":{},"offer":{},"offer_sha256":"x"}'); sp.write_text(SAMPLE.read_text())
            with self.assertRaisesRegex(vc.CommercialPacketError,"duplicate_json_key"): vc.verify(op,sp)
    def test_stripped_resealed_contract_rejected(self):
        prov=copy.deepcopy(self.offer["offer"]["acceptance"]["engine_provenance"])
        offer={
            "schema":vc.EXPECTED_SCHEMA,
            "price":{"currency":"USD","amount_cents":350000,"status":"TEST_PRICE_NOT_ACCEPTED"},
            "scope":{"max_evidence_objects":500},
            "optional_integration":{"price":{"currency":"USD","amount_cents":1000000,"status":"TEST_PRICE_NOT_ACCEPTED"}},
            "acceptance":{"engine_provenance":prov},
            "authority":copy.deepcopy(self.offer["offer"]["authority"]),
        }
        x={"offer":offer,"offer_sha256":vc._sha(offer)}
        sample={
            "schema":vc.EXPECTED_SAMPLE_SCHEMA,
            "offer_sha256":x["offer_sha256"],
            "engine_provenance":prov,
            "synthetic":True,
            "contains_buyer_data":False,
            "summary":copy.deepcopy(self.sample["sample"]["summary"]),
        }
        y={"sample":sample,"sample_sha256":vc._sha(sample)}
        with tempfile.TemporaryDirectory() as td:
            op,sp=self.write(td,offer=x,sample=y)
            with self.assertRaisesRegex(vc.CommercialPacketError,"offer_contract_mismatch"): vc.verify(op,sp)
    def test_resealed_offer_contract_mutations_rejected(self):
        cases = {
            "name": lambda o: o.__setitem__("name","Evidence Freshness"),
            "offer_id": lambda o: o.__setitem__("offer_id","MFEF-ALTERED"),
            "positioning": lambda o: o.__setitem__("positioning","certification-ready"),
            "deliverables": lambda o: o["scope"]["deliverables"].pop(),
            "exclusions": lambda o: o["scope"]["exclusions"].pop(),
            "frameworks": lambda o: o["scope"]["frameworks"].pop(),
            "inputs": lambda o: o["scope"]["inputs"].pop(),
            "states": lambda o: o["scope"]["states"].pop(),
            "integration_boundary": lambda o: o["optional_integration"].__setitem__("boundary","free adapter included"),
            "acceptance_packet": lambda o: o["acceptance"].__setitem__("commercial_packet_verifies",False),
            "acceptance_sample": lambda o: o["acceptance"].__setitem__("synthetic_report_verifies",False),
            "acceptance_buyer_data": lambda o: o["acceptance"].__setitem__("buyer_data_required_for_acceptance",True),
            "extra_field": lambda o: o.__setitem__("buyer_promise","expanded"),
        }
        for name,mutate in cases.items():
            with self.subTest(name=name):
                x=copy.deepcopy(self.offer); mutate(x["offer"]); y=self.reseal_offer(x)
                with tempfile.TemporaryDirectory() as td:
                    op,sp=self.write(td,offer=x,sample=y)
                    with self.assertRaisesRegex(vc.CommercialPacketError,"offer_contract_mismatch"): vc.verify(op,sp)
    def test_resealed_offer_contract_deletions_rejected(self):
        for path in ("offer_id","positioning","name"):
            with self.subTest(path=path):
                x=copy.deepcopy(self.offer); del x["offer"][path]; y=self.reseal_offer(x)
                with tempfile.TemporaryDirectory() as td:
                    op,sp=self.write(td,offer=x,sample=y)
                    with self.assertRaisesRegex(vc.CommercialPacketError,"offer_contract_mismatch"): vc.verify(op,sp)
    def test_resealed_sample_contract_mutations_rejected(self):
        cases = {
            "sample_id": lambda s: s.__setitem__("sample_id","SYNTHETIC-ALTERED"),
            "interpretation": lambda s: s["interpretation"].pop(),
            "extra_field": lambda s: s.__setitem__("buyer_claim","expanded"),
        }
        for name,mutate in cases.items():
            with self.subTest(name=name):
                x=copy.deepcopy(self.sample); mutate(x["sample"]); x["sample_sha256"]=vc._sha(x["sample"])
                with tempfile.TemporaryDirectory() as td:
                    op,sp=self.write(td,sample=x)
                    with self.assertRaisesRegex(vc.CommercialPacketError,"sample_contract_mismatch"): vc.verify(op,sp)

if __name__=="__main__": unittest.main()
