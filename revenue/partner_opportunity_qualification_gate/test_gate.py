import copy
import unittest

from revenue.partner_opportunity_qualification_gate.engine import (
    QualificationError,
    compile_qualification,
    make_receipt,
    verify_bundle,
)
from revenue.partner_opportunity_qualification_gate.validation import load_strict_json_text


def ref(source_id, ch):
    return {"source_id": source_id, "source_sha256": ch * 64}


def src(source_id, kind, ch, url, status="CURRENT", subject_partner=None):
    return {
        "source_id": source_id,
        "kind": kind,
        "status": status,
        "url": url,
        "sha256": ch * 64,
        "observed_on": "2026-09-17",
        "subject_partner": subject_partner,
    }


def packet():
    return {
        "schema": "partner-opportunity-qualification-input/v1",
        "as_of": "2026-09-17",
        "opportunity_id": "SYNTH-001",
        "runway_input": {
            "schema": "procurement-runway-gate-input/v1",
            "as_of": "2026-09-17",
            "opportunities": [{
                "id": "SYNTH-001",
                "buyer": "Synthetic Buyer",
                "source_urls": ["https://buyer.example/rfp.pdf"],
                "dates": {"proposal_due": {"date": "2026-10-23", "label": "proposal due", "evidence_urls": ["https://buyer.example/rfp.pdf"]}},
                "partners": [{"name": "Example MSP", "capability_evidence_urls": ["https://partner.example/services"], "capacity": {"state": "EXPLICIT_LEAD_TIME_DAYS", "lead_time_days": 0, "evidence_urls": ["https://partner.example/capacity"]}, "conflicts_dnr": []}],
                "workshare": {"fixed_fee_minor": 500000, "currency": "USD", "scope": "qualification evidence QA", "acceptance_criteria": ["evidence matrix accepted"], "exclusions": ["submission"]},
                "relationship_state": "CLEAR",
                "collision_state": "CLEAR",
            }],
        },
        "sources": [
            src("rfp", "SOLICITATION_CONTROL", "a", "https://buyer.example/rfp.pdf"),
            src("sam", "PARTNER_EVIDENCE", "b", "https://partner.example/sam", subject_partner="Example MSP"),
            src("reg", "REGISTRATION_EVIDENCE", "c", "https://buyer.example/registration", subject_partner="Example MSP"),
        ],
        "hard_gates": [
            {"gate_id": "active-sam", "label": "Active SAM", "phase": "PRE_OUTREACH", "requirement": "Partner must evidence active SAM registration", "required_evidence_kind": "PARTNER_EVIDENCE", "source_refs": [ref("rfp", "a"), ref("sam", "b")]},
            {"gate_id": "three-refs", "label": "Three references", "phase": "PRE_SUBMISSION", "requirement": "Three recent references required", "required_evidence_kind": "PARTNER_EVIDENCE", "source_refs": [ref("rfp", "a")]},
        ],
        "partners": [{
            "name": "Example MSP",
            "registration": {"state": "COMPLETE", "deadline": None, "requirement_refs": [ref("rfp", "a")], "evidence_refs": [ref("reg", "c")]},
            "gate_dispositions": [
                {"gate_id": "active-sam", "state": "SATISFIED", "evidence_refs": [ref("sam", "b")], "note": "retained SAM evidence"},
                {"gate_id": "three-refs", "state": "UNKNOWN", "evidence_refs": [], "note": "screen before submission"},
            ],
            "paid_workshare": {"state": "DEFINED", "fixed_fee_minor": 500000, "currency": "USD", "scope": "qualification evidence matrix", "acceptance_criteria": ["matrix source-bound"], "exclusions": ["prime responsibility"]},
        }],
    }


def add_unknown_partner(p, name="Other MSP"):
    p["partners"].append({"name": name, "registration": {"state": "UNKNOWN", "deadline": None, "requirement_refs": [], "evidence_refs": []}, "gate_dispositions": [{"gate_id": "active-sam", "state": "UNKNOWN", "evidence_refs": []}, {"gate_id": "three-refs", "state": "UNKNOWN", "evidence_refs": []}], "paid_workshare": {"state": "UNDEFINED"}})
    return p


