import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from packet_gate import GateError, build_receipt, validate_matrix, validate_sources, verify_receipt

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class PacketGateTests(unittest.TestCase):
    def setUp(self):
        self.sources = load("sources.json")
        self.matrix = load("matrix.json")

    def test_builds_fail_closed_receipt(self):
        receipt = build_receipt(self.sources, self.matrix)
        self.assertEqual(receipt["decision"], "HOLD_PACKET_REQUIRED")
        self.assertEqual(receipt["state"], "EVIDENCE_MATRIX_READY_PACKET_BLOCKED")
        self.assertGreater(len(receipt["mandatory_packet_required_ids"]), 0)
        self.assertGreater(len(receipt["scoreable_packet_required_ids"]), 0)
        self.assertTrue(all(value is False for value in receipt["authorities"].values()))

    def test_receipt_is_deterministic(self):
        self.assertEqual(build_receipt(self.sources, self.matrix), build_receipt(self.sources, self.matrix))

    def test_receipt_verifies_and_tamper_fails(self):
        receipt = build_receipt(self.sources, self.matrix)
        self.assertTrue(verify_receipt(receipt, self.sources, self.matrix))
        tampered = copy.deepcopy(receipt)
        tampered["decision"] = "TEAMING_BID"
        self.assertFalse(verify_receipt(tampered, self.sources, self.matrix))

    def test_third_party_mirror_cannot_be_assertable(self):
        data = copy.deepcopy(self.sources)
        next(s for s in data["sources"] if s["authority"] == "THIRD_PARTY_MIRROR")["assertable"] = True
        with self.assertRaises(GateError):
            validate_sources(data)

    def test_packet_gap_cannot_be_promoted_to_confirmed(self):
        sources = validate_sources(self.sources)
        matrix = copy.deepcopy(self.matrix)
        req = next(r for r in matrix["requirements"] if r["id"] == "clarification_deadline")
        req["state"] = "CONFIRMED_OFFICIAL"
        with self.assertRaisesRegex(GateError, "untrusted confirmed requirement id"):
            validate_matrix(matrix, sources)

    def test_unrelated_official_source_cannot_launder_mirror_claim(self):
        sources = validate_sources(self.sources)
        matrix = copy.deepcopy(self.matrix)
        req = next(r for r in matrix["requirements"] if r["id"] == "clarification_deadline")
        req["state"] = "CONFIRMED_OFFICIAL"
        req["source_ids"] = ["snoco_supplier_info"]
        with self.assertRaisesRegex(
            GateError,
            "source snoco_supplier_info does not support requirement clarification_deadline",
        ):
            validate_matrix(matrix, sources)

    def test_mixed_mirror_and_unrelated_official_cannot_launder_claim(self):
        sources = validate_sources(self.sources)
        matrix = copy.deepcopy(self.matrix)
        req = next(r for r in matrix["requirements"] if r["id"] == "clarification_deadline")
        req["state"] = "CONFIRMED_OFFICIAL"
        req["source_ids"] = ["cleat_mirror", "snoco_supplier_info"]
        with self.assertRaisesRegex(GateError, "does not support requirement clarification_deadline"):
            validate_matrix(matrix, sources)

    def test_forged_official_source_is_rejected(self):
        data = copy.deepcopy(self.sources)
        data["sources"].append(
            {
                "id": "forged",
                "authority": "OFFICIAL_COUNTY_GUIDANCE",
                "url": "https://attacker.example/fake",
                "assertable": True,
                "raw_bytes_sha256": None,
                "raw_hash_status": "UNAVAILABLE_WEB_TEXT_ONLY",
                "supports_requirement_ids": ["clarification_deadline"],
                "facts": ["Fabricated solicitation-specific deadline."],
            }
        )
        with self.assertRaisesRegex(GateError, "untrusted official source id: forged"):
            validate_sources(data)

    def test_existing_official_support_list_is_code_pinned(self):
        data = copy.deepcopy(self.sources)
        source = next(s for s in data["sources"] if s["id"] == "snoco_supplier_info")
        source["supports_requirement_ids"].append("clarification_deadline")
        with self.assertRaisesRegex(GateError, "official source identity drift: snoco_supplier_info"):
            validate_sources(data)

    def test_existing_official_url_is_code_pinned(self):
        data = copy.deepcopy(self.sources)
        source = next(s for s in data["sources"] if s["id"] == "snoco_supplier_info")
        source["url"] = "https://attacker.example/looks-official"
        with self.assertRaisesRegex(GateError, "official source identity drift: snoco_supplier_info"):
            validate_sources(data)

    def test_confirmed_requirement_text_is_code_pinned(self):
        sources = validate_sources(self.sources)
        matrix = copy.deepcopy(self.matrix)
        req = next(r for r in matrix["requirements"] if r["id"] == "proposal_due")
        req["requirement"] = "Proposal due tomorrow at noon."
        with self.assertRaisesRegex(GateError, "confirmed requirement identity drift: proposal_due"):
            validate_matrix(matrix, sources)

    def test_trusted_confirmed_requirement_cannot_be_silently_downgraded(self):
        sources = validate_sources(self.sources)
        matrix = copy.deepcopy(self.matrix)
        req = next(r for r in matrix["requirements"] if r["id"] == "proposal_due")
        req["state"] = "PACKET_REQUIRED"
        with self.assertRaisesRegex(GateError, "untrusted packet-required requirement id: proposal_due"):
            validate_matrix(matrix, sources)

    def test_confirmed_requirement_cannot_have_no_source(self):
        sources = validate_sources(self.sources)
        matrix = copy.deepcopy(self.matrix)
        req = next(r for r in matrix["requirements"] if r["id"] == "proposal_due")
        req["source_ids"] = []
        with self.assertRaisesRegex(GateError, "confirmed requirement identity drift"):
            validate_matrix(matrix, sources)

    def test_unknown_source_fails(self):
        sources = validate_sources(self.sources)
        matrix = copy.deepcopy(self.matrix)
        matrix["requirements"][0]["source_ids"] = ["missing"]
        with self.assertRaisesRegex(GateError, "unknown source"):
            validate_matrix(matrix, sources)

    def test_source_support_ids_must_be_unique(self):
        data = copy.deepcopy(self.sources)
        mirror = next(s for s in data["sources"] if s["authority"] == "THIRD_PARTY_MIRROR")
        mirror["supports_requirement_ids"].append(mirror["supports_requirement_ids"][0])
        with self.assertRaisesRegex(GateError, "must not contain duplicates"):
            validate_sources(data)

    def test_duplicate_requirement_id_fails(self):
        sources = validate_sources(self.sources)
        matrix = copy.deepcopy(self.matrix)
        matrix["requirements"][1]["id"] = matrix["requirements"][0]["id"]
        with self.assertRaisesRegex(GateError, "duplicate requirement"):
            validate_matrix(matrix, sources)

    def test_boundary_escalation_fails(self):
        sources = validate_sources(self.sources)
        matrix = copy.deepcopy(self.matrix)
        matrix["boundaries"]["proposal_submission_authorized"] = True
        with self.assertRaisesRegex(GateError, "authority boundary escalated"):
            validate_matrix(matrix, sources)

    def test_packet_state_cannot_claim_complete(self):
        matrix = copy.deepcopy(self.matrix)
        matrix["packet_state"] = "COMPLETE"
        with self.assertRaisesRegex(GateError, "fail closed"):
            build_receipt(self.sources, matrix)

    def test_no_packet_gaps_is_not_accepted_by_this_carrier(self):
        matrix = copy.deepcopy(self.matrix)
        for req in matrix["requirements"]:
            if req["state"] == "PACKET_REQUIRED":
                req["state"] = "CONFIRMED_OFFICIAL"
                req["source_ids"] = ["snoco_supplier_info"]
        with self.assertRaises(GateError):
            build_receipt(self.sources, matrix)

    def test_unknown_fields_fail_closed(self):
        data = copy.deepcopy(self.sources)
        data["surprise"] = True
        with self.assertRaisesRegex(GateError, "keys mismatch"):
            validate_sources(data)


if __name__ == "__main__":
    unittest.main()
