from __future__ import annotations
import copy, hashlib, sys, unittest
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE))
from agdia_order_orchestrator import FORBIDDEN_PHI_KEYS,AgdiaOrderShadow,IntegrityError,load_fixture,verify_manifest_signature,verify_records

class AgdiaOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records,cls.manifest=load_fixture(); cls.by_id={r["case_id"]:r for r in cls.records}

    def test_frozen_truth_set_exact(self):
        self.assertEqual((300,240,60),(len(self.records),self.manifest["expected_ready"],self.manifest["expected_hold"]))
        expected={"ORPHAN_OR_MISSING_FORM":15,"MISSING_TUBE":15,"PERMIT_REFERENCE_INVALID":8,"LICENSE_REFERENCE_INVALID":8,"CROP_PANEL_MISMATCH":7,"ASSAY_VERSION_UNAPPROVED":7}
        self.assertEqual(expected,self.manifest["expected_hold_codes"])
        self.assertEqual(Counter(expected),Counter(r["truth_hold"] for r in self.records if r["truth_hold"]))
        verify_manifest_signature(self.manifest); verify_records(self.records,self.manifest)
        text=(HERE/"fixtures"/"agdia_300_cases.json").read_text()
        self.assertEqual(self.manifest["dataset_sha256"],hashlib.sha256(text.encode()).hexdigest())

    def test_first_replay_is_exact_240_ready_60_hold(self):
        s=AgdiaOrderShadow({"authoritative":"unchanged"}); r=s.replay(self.records,self.manifest)
        self.assertEqual((240,60,0),(r.ready,r.hold,r.replayed))
        self.assertEqual((240,240,480,240,60,300),(r.accessions_added,r.panels_added,r.aliquots_added,r.reports_added,r.holds_added,r.events_added))
        self.assertEqual(dict(sorted(self.manifest["expected_hold_codes"].items())),r.hold_counts)

    def test_ready_cases_reconcile_counts_and_route_correct_panel_once(self):
        s=AgdiaOrderShadow(); r=s.replay(self.records,self.manifest)
        for out in r.outcomes:
            if out["status"]!="READY":continue
            src=self.by_id[out["case_id"]]; spec=self.manifest["approved_specs"][src["crop"]]
            self.assertEqual((1,1,2,2),(src["package_count"],src["form_count"],src["tube_count"],len(src["tube_ids"])))
            self.assertEqual((spec["panel"],spec["assay_version"]),(out["panel"],out["assay_version"]))
            self.assertEqual(2,out["aliquots_created"])
            self.assertEqual(2,sum(1 for a in s.aliquots.values() if a["case_id"]==out["case_id"]))

    def test_held_cases_create_no_report_or_aliquot(self):
        s=AgdiaOrderShadow(); r=s.replay(self.records,self.manifest)
        held=[o for o in r.outcomes if o["status"]=="HOLD"]; self.assertEqual(60,len(held))
        for o in held:
            cid=o["case_id"]; self.assertEqual((0,0),(o["report_created"],o["aliquots_created"]))
            self.assertNotIn(cid,s.accessions); self.assertNotIn(cid,s.panels); self.assertNotIn(cid,s.staged_reports)
            self.assertFalse(any(a["case_id"]==cid for a in s.aliquots.values()))

    def test_results_stage_only_for_designated_contact_and_are_not_sent(self):
        s=AgdiaOrderShadow(); s.replay(self.records,self.manifest)
        for cid,report in s.staged_reports.items():
            src=self.by_id[cid]
            self.assertEqual(src["designated_contact_id"],report["designated_contact_id"])
            self.assertEqual("STAGED_HUMAN_REVIEW",report["state"]); self.assertFalse(report["sent"])
            self.assertEqual(src["route_sha256"],report["route_sha256"])

    def test_source_hashes_and_custody_lineage_survive(self):
        s=AgdiaOrderShadow(); r=s.replay(self.records,self.manifest)
        for o in r.outcomes:
            if o["status"]!="READY":continue
            src=self.by_id[o["case_id"]]; acc=s.accessions[o["case_id"]]
            self.assertEqual((src["source_sha256"],src["custody_sha256"],src["route_sha256"]),(o["source_sha256"],o["custody_sha256"],o["route_sha256"]))
            self.assertEqual((src["source_sha256"],src["custody_sha256"]),(acc["source_sha256"],acc["custody_sha256"]))

    def test_second_full_replay_adds_zero_state(self):
        authoritative={"source":"buyer-system","revision":2}; s=AgdiaOrderShadow(authoritative); fp=s.authoritative_fingerprint
        first=s.replay(self.records,self.manifest); digest=first.state_digest; counts=(len(s.accessions),len(s.panels),len(s.aliquots),len(s.staged_reports),len(s.holds),len(s.events))
        second=s.replay(self.records,self.manifest)
        self.assertEqual((0,0,300),(second.ready,second.hold,second.replayed))
        self.assertEqual((0,0,0,0,0,0),(second.accessions_added,second.panels_added,second.aliquots_added,second.reports_added,second.holds_added,second.events_added))
        self.assertEqual(digest,second.state_digest); self.assertEqual(counts,(len(s.accessions),len(s.panels),len(s.aliquots),len(s.staged_reports),len(s.holds),len(s.events)))
        self.assertEqual((fp,authoritative),(s.authoritative_fingerprint,s.authoritative_state))

    def test_manifest_record_and_phi_shaped_tampering_reject(self):
        bad=copy.deepcopy(self.manifest); bad["expected_ready"]=239
        with self.assertRaises(IntegrityError):verify_manifest_signature(bad)
        rec=copy.deepcopy(self.records); rec[0]["custody_chain"].append("TAMPER")
        with self.assertRaises(IntegrityError):verify_records(rec,self.manifest)
        phi=copy.deepcopy(self.records); phi[0]["patient_name"]="synthetic-but-forbidden"
        with self.assertRaises(IntegrityError):verify_records(phi,self.manifest)

    def test_release_requires_named_human_and_auto_release_fails_closed(self):
        s=AgdiaOrderShadow(); s.replay(self.records,self.manifest)
        with self.assertRaises(PermissionError):s.release_report("AGDIA-CASE-0001","")
        for actor in ("auto","system","bot","automation","agent","autonomous"," SYSTEM "):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionError):s.release_report("AGDIA-CASE-0001",actor)
        self.assertEqual(("STAGED_HUMAN_REVIEW",None),(s.staged_reports["AGDIA-CASE-0001"]["state"],s.staged_reports["AGDIA-CASE-0001"]["released_by"]))
        with self.assertRaises(PermissionError):s.automatic_release("AGDIA-CASE-0001")
        x=s.release_report("AGDIA-CASE-0001","Named QA Reviewer")
        self.assertEqual(("RELEASED_BY_NAMED_HUMAN","Named QA Reviewer",self.by_id["AGDIA-CASE-0001"]["designated_contact_id"]),(x["state"],x["released_by"],x["designated_contact_id"]))
        with self.assertRaises(PermissionError):s.release_report("AGDIA-CASE-0001","Second Reviewer")
        self.assertEqual("Named QA Reviewer",s.staged_reports["AGDIA-CASE-0001"]["released_by"])

    def test_release_rejects_reserved_tokens_and_single_token_labels_without_mutation(self):
        s=AgdiaOrderShadow(); s.replay(self.records,self.manifest)
        before=copy.deepcopy(s.staged_reports["AGDIA-CASE-0001"])
        for actor in ("System Reviewer","AI Reviewer","Service Account","bot-reviewer","agent_01",
                      "Serv ice Account","Sys tem Reviewer","Autom ation Reviewer",
                      "Autono mous Reviewer","A I Reviewer","Reviewer","12 34",None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionError):s.release_report("AGDIA-CASE-0001",actor)
                self.assertEqual(before,s.staged_reports["AGDIA-CASE-0001"])
        x=s.release_report("AGDIA-CASE-0001","QA Reviewer")
        self.assertEqual(("RELEASED_BY_NAMED_HUMAN","QA Reviewer"),(x["state"],x["released_by"]))

if __name__=="__main__":unittest.main()