def add_qualified_partner(p, name, suffix, lead_time_days=None, capacity_state="EXPLICIT_LEAD_TIME_DAYS"):
    source_ch = {"other": "d", "third": "f"}[suffix]
    reg_ch = {"other": "e", "third": "0"}[suffix]
    p["sources"].extend([
        src(f"{suffix}-sam", "PARTNER_EVIDENCE", source_ch, f"https://{suffix}.example/sam", subject_partner=name),
        src(f"{suffix}-reg", "REGISTRATION_EVIDENCE", reg_ch, f"https://buyer.example/{suffix}-registration", subject_partner=name),
    ])
    p["hard_gates"][0]["source_refs"].append(ref(f"{suffix}-sam", source_ch))
    capacity = {"state": "UNVERIFIED", "evidence_urls": []} if capacity_state == "UNVERIFIED" else {"state": "EXPLICIT_LEAD_TIME_DAYS", "lead_time_days": lead_time_days, "evidence_urls": [f"https://{suffix}.example/capacity"]}
    p["runway_input"]["opportunities"][0]["partners"].append({"name": name, "capability_evidence_urls": [f"https://{suffix}.example/services"], "capacity": capacity, "conflicts_dnr": []})
    p["partners"].append({"name": name, "registration": {"state": "COMPLETE", "deadline": None, "requirement_refs": [ref("rfp", "a")], "evidence_refs": [ref(f"{suffix}-reg", reg_ch)]}, "gate_dispositions": [{"gate_id": "active-sam", "state": "SATISFIED", "evidence_refs": [ref(f"{suffix}-sam", source_ch)]}, {"gate_id": "three-refs", "state": "UNKNOWN", "evidence_refs": []}], "paid_workshare": {"state": "DEFINED", "fixed_fee_minor": 500000, "currency": "USD", "scope": "qualification evidence matrix", "acceptance_criteria": ["matrix source-bound"], "exclusions": ["prime responsibility"]}})
    return p


