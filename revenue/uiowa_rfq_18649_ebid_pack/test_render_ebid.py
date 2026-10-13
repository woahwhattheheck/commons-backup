#!/usr/bin/env python3
from __future__ import annotations
import copy, importlib.util, sys, tempfile, unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("uiowa_ebid",HERE/"render_ebid.py")
m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m
assert spec.loader is not None
spec.loader.exec_module(m)

def inputs():
    return (
        m.load_json(HERE/"field-map.json"),
        m.load_json(HERE/"answers.json"),
        m.load_json(HERE/"attachments.json"),
        m.load_json(HERE/"source-state.json"),
    )

class EbidRendererTests(unittest.TestCase):
    def run_pack(self,fmap=None,answers=None,attachments=None,source=None):
        base=inputs()
        fmap=copy.deepcopy(fmap if fmap is not None else base[0])
        answers=copy.deepcopy(answers if answers is not None else base[1])
        attachments=copy.deepcopy(attachments if attachments is not None else base[2])
        source=copy.deepcopy(source if source is not None else base[3])
        out=Path(tempfile.mkdtemp())/"outputs"
        return m.render_pack(fmap,answers,attachments,source,out),out

    def test_exact_36_attribute_map(self):
        fmap,*_=inputs()
        self.assertEqual(m.validate_map(fmap),[])
        self.assertEqual([a["attribute_id"] for a in fmap["attributes"]],list(range(1,37)))

    def test_prepared_pack_structural_but_not_submission_ready(self):
        report,out=self.run_pack()
        self.assertTrue(report["structurally_valid"])
        self.assertFalse(report["submission_ready"])
        self.assertEqual(report["attribute_count"],36)
        self.assertTrue((out/"submission-index.csv").exists())
        self.assertTrue((out/"combined-preview.md").exists())
        self.assertTrue(any("source_refresh" in b for b in report["blockers"]))

    def test_no_silent_truncation_and_utf8_round_trip(self):
        fmap,answers,attachments,source=inputs(); answers=copy.deepcopy(answers)
        text="Bullets • survive\nCurly “quotes” survive\nEm dash — survives\nEmoji 🧪 survives"
        answers["attributes"]["attribute_05"]["text"]=text
        report,out=self.run_pack(fmap,answers,attachments,source)
        self.assertEqual(report["errors"],[])
        self.assertEqual((out/"attributes"/"attr-05.txt").read_text(encoding="utf-8"),text)

    def test_over_limit_fails_instead_of_truncating(self):
        fmap,answers,attachments,source=inputs(); answers=copy.deepcopy(answers)
        answers["attributes"]["attribute_05"]["text"]="x"*4001
        report,out=self.run_pack(fmap,answers,attachments,source)
        self.assertFalse(report["structurally_valid"])
        self.assertTrue(any("exceeds limit 4000" in e for e in report["errors"]))
        self.assertEqual(len((out/"attributes"/"attr-05.txt").read_text()),4001)

    def test_utf16_surrogate_pairs_count_conservatively(self):
        self.assertEqual(m.portal_count("🧪"*500),1000)

    def test_required_missing_accounting_record_is_error(self):
        fmap,answers,attachments,source=inputs(); answers=copy.deepcopy(answers)
        del answers["attributes"]["attribute_25"]
        report,_=self.run_pack(fmap,answers,attachments,source)
        self.assertTrue(any("attribute_25: missing answer/accounting record" in e for e in report["errors"]))

    def test_unknown_attachment_reference_is_error(self):
        fmap,answers,attachments,source=inputs(); answers=copy.deepcopy(answers)
        answers["attributes"]["attribute_05"]["text"]+="\n[[ATTACH:not-real]]"
        report,_=self.run_pack(fmap,answers,attachments,source)
        self.assertTrue(any("unknown attachment refs" in e for e in report["errors"]))

    def test_certification_cannot_auto_authorize_without_receipt(self):
        fmap,answers,attachments,source=inputs(); answers=copy.deepcopy(answers)
        answers["attributes"]["attribute_01"]={"status":"authorized","authorized_value":"checked"}
        report,_=self.run_pack(fmap,answers,attachments,source)
        self.assertTrue(any("authorization_ref" in e for e in report["errors"]))

    def test_exception_blank_not_harmless(self):
        fmap,answers,attachments,source=inputs(); answers=copy.deepcopy(answers)
        answers["attributes"]["attribute_15"]={"status":"optional_blank"}
        report,_=self.run_pack(fmap,answers,attachments,source)
        self.assertTrue(any("blank has certification effect" in e for e in report["errors"]))

    def test_required_attachments_block_submission(self):
        report,_=self.run_pack()
        self.assertTrue(any("attachment proposal" in b for b in report["blockers"]))
        self.assertTrue(any("audited_financial_statements" in b for b in report["blockers"]))

    def test_source_refresh_is_independent_gate(self):
        fmap,answers,attachments,source=inputs(); source=copy.deepcopy(source)
        source["official_refresh"].update({"confirmed":True,"source_ref":"synthetic://current-read","confirmed_at":"2026-09-19T14:00:00Z"})
        report,_=self.run_pack(fmap,answers,attachments,source)
        self.assertFalse(any("source_refresh" in b for b in report["blockers"]))
        self.assertFalse(report["submission_ready"])

    def test_fee_candidate_not_submission_ready_price(self):
        report,out=self.run_pack()
        self.assertTrue(any("fee_for_services" in b for b in report["blockers"]))
        fee=(out/"fee-details.txt").read_text(encoding="utf-8")
        self.assertIn("$24,000",fee)
        self.assertIn("travel",fee.lower())

    def test_real_prepared_text_fields_all_fit(self):
        fmap,answers,*_=inputs()
        by_id={a["field_id"]:a for a in fmap["attributes"]}
        for fid,entry in answers["attributes"].items():
            if "text" in entry:
                self.assertLessEqual(m.portal_count(entry["text"]),by_id[fid]["character_limit"],fid)

    def test_all_noninformational_attributes_accounted(self):
        fmap,answers,*_=inputs()
        expected={a["field_id"] for a in fmap["attributes"] if a["response_type"]!="informational"}
        self.assertEqual(expected,set(answers["attributes"]))

if __name__=="__main__":
    unittest.main()
