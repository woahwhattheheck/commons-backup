from copy import deepcopy
from pathlib import Path
import tempfile,unittest
try:
    from .assemble_corpus import load_bundle
    from .validate_corpus import CorpusError,load,validate
except ImportError:
    from assemble_corpus import load_bundle
    from validate_corpus import CorpusError,load,validate
HERE=Path(__file__).resolve().parent; CORPUS=HERE/"manifest.json"
class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.base=load_bundle(CORPUS)
    def fresh(self): return deepcopy(self.base)
    def test_checked_in_corpus(self):
        s=validate(self.fresh()); self.assertEqual(s["record_count"],25); self.assertEqual(s["source_count"],20); self.assertEqual(s["buyer_counts"],{"City of Coweta":6,"Coral Gables":4,"MWRD":15}); self.assertEqual(s["price_kind_counts"],{"AWARD":19,"BID":6}); self.assertEqual(s["promotability_counts"],{"HOLD_RAW_SOURCE_HASH_PENDING":25})
    def test_authority_escalation_rejected(self):
        v=self.fresh(); v["authority"]["bid_authorized"]=True
        with self.assertRaisesRegex(CorpusError,"authority ceiling"): validate(v)
    def test_fake_raw_hash_on_pending_source_rejected(self):
        v=self.fresh(); v["sources"][0]["raw_source_sha256"]="a"*64
        with self.assertRaisesRegex(CorpusError,"pending raw source hash"): validate(v)
    def test_verified_state_requires_real_hash(self):
        v=self.fresh(); v["sources"][0]["raw_hash_state"]="VERIFIED_LIVE_ADAPTER"; v["sources"][0]["raw_source_sha256"]="x"*64
        with self.assertRaisesRegex(CorpusError,"raw_source_sha256"): validate(v)
    def test_pending_source_cannot_promote(self):
        v=self.fresh(); v["records"][0]["promotability"]="LIVE_ADAPTER_READY"
        with self.assertRaisesRegex(CorpusError,"pending source cannot promote"): validate(v)
    def test_source_snapshot_tamper_rejected(self):
        v=self.fresh(); v["sources"][0]["buyer"]="Other Buyer"
        with self.assertRaisesRegex(CorpusError,"source snapshot digest mismatch"): validate(v)
    def test_record_tamper_rejected(self):
        v=self.fresh(); v["records"][0]["amount_minor"]+=1
        with self.assertRaisesRegex(CorpusError,"claim digest mismatch"): validate(v)
    def test_duplicate_source_uri_rejected(self):
        v=self.fresh(); v["sources"][1]["uri"]=v["sources"][0]["uri"]
        with self.assertRaisesRegex(CorpusError,"duplicate source URI"): validate(v)
    def test_unknown_source_rejected(self):
        v=self.fresh(); v["records"][0]["source_id"]="invented"
        with self.assertRaisesRegex(CorpusError,"unknown source"): validate(v)
    def test_source_record_binding_rejected(self):
        v=self.fresh(); v["sources"][0]["record_ids"][0]="other"
        with self.assertRaisesRegex(CorpusError,"source does not bind record id|source snapshot digest mismatch"): validate(v)
    def test_award_bid_mismatch_rejected(self):
        v=self.fresh(); v["records"][0]["price_kind"]="BID"
        with self.assertRaisesRegex(CorpusError,"price kind/source class mismatch"): validate(v)
    def test_float_money_rejected(self):
        v=self.fresh(); v["records"][0]["amount_minor"]=1.25
        with self.assertRaisesRegex(CorpusError,"amount_minor"): validate(v)
    def test_bool_money_rejected(self):
        v=self.fresh(); v["records"][0]["amount_minor"]=True
        with self.assertRaisesRegex(CorpusError,"amount_minor"): validate(v)
    def test_future_event_rejected(self):
        v=self.fresh(); v["records"][0]["event_date"]="2027-01-01"
        with self.assertRaisesRegex(CorpusError,"future event"): validate(v)
    def test_invented_term_rejected(self):
        v=self.fresh(); v["records"][0]["term_months"]=12
        with self.assertRaisesRegex(CorpusError,"must not invent unit/term"): validate(v)
    def test_excluded_bid_cannot_be_included(self):
        v=self.fresh(); v["exclusions"][0]["source_disposition"]="INCLUDED_BY_SOURCE"
        with self.assertRaisesRegex(CorpusError,"exclusion must be REJECTED_BY_SOURCE"): validate(v)
    def test_summary_drift_rejected(self):
        v=self.fresh(); v["summary"]["record_count"]=24
        with self.assertRaisesRegex(CorpusError,"summary drift"): validate(v)
    def test_too_few_records_rejected(self):
        v=self.fresh(); v["records"]=v["records"][:24]
        with self.assertRaisesRegex(CorpusError,"25..50"): validate(v)
    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"dup.json"; p.write_text('{"a":1,"a":2}',encoding="utf-8")
            with self.assertRaisesRegex(CorpusError,"duplicate JSON key"): load(p)
    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"nan.json"; p.write_text('{"a":NaN}',encoding="utf-8")
            with self.assertRaisesRegex(CorpusError,"non-finite"): load(p)
if __name__=="__main__": unittest.main()