class QualificationGateTests(unittest.TestCase):
    def test_ready_and_receipt(self):
        p = packet(); out = compile_qualification(p)
        self.assertEqual(out["partners"][0]["state"], "READY_FOR_MUSE_ELECTION_ONLY")
        self.assertIn("later:three-refs:UNKNOWN", out["partners"][0]["reasons"])
        self.assertFalse(out["partner_contact_authorized"])
        verify_bundle(p, out, make_receipt(p, out))

    def test_preoutreach_unknown_holds(self):
        p = packet(); p["partners"][0]["gate_dispositions"][0] = {"gate_id": "active-sam", "state": "UNKNOWN", "evidence_refs": []}
        self.assertEqual(compile_qualification(p)["partners"][0]["state"], "HOLD_HARD_GATE")

    def test_control_source_stale_holds(self):
        p = packet(); p["sources"][0]["status"] = "STALE"; self.assertEqual(compile_qualification(p)["partners"][0]["state"], "HOLD_SOURCE")

    def test_stale_partner_evidence_holds(self):
        p = packet(); p["sources"][1]["status"] = "STALE"; self.assertEqual(compile_qualification(p)["partners"][0]["state"], "HOLD_HARD_GATE")

    def test_registration_unknown_holds(self):
        p = packet(); p["partners"][0]["registration"] = {"state": "UNKNOWN", "deadline": None, "requirement_refs": [], "evidence_refs": []}; self.assertEqual(compile_qualification(p)["partners"][0]["state"], "HOLD_REGISTRATION")

    def test_registration_complete_requires_completion_evidence(self):
        p = packet(); p["partners"][0]["registration"]["evidence_refs"] = []
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_registration_complete_cannot_use_requirement_as_completion(self):
        p = packet(); p["partners"][0]["registration"]["evidence_refs"] = [ref("rfp", "a")]
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_registration_complete_requires_registration_evidence_kind(self):
        p = packet(); p["partners"][0]["registration"]["evidence_refs"] = [ref("sam", "b")]
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_future_source_rejected(self):
        p = packet(); p["sources"][1]["observed_on"] = "2026-09-18"
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_registration_expired_holds(self):
        p = packet(); p["partners"][0]["registration"] = {"state": "OPEN", "deadline": "2026-09-17", "requirement_refs": [ref("rfp", "a")], "evidence_refs": []}; self.assertEqual(compile_qualification(p)["partners"][0]["state"], "HOLD_REGISTRATION")

    def test_no_paid_seam_holds(self):
        p = packet(); p["partners"][0]["paid_workshare"] = {"state": "UNDEFINED"}; self.assertEqual(compile_qualification(p)["partners"][0]["state"], "HOLD_NO_PAID_SEAM")

    def test_digest_mismatch_fails(self):
        p = packet(); p["partners"][0]["gate_dispositions"][0]["evidence_refs"][0]["source_sha256"] = "d" * 64
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_old_receipt_rejects_source_remint(self):
        p = packet(); out = compile_qualification(p); old = make_receipt(p, out); q = copy.deepcopy(p)
        q["sources"][1]["sha256"] = "d" * 64; q["partners"][0]["gate_dispositions"][0]["evidence_refs"][0]["source_sha256"] = "d" * 64; q["hard_gates"][0]["source_refs"][1]["source_sha256"] = "d" * 64
        newout = compile_qualification(q)
        with self.assertRaises(QualificationError): verify_bundle(q, newout, old)

    def test_upstream_input_generation_remint_changes_binding_even_if_runway_output_same(self):
        p = packet(); out = compile_qualification(p); old = make_receipt(p, out); q = copy.deepcopy(p); q["runway_input"]["opportunities"][0]["mandatory_delivery_window_days"] = 10; newout = compile_qualification(q)
        self.assertEqual(out["runway_binding"]["runway_output_sha256"], newout["runway_binding"]["runway_output_sha256"]); self.assertNotEqual(out["runway_binding"]["runway_input_sha256"], newout["runway_binding"]["runway_input_sha256"])
        with self.assertRaises(QualificationError): verify_bundle(q, out, old)

    def test_control_source_must_match_runway(self):
        p = packet(); p["sources"][0]["url"] = "https://attacker.example/rfp.pdf"
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_gate_requirement_must_bind_control_source(self):
        p = packet(); p["hard_gates"][0]["source_refs"] = [ref("sam", "b")]
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_gate_disposition_cannot_use_requirement_as_partner_evidence(self):
        p = packet(); p["partners"][0]["gate_dispositions"][0]["evidence_refs"] = [ref("rfp", "a")]
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_gate_required_evidence_kind_is_enforced(self):
        p = packet(); p["hard_gates"][0]["required_evidence_kind"] = "REGISTRATION_EVIDENCE"
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_gate_required_evidence_kind_cannot_be_omitted(self):
        p = packet(); del p["hard_gates"][0]["required_evidence_kind"]
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_gate_required_evidence_kind_rejects_owner_workshare_kind(self):
        p = packet(); p["hard_gates"][0]["required_evidence_kind"] = "OWNER_WORKSHARE_EVIDENCE"
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_unsatisfied_gate_still_requires_its_evidence_kind(self):
        p = packet(); p["hard_gates"][0]["required_evidence_kind"] = "REGISTRATION_EVIDENCE"; p["partners"][0]["gate_dispositions"][0]["state"] = "UNSATISFIED"
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_gate_evidence_cannot_cross_partner_subject(self):
        p = add_unknown_partner(packet()); p["sources"][1]["subject_partner"] = "Other MSP"
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_registration_evidence_cannot_cross_partner_subject(self):
        p = add_unknown_partner(packet()); p["sources"][2]["subject_partner"] = "Other MSP"
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_partner_source_subject_must_exist(self):
        p = packet(); p["sources"][1]["subject_partner"] = "Ghost MSP"
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_nonpartner_source_cannot_claim_partner_subject(self):
        p = packet(); p["sources"][0]["subject_partner"] = "Example MSP"
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_source_identity_cannot_be_retyped(self):
        p = packet(); p["sources"].append(src("rfp-as-partner", "PARTNER_EVIDENCE", "a", "https://attacker.example/rfp-copy", subject_partner="Example MSP"))
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_source_identity_cannot_be_rebound_to_other_partner(self):
        p = add_unknown_partner(packet()); p["sources"].append(src("sam-other", "PARTNER_EVIDENCE", "b", "https://other.example/sam", subject_partner="Other MSP"))
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_same_kind_evidence_cannot_cross_gate_claim(self):
        p = packet(); p["partners"][0]["gate_dispositions"][1] = {"gate_id": "three-refs", "state": "SATISFIED", "evidence_refs": [ref("sam", "b")]}
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_gate_disposition_rejects_valid_plus_unbound_extra(self):
        p = packet()
        p["sources"].append(
            src(
                "other-proof",
                "PARTNER_EVIDENCE",
                "d",
                "https://partner.example/other-proof",
                subject_partner="Example MSP",
            )
        )
        p["partners"][0]["gate_dispositions"][0]["evidence_refs"].append(ref("other-proof", "d"))
        with self.assertRaises(QualificationError):
            compile_qualification(p)

    def test_gate_disposition_rejects_valid_plus_gate_bound_wrong_kind_extra(self):
        p = packet()
        p["hard_gates"][0]["source_refs"].append(ref("reg", "c"))
        p["partners"][0]["gate_dispositions"][0]["evidence_refs"].append(ref("reg", "c"))
        with self.assertRaises(QualificationError):
            compile_qualification(p)

    def test_registration_complete_rejects_valid_plus_partner_evidence_extra(self):
        p = packet()
        p["partners"][0]["registration"]["evidence_refs"].append(ref("sam", "b"))
        with self.assertRaises(QualificationError):
            compile_qualification(p)

    def test_old_bundle_rejects_after_gate_provenance_removal(self):
        p = packet()
        out = compile_qualification(p)
        receipt = make_receipt(p, out)
        q = copy.deepcopy(p)
        q["hard_gates"][0]["source_refs"] = [ref("rfp", "a")]
        with self.assertRaises(QualificationError):
            verify_bundle(q, out, receipt)

    def test_duplicate_gate_rejected(self):
        p = packet(); p["hard_gates"].append(copy.deepcopy(p["hard_gates"][0]))
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_missing_disposition_rejected(self):
        p = packet(); p["partners"][0]["gate_dispositions"].pop()
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_order_invariant(self):
        p = packet(); a = compile_qualification(p); q = copy.deepcopy(p); q["sources"].reverse(); q["hard_gates"].reverse(); q["partners"][0]["gate_dispositions"].reverse(); self.assertEqual(a, compile_qualification(q))

    def test_bool_not_int(self):
        p = packet(); p["partners"][0]["paid_workshare"]["fixed_fee_minor"] = True
        with self.assertRaises(QualificationError): compile_qualification(p)

    def test_selected_partner_with_explicit_miss_holds_even_when_other_partner_makes_runway_ready(self):
        p = packet(); p["runway_input"]["opportunities"][0]["dates"]["start"] = {"date": "2026-09-20", "label": "start", "evidence_urls": ["https://buyer.example/rfp.pdf"]}; add_qualified_partner(p, "Other MSP", "other", lead_time_days=10); out = compile_qualification(p); rows = {row["name"]: row for row in out["partners"]}; self.assertEqual(out["runway_binding"]["runway_state"], "READY"); self.assertEqual(rows["Example MSP"]["state"], "READY_FOR_MUSE_ELECTION_ONLY"); self.assertEqual(rows["Other MSP"]["state"], "HOLD_RUNWAY"); self.assertIn("EXPLICIT_MISS", rows["Other MSP"]["reasons"][0])

    def test_unknown_capacity_candidate_gets_capacity_question_even_when_other_partner_makes_runway_ready(self):
        p = packet(); add_qualified_partner(p, "Other MSP", "other", capacity_state="UNVERIFIED"); out = compile_qualification(p); rows = {row["name"]: row for row in out["partners"]}; self.assertEqual(out["runway_binding"]["runway_state"], "READY"); self.assertEqual(rows["Example MSP"]["state"], "READY_FOR_MUSE_ELECTION_ONLY"); self.assertEqual(rows["Other MSP"]["state"], "READY_FOR_CAPACITY_MUSE_ELECTION_ONLY")

    def test_ask_capacity_is_separate_muse_state(self):
        p = packet(); p["runway_input"]["opportunities"][0]["partners"][0]["capacity"] = {"state": "UNVERIFIED", "evidence_urls": []}; self.assertEqual(compile_qualification(p)["partners"][0]["state"], "READY_FOR_CAPACITY_MUSE_ELECTION_ONLY")

    def test_upstream_dnr_dominates(self):
        p = packet(); p["runway_input"]["opportunities"][0]["relationship_state"] = "DNR"; self.assertEqual(compile_qualification(p)["partners"][0]["state"], "HOLD_CONTACT_POLICY")

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(QualificationError): load_strict_json_text('{"schema":"a","schema":"b"}')


if __name__ == "__main__":
    unittest.main()
