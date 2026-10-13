import copy
import json
import unittest

from core import ContractError, build_packet, canonical_json, extract_requirements, parse_evidence, verify_packet

RFP = """# Demo procurement\nProposals must be received by October 1, 2026.\nThe vendor shall maintain at least $1,000,000 general liability insurance.\nThe vendor must hold SOC 2 Type II certification at the time of submission.\nThe solution must support WCAG 2.2 AA accessibility.\nThe vendor shall provide an incident response target of four hours or less.\nThe vendor must provide three client references.\n"""

EVIDENCE = [
    {"id": "E-INSURANCE", "claim": "Synthetic demo general liability insurance coverage of $2,000,000.", "source": "demo/insurance.txt", "confirmed": True, "tags": ["insurance"], "expires": "2026-12-31", "synthetic": True},
    {"id": "E-ACCESS", "claim": "Synthetic demo product accessibility verification states WCAG 2.2 AA support.", "source": "demo/accessibility.txt", "confirmed": True, "tags": ["accessibility"], "synthetic": True},
    {"id": "E-IR", "claim": "Synthetic demo incident response policy targets acknowledgement within two hours.", "source": "demo/incident-response.txt", "confirmed": True, "tags": ["security"], "synthetic": True},
    {"id": "E-OLD-SOC", "claim": "Synthetic SOC 2 Type II report.", "source": "demo/old-soc2.txt", "confirmed": True, "tags": ["security", "certification"], "expires": "2026-01-01", "synthetic": True},
]


class TenderProofCoreTests(unittest.TestCase):
    def test_extracts_stable_requirements_and_deadline(self):
        one = extract_requirements(RFP)
        two = extract_requirements(RFP)
        self.assertEqual(one, two)
        self.assertEqual([r.id for r in one], [f"R-{i:03d}" for i in range(1, 7)])
        self.assertEqual(one[0].deadline, "October 1, 2026")

    def test_empty_rfp_fails_closed(self):
        with self.assertRaises(ContractError):
            extract_requirements("hello world")

    def test_duplicate_evidence_id_rejected(self):
        with self.assertRaises(ContractError):
            parse_evidence([EVIDENCE[0], EVIDENCE[0]])

    def test_unconfirmed_evidence_is_not_support(self):
        ev = copy.deepcopy(EVIDENCE)
        ev[0]["confirmed"] = False
        packet = build_packet(RFP, ev, as_of="2026-09-13")
        ins = next(b for b in packet["bindings"] if b["requirement"]["category"] == "insurance")
        self.assertEqual(ins["status"], "BLOCKER")

    def test_expired_security_evidence_is_ignored_and_blocks_bid(self):
        packet = build_packet(RFP, EVIDENCE, as_of="2026-09-13")
        soc = next(b for b in packet["bindings"] if "SOC 2" in b["requirement"]["text"])
        self.assertEqual(soc["status"], "BLOCKER")
        self.assertEqual(packet["decision"]["state"], "NO_BID")

    def test_supported_claims_bind_to_evidence(self):
        packet = build_packet(RFP, EVIDENCE, as_of="2026-09-13")
        supported = [b for b in packet["bindings"] if b["status"] == "SUPPORTED"]
        self.assertGreaterEqual(len(supported), 2)
        for b in supported:
            self.assertTrue(b["evidence_id"].startswith("E-"))

    def test_missing_items_never_become_affirmative_response_text(self):
        packet = build_packet(RFP, EVIDENCE, as_of="2026-09-13")
        by_id = {s["requirement_id"]: s for s in packet["response_sections"]}
        for binding in packet["bindings"]:
            if binding["status"] in {"MISSING", "BLOCKER"}:
                self.assertTrue(by_id[binding["requirement"]["id"]]["text"].startswith("DO NOT CLAIM"))

    def test_packet_is_deterministic_for_fixed_as_of(self):
        a = build_packet(RFP, EVIDENCE, as_of="2026-09-13")
        b = build_packet(RFP, json.loads(json.dumps(EVIDENCE)), as_of="2026-09-13")
        self.assertEqual(canonical_json(a), canonical_json(b))

    def test_receipt_verifies(self):
        packet = build_packet(RFP, EVIDENCE, as_of="2026-09-13")
        self.assertTrue(verify_packet(packet))

    def test_tampered_decision_fails_receipt(self):
        packet = build_packet(RFP, EVIDENCE, as_of="2026-09-13")
        packet["decision"]["state"] = "BID"
        self.assertFalse(verify_packet(packet))

    def test_resealed_authority_escalation_still_fails(self):
        from core import sha256_text
        packet = build_packet(RFP, EVIDENCE, as_of="2026-09-13")
        packet["authority"]["buyer_send_authorized"] = True
        bare = dict(packet)
        bare.pop("receipt")
        packet["receipt"]["payload_sha256"] = sha256_text(canonical_json(bare))
        self.assertFalse(verify_packet(packet))

    def test_input_change_changes_receipt(self):
        a = build_packet(RFP, EVIDENCE, as_of="2026-09-13")
        b = build_packet(RFP + "\nThe vendor must provide a disaster recovery plan.\n", EVIDENCE, as_of="2026-09-13")
        self.assertNotEqual(a["receipt"]["payload_sha256"], b["receipt"]["payload_sha256"])

    def test_deadline_is_operational_not_missing_evidence(self):
        packet = build_packet(RFP, EVIDENCE, as_of="2026-09-13")
        deadline = next(b for b in packet["bindings"] if b["requirement"]["category"] == "deadline")
        self.assertEqual(deadline["status"], "OPERATIONAL")
        self.assertNotIn(deadline["requirement"]["id"], packet["decision"]["missing"])

    def test_two_references_cannot_satisfy_three_reference_requirement(self):
        ev = copy.deepcopy(EVIDENCE) + [{
            "id": "E-REFERENCES",
            "claim": "Synthetic demo includes two client references.",
            "source": "demo/references.txt",
            "confirmed": True,
            "tags": ["references"],
            "synthetic": True,
        }]
        packet = build_packet(RFP, ev, as_of="2026-09-13")
        refs = next(b for b in packet["bindings"] if b["requirement"]["category"] == "references")
        self.assertEqual(refs["status"], "MISSING")

    def test_low_insurance_limit_cannot_satisfy_requirement(self):
        ev = copy.deepcopy(EVIDENCE)
        ev[0]["claim"] = "Synthetic demo general liability insurance coverage of $500,000."
        packet = build_packet(RFP, ev, as_of="2026-09-13")
        ins = next(b for b in packet["bindings"] if b["requirement"]["category"] == "insurance")
        self.assertEqual(ins["status"], "BLOCKER")

    def test_slow_incident_target_cannot_satisfy_four_hour_requirement(self):
        ev = copy.deepcopy(EVIDENCE)
        ev[2]["claim"] = "Synthetic demo incident response policy targets acknowledgement within eight hours."
        packet = build_packet(RFP, ev, as_of="2026-09-13")
        incident = next(b for b in packet["bindings"] if "incident response" in b["requirement"]["text"].lower())
        self.assertEqual(incident["status"], "BLOCKER")


if __name__ == "__main__":
    unittest.main()
