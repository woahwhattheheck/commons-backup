import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import packet_gate as gate

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def requirement(matrix, rid):
    return next(row for row in matrix["requirements"] if row["id"] == rid)


class PacketGateTrustBindingTests(unittest.TestCase):
    def setUp(self):
        self.sources = load("sources.json")
        self.matrix = load("matrix.json")

    def test_public_trust_map_rebinding_cannot_mint_official_authority(self):
        baseline = gate.build_receipt(self.sources, self.matrix)
        self.assertEqual(baseline["decision"], "HOLD_PACKET_REQUIRED")

        registry = copy.deepcopy(self.sources)
        matrix = copy.deepcopy(self.matrix)
        forged_source = {
            "id": "forged_official",
            "authority": "OFFICIAL_COUNTY_GUIDANCE",
            "url": "https://attacker.example/looks-official",
            "assertable": True,
            "raw_bytes_sha256": None,
            "raw_hash_status": "UNAVAILABLE_WEB_TEXT_ONLY",
            "supports_requirement_ids": ["forged_confirmed"],
            "facts": ["Fabricated solicitation-specific authority."],
        }
        forged_requirement = {
            "id": "forged_confirmed",
            "classification": "MANDATORY",
            "state": "CONFIRMED_OFFICIAL",
            "source_ids": ["forged_official"],
            "requirement": "Fabricated requirement must be treated as official.",
        }
        registry["sources"].append(forged_source)
        matrix["requirements"].append(forged_requirement)

        sentinel = object()
        saved_sources = getattr(gate, "TRUSTED_OFFICIAL_SOURCES", sentinel)
        saved_requirements = getattr(gate, "TRUSTED_CONFIRMED_REQUIREMENTS", sentinel)
        saved_official = gate.OFFICIAL_AUTHORITIES
        saved_allowed = gate.ALLOWED_AUTHORITIES
        try:
            # Recreate the exact predecessor defect: caller process state claims
            # the forged records are trusted and also weakens public policy data.
            gate.TRUSTED_OFFICIAL_SOURCES = {"forged_official": copy.deepcopy(forged_source)}
            gate.TRUSTED_CONFIRMED_REQUIREMENTS = {
                "forged_confirmed": copy.deepcopy(forged_requirement)
            }
            gate.OFFICIAL_AUTHORITIES = {"OFFICIAL_COUNTY_GUIDANCE"}
            gate.ALLOWED_AUTHORITIES = {"OFFICIAL_COUNTY_GUIDANCE", "THIRD_PARTY_MIRROR"}

            with self.assertRaisesRegex(gate.GateError, "untrusted official source id: forged_official"):
                gate.build_receipt(registry, matrix)

            # The retained authority API must also ignore those public-module
            # rebindings for the real reviewed packet state.
            after = gate.build_receipt(self.sources, self.matrix)
            self.assertEqual(after, baseline)
            self.assertTrue(gate.verify_receipt(after, self.sources, self.matrix))
        finally:
            if saved_sources is sentinel:
                delattr(gate, "TRUSTED_OFFICIAL_SOURCES")
            else:
                gate.TRUSTED_OFFICIAL_SOURCES = saved_sources
            if saved_requirements is sentinel:
                delattr(gate, "TRUSTED_CONFIRMED_REQUIREMENTS")
            else:
                gate.TRUSTED_CONFIRMED_REQUIREMENTS = saved_requirements
            gate.OFFICIAL_AUTHORITIES = saved_official
            gate.ALLOWED_AUTHORITIES = saved_allowed

    def test_direct_matrix_validation_repins_official_source_identity(self):
        sources = gate.validate_sources(copy.deepcopy(self.sources))
        matrix = copy.deepcopy(self.matrix)

        poisoned = copy.deepcopy(sources["snoco_legal_notice"])
        poisoned["facts"] = ["Fabricated replacement fact."]
        sources["snoco_legal_notice"] = poisoned

        with self.assertRaisesRegex(gate.GateError, "official source identity drift: snoco_legal_notice"):
            gate.validate_matrix(matrix, sources)

    def test_deleting_required_forms_is_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        matrix["requirements"] = [
            row for row in matrix["requirements"] if row["id"] != "required_forms"
        ]

        with self.assertRaisesRegex(
            gate.GateError,
            r"packet-required requirement set drift: .*required_forms",
        ):
            gate.build_receipt(self.sources, matrix)

    def test_reclassifying_references_is_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        requirement(matrix, "references")["classification"] = "INFORMATIONAL"

        with self.assertRaisesRegex(
            gate.GateError,
            "packet-gap row drift: references",
        ):
            gate.build_receipt(self.sources, matrix)

    def test_rewriting_packet_gap_text_is_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        requirement(matrix, "insurance")["requirement"] = "No insurance evidence is needed."

        with self.assertRaisesRegex(
            gate.GateError,
            "packet-gap row drift: insurance",
        ):
            gate.build_receipt(self.sources, matrix)

    def test_removing_packet_gap_source_binding_is_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        requirement(matrix, "addenda_acknowledgement")["source_ids"] = []

        with self.assertRaisesRegex(
            gate.GateError,
            "packet-gap row drift: addenda_acknowledgement",
        ):
            gate.build_receipt(self.sources, matrix)

    def test_unknown_packet_gap_cannot_expand_trusted_inventory(self):
        matrix = copy.deepcopy(self.matrix)
        matrix["requirements"].append(
            {
                "id": "invented_packet_gap",
                "classification": "MANDATORY",
                "state": "PACKET_REQUIRED",
                "source_ids": [],
                "requirement": "Caller-invented packet gap.",
            }
        )

        with self.assertRaisesRegex(
            gate.GateError,
            "untrusted packet-required requirement id: invented_packet_gap",
        ):
            gate.build_receipt(self.sources, matrix)

    def test_canonical_receipt_preserves_hold_and_full_gap_inventory(self):
        receipt = gate.build_receipt(self.sources, self.matrix)

        self.assertEqual(receipt["decision"], "HOLD_PACKET_REQUIRED")
        self.assertEqual(receipt["state"], "EVIDENCE_MATRIX_READY_PACKET_BLOCKED")
        self.assertEqual(len(receipt["packet_required_ids"]), 14)
        self.assertIn("required_forms", receipt["mandatory_packet_required_ids"])
        self.assertIn("references", receipt["mandatory_packet_required_ids"])
        self.assertIn("references", receipt["scoreable_packet_required_ids"])
        self.assertTrue(receipt["authorities"])
        self.assertTrue(all(value is False for value in receipt["authorities"].values()))
        self.assertTrue(gate.verify_receipt(receipt, self.sources, self.matrix))


if __name__ == "__main__":
    unittest.main()
