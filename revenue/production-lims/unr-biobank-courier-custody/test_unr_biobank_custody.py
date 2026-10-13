from __future__ import annotations
import copy, hashlib, sys, unittest
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE))
from unr_biobank_custody import FORBIDDEN_PHI_KEYS,IntegrityError,UNRBiobankCustodyShadow,load_fixture,named_human,verify_manifest_signature,verify_records

class UNRBiobankCustodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records,cls.manifest=load_fixture(); cls.by_id={r["shipment_id"]:r for r in cls.records}

    def test_frozen_manifest_and_truth_set_are_exact(self):
        self.assertEqual((120,90,30),(len(self.records),self.manifest["expected_ready"],self.manifest["expected_hold"]))
        expected={"IRB_MTA_REFERENCE_INVALID":8,"CUSTODY_TEMPERATURE_FAIL":6,"DUPLICATE_BARCODE":6,"SPECIMEN_MANIFEST_MISMATCH":5,"UNAPPROVED_TRANSPORT_ROUTE":5}
        self.assertEqual(expected,self.manifest["expected_hold_codes"])
        self.assertEqual(Counter(expected),Counter(r["truth_hold"] for r in self.records if r["truth_hold"]))
        verify_manifest_signature(self.manifest); verify_records(self.records,self.manifest)
        text=(HERE/"fixtures"/"unr_120_shipments.json").read_text()
        self.assertEqual(self.manifest["dataset_sha256"],hashlib.sha256(text.encode()).hexdigest())

    def test_first_replay_is_exact_90_ready_30_hold(self):
        s=UNRBiobankCustodyShadow({"authoritative":"unchanged"}); r=s.replay(self.records,self.manifest)
        self.assertEqual((90,30,0,90,180,270,30,120),(r.ready_for_storage,r.hold,r.replayed,r.specimens_added,r.aliquots_added,r.positions_added,r.holds_added,r.events_added))
        self.assertEqual(dict(sorted(self.manifest["expected_hold_codes"].items())),r.hold_counts)
        self.assertEqual((90,180,270,30,120),(len(s.specimens),len(s.aliquots),len(s.positions),len(s.holds),len(s.events)))

    def test_held_shipments_create_nothing_and_research_stays_unavailable(self):
        s=UNRBiobankCustodyShadow(); r=s.replay(self.records,self.manifest)
        held=[x for x in r.outcomes if x["status"]=="HOLD"]; ready=[x for x in r.outcomes if x["status"]=="READY_FOR_STORAGE"]
        self.assertEqual((30,90),(len(held),len(ready)))
        self.assertTrue(all((x["specimen_created"],x["aliquots_created"],x["positions_created"])==(0,0,0) for x in held))
        self.assertTrue(all(not x["research_available"] for x in ready))
        self.assertTrue(all(not x["research_available"] for x in s.specimens.values()))
        self.assertTrue(all(not x["research_available"] for x in s.aliquots.values()))

    def test_ready_lineage_hashes_and_position_map_survive_exactly(self):
        s=UNRBiobankCustodyShadow(); r=s.replay(self.records,self.manifest)
        keys=("source_sha256","courier_sha256","custody_sha256","temperature_sha256","position_sha256")
        for o in r.outcomes:
            if o["status"]!="READY_FOR_STORAGE":continue
            src=self.by_id[o["shipment_id"]]; specimen=s.specimens[o["shipment_id"]]
            for k in keys:self.assertEqual((src[k],src[k]),(o[k],specimen[k]))
            self.assertEqual(3,len(src["positions"]))
            for label,coord in src["positions"].items():
                expected=src["specimen_id"] if label=="parent" else f"{src['specimen_id']}-A{int(label.split('_')[1])}"
                self.assertEqual(expected,s.positions[coord])

    def test_fixture_is_explicitly_deidentified_and_has_no_phi_shaped_keys(self):
        self.assertTrue(all(r["deidentified"] and not ({k.lower() for k in r}&FORBIDDEN_PHI_KEYS) for r in self.records))

    def test_full_second_replay_adds_zero_effects(self):
        authoritative={"source":"buyer-system","revision":3}; s=UNRBiobankCustodyShadow(authoritative); af=s.authoritative_fingerprint
        first=s.replay(self.records,self.manifest); digest=first.state_digest; counts=(len(s.specimens),len(s.aliquots),len(s.positions),len(s.holds),len(s.events))
        second=s.replay(self.records,self.manifest)
        self.assertEqual((0,0,120,0,0,0,0,0),(second.ready_for_storage,second.hold,second.replayed,second.specimens_added,second.aliquots_added,second.positions_added,second.holds_added,second.events_added))
        self.assertEqual(digest,second.state_digest); self.assertEqual(counts,(len(s.specimens),len(s.aliquots),len(s.positions),len(s.holds),len(s.events)))
        self.assertEqual((af,authoritative),(s.authoritative_fingerprint,s.authoritative_state))

    def test_duplicate_barcodes_hold_without_creating_storage_state(self):
        s=UNRBiobankCustodyShadow(); s.replay(self.records,self.manifest); dup=[r for r in self.records if r["truth_hold"]=="DUPLICATE_BARCODE"]
        self.assertEqual(6,len(dup))
        for r in dup:
            sid=r["shipment_id"]; self.assertEqual("DUPLICATE_BARCODE",s.holds[sid]["hold_code"]); self.assertNotIn(sid,s.specimens)
            self.assertFalse(any(a["shipment_id"]==sid for a in s.aliquots.values()))

    def test_manifest_and_record_tampering_are_rejected(self):
        bad=copy.deepcopy(self.manifest); bad["expected_ready"]=89
        with self.assertRaises(IntegrityError):verify_manifest_signature(bad)
        badr=copy.deepcopy(self.records); badr[0]["receipt_temp_c"]+=1
        with self.assertRaises(IntegrityError):verify_records(badr,self.manifest)
        phi=copy.deepcopy(self.records); phi[0]["patient_name"]="synthetic-but-forbidden"
        with self.assertRaises(IntegrityError):verify_records(phi,self.manifest)

    def test_named_human_controls_research_use_and_auto_release_is_impossible(self):
        s=UNRBiobankCustodyShadow(); s.replay(self.records,self.manifest)
        with self.assertRaises(PermissionError):s.authorize_research_use("UNR-SHIP-0001","")
        with self.assertRaises(PermissionError):s.automatic_research_release("UNR-SHIP-0001")
        x=s.authorize_research_use("UNR-SHIP-0001","Named Biobank Reviewer")
        self.assertEqual(("RESEARCH_USE_AUTHORIZED_BY_NAMED_HUMAN","Named Biobank Reviewer"),(x["state"],x["reviewed_by"]))
        self.assertTrue(s.specimens["UNR-SHIP-0001"]["research_available"])
        self.assertTrue(all(a["research_available"] for a in s.aliquots.values() if a["shipment_id"]=="UNR-SHIP-0001"))

    def test_reserved_automation_tokens_and_short_labels_are_rejected_without_mutation(self):
        s=UNRBiobankCustodyShadow(); s.replay(self.records,self.manifest)
        before=s.state_digest()
        for bad in (
            "system","AI Reviewer","Service Account","bot agent","12 34","A B","auto",
            "Serv ice Account","Sys tem Reviewer","Work flow Account","Assist ant Reviewer",
            "service2 account","AI2 Reviewer",
        ):
            with self.assertRaises(PermissionError):s.authorize_research_use("UNR-SHIP-0001",bad)
            self.assertFalse(s.specimens["UNR-SHIP-0001"]["research_available"])
            self.assertNotIn("UNR-SHIP-0001",s.research_use)
        self.assertEqual(before,s.state_digest())
        for good in ("Named Biobank Reviewer","Aisha Reviewer","Agentson Reviewer","Serviceman Reviewer"):
            self.assertTrue(named_human(good),good)

    def test_one_way_authorization_does_not_overwrite_reviewed_by(self):
        s=UNRBiobankCustodyShadow(); s.replay(self.records,self.manifest)
        first=s.authorize_research_use("UNR-SHIP-0001","Named Biobank Reviewer")
        second=s.authorize_research_use("UNR-SHIP-0001","Different Named Reviewer")
        self.assertEqual(first,second)
        self.assertEqual("Named Biobank Reviewer",s.research_use["UNR-SHIP-0001"]["reviewed_by"])
        self.assertTrue(s.specimens["UNR-SHIP-0001"]["research_available"])

if __name__=="__main__":unittest.main()
