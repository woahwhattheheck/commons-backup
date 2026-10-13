import copy
import json
from pathlib import Path
import unittest

from revenue.procurement.loudoun_lims_13673.qualify import (
    QualificationError,
    compile_decision,
    validate_manifest,
    verify_decision,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "public_source_manifest.json").read_text(encoding="utf-8"))
PARTNER = json.loads((ROOT / "partner_role.json").read_text(encoding="utf-8"))


class LoudounQualificationTests(unittest.TestCase):
    def test_baseline_is_teaming_only(self):
        decision = compile_decision(MANIFEST, PARTNER)
        self.assertEqual(decision["posture"], "TEAMING_ONLY")
        self.assertEqual(
            decision["blocker"],
            "OFFICIAL_PACKAGE_AND_PRIME_CORPORATE_EVIDENCE_REQUIRED",
        )
        self.assertFalse(decision["outbound_authorized"])
        self.assertFalse(decision["submission_authorized"])
        self.assertTrue(verify_decision(MANIFEST, PARTNER, decision))

    def test_deadline_is_extension_not_old_date(self):
        validate_manifest(MANIFEST)
        self.assertEqual(
            MANIFEST["current_public_close"]["at"],
            "2026-09-18T14:00:00-04:00",
        )

    def test_official_hash_cannot_be_invented(self):
        bad = copy.deepcopy(MANIFEST)
        bad["official_attachments"][0]["sha256"] = "0" * 64
        with self.assertRaises(QualificationError):
            compile_decision(bad, PARTNER)

    def test_product_source_cannot_mint_soc2(self):
        bad = copy.deepcopy(MANIFEST)
        gate = next(g for g in bad["qualification_gates"] if g["id"] == "soc2_type_ii_or_equivalent")
        gate["evidence_status"] = "EVIDENCED"
        gate["basis"] = "INTERNAL_PRODUCT_ONLY"
        gate["evidence_refs"] = ["aquatrace_main"]
        with self.assertRaises(QualificationError):
            compile_decision(bad, PARTNER)

    def test_external_authority_fails_closed(self):
        bad = copy.deepcopy(MANIFEST)
        bad["authority"]["partner_contact"] = True
        with self.assertRaises(QualificationError):
            compile_decision(bad, PARTNER)

    def test_tampered_decision_fails_verification(self):
        decision = compile_decision(MANIFEST, PARTNER)
        decision["posture"] = "PRIME_ELIGIBLE"
        self.assertFalse(verify_decision(MANIFEST, PARTNER, decision))


if __name__ == "__main__":
    unittest.main()
