from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from .cli import main
from .engine import GateError, compile_gate, make_receipt, verify_bundle


def partner(name="Partner A", state="UNVERIFIED", *, earliest=None, lead=None):
    cap = {"state": state, "earliest_date": earliest, "lead_time_days": lead, "evidence_urls": []}
    if state != "UNVERIFIED":
        cap["evidence_urls"] = ["https://partner.example/capacity"]
    return {
        "name": name,
        "capability_evidence_urls": ["https://partner.example/capability"],
        "capacity": cap,
        "conflicts_dnr": [],
    }


def opp(oid="o1", *, due="2026-10-01", partners=None, start=None, rel="CLEAR", collision="CLEAR"):
    dates = {
        "issue": {"date": "2026-09-01", "label": "issued", "evidence_urls": ["https://buyer.example/rfp"]},
        "questions_due": None,
        "prebid": None,
        "proposal_due": {"date": due, "label": "proposal due", "evidence_urls": ["https://buyer.example/rfp"]},
        "anticipated_award": None,
        "start": None if start is None else {"date": start, "label": "start", "evidence_urls": ["https://buyer.example/rfp"]},
        "go_live": None,
    }
    return {
        "id": oid,
        "buyer": f"Buyer {oid}",
        "source_urls": ["https://buyer.example/rfp"],
        "dates": dates,
        "mandatory_delivery_window_days": None,
        "partners": partners if partners is not None else [partner()],
        "workshare": {
            "fixed_fee_minor": 2500000,
            "currency": "USD",
            "scope": "bounded acceptance-evidence workshare",
            "acceptance_criteria": ["evidence ledger reproduced"],
            "exclusions": ["no production mutation"],
        },
        "relationship_state": rel,
        "collision_state": collision,
    }


def doc(*rows):
    return {"schema": "procurement-runway-gate-input/v1", "as_of": "2026-09-17", "opportunities": list(rows)}


class GateTests(unittest.TestCase):
    def test_unverified_capacity_means_ask(self):
        out = compile_gate(doc(opp()))
        row = out["opportunities"][0]
        self.assertEqual(row["runway_state"], "ASK_CAPACITY_FIRST")
        self.assertFalse(row["external_send_authorized"])

    def test_explicit_earliest_fit_means_ready(self):
        p = partner(state="EXPLICIT_EARLIEST_DATE", earliest="2026-09-20")
        row = compile_gate(doc(opp(partners=[p], start="2026-10-15")))["opportunities"][0]
        self.assertEqual(row["runway_state"], "READY")

    def test_explicit_lead_fit_means_ready(self):
        p = partner(state="EXPLICIT_LEAD_TIME_DAYS", lead=10)
        row = compile_gate(doc(opp(partners=[p], start="2026-10-15")))["opportunities"][0]
        self.assertEqual(row["runway_state"], "READY")

    def test_all_explicit_capacity_miss_is_too_late(self):
        p = partner(state="EXPLICIT_EARLIEST_DATE", earliest="2026-11-01")
        row = compile_gate(doc(opp(partners=[p], start="2026-10-15")))["opportunities"][0]
        self.assertEqual(row["runway_state"], "TOO_LATE")
        self.assertEqual(row["selected_partners"], [])

    def test_due_today_is_too_late(self):
        row = compile_gate(doc(opp(due="2026-09-17")))["opportunities"][0]
        self.assertEqual(row["runway_state"], "TOO_LATE")

    def test_no_partner_is_unknown(self):
        row = compile_gate(doc(opp(partners=[])))["opportunities"][0]
        self.assertEqual(row["runway_state"], "UNKNOWN")

    def test_max_three_selected_sorted(self):
        rows = [
            partner("Zulu"), partner("Alpha"), partner("Delta"), partner("Beta")
        ]
        selected = compile_gate(doc(opp(partners=rows)))["opportunities"][0]["selected_partners"]
        self.assertEqual([p["name"] for p in selected], ["Alpha", "Beta", "Delta"])

    def test_dnr_dominates_contact_not_runway(self):
        row = compile_gate(doc(opp(rel="DNR")))["opportunities"][0]
        self.assertEqual(row["runway_state"], "ASK_CAPACITY_FIRST")
        self.assertEqual(row["contact_state"], "HOLD_DNR")
        self.assertFalse(row["external_send_authorized"])

    def test_collision_holds_contact(self):
        row = compile_gate(doc(opp(collision="CLAIMED_ELSEWHERE")))["opportunities"][0]
        self.assertEqual(row["contact_state"], "HOLD_COLLISION")

    def test_unverified_capacity_cannot_smuggle_timing(self):
        bad = opp()
        bad["partners"][0]["capacity"]["earliest_date"] = "2026-09-20"
        with self.assertRaises(GateError):
            compile_gate(doc(bad))

    def test_explicit_capacity_requires_evidence(self):
        p = partner(state="EXPLICIT_LEAD_TIME_DAYS", lead=2)
        p["capacity"]["evidence_urls"] = []
        with self.assertRaises(GateError):
            compile_gate(doc(opp(partners=[p])))

    def test_bad_date_rejected(self):
        bad = opp()
        bad["dates"]["proposal_due"]["date"] = "09/30/2026"
        with self.assertRaises(GateError):
            compile_gate(doc(bad))

    def test_duplicate_opportunity_rejected(self):
        with self.assertRaises(GateError):
            compile_gate(doc(opp("same"), opp("same")))

    def test_unknown_keys_rejected(self):
        bad = opp()
        bad["send_authorized"] = True
        with self.assertRaises(GateError):
            compile_gate(doc(bad))

    def test_receipt_tamper_detected(self):
        raw = doc(opp())
        out = compile_gate(raw)
        receipt = make_receipt(out)
        verify_bundle(raw, out, receipt)
        tampered = copy.deepcopy(out)
        tampered["opportunities"][0]["runway_state"] = "READY"
        with self.assertRaises(GateError):
            verify_bundle(raw, tampered, receipt)

    def test_cli_compile_verify_and_exclusive_output(self):
        raw = doc(opp())
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "input.json"
            inp.write_text(json.dumps(raw), encoding="utf-8")
            out = td / "out"
            self.assertEqual(main(["compile", str(inp), "--output-dir", str(out)]), 0)
            self.assertEqual(main(["verify", str(inp), "--output-dir", str(out)]), 0)
            self.assertEqual(main(["compile", str(inp), "--output-dir", str(out)]), 2)

    def test_all_authority_flags_false(self):
        out = compile_gate(doc(opp()))
        for key in (
            "external_send_authorized", "provider_mutation_authorized",
            "submission_authorized", "payment_or_revenue_inferred",
        ):
            self.assertIs(out[key], False)
            self.assertIs(out["opportunities"][0][key], False)


if __name__ == "__main__":
    unittest.main()
