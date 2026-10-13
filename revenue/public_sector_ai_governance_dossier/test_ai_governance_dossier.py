import copy
import json
import tempfile
import unittest
from pathlib import Path

import ai_governance_dossier as gov


def base_packet():
    return {
        "schema_version": 1,
        "organization": {"name": "Synthetic Water Utility", "sector": "public wastewater"},
        "vendors": [
            {"id": "v-internal", "name": "Internal Analytics", "evidence_refs": ["ev-provenance"]},
        ],
        "models": [
            {"id": "m-anomaly", "name": "Anomaly Model", "vendor_id": "v-internal", "version": "1.0", "evidence_refs": ["ev-provenance"]},
        ],
        "use_cases": [
            {
                "id": "uc-anomaly",
                "name": "Wastewater anomaly recommendation",
                "kind": "operational",
                "stage": "pilot",
                "decision_authority": "recommendation",
                "operational_impact": "infrastructure",
                "recoverability": "bounded",
                "external_publication": False,
                "shadow_ai": False,
                "data_classes": ["operational_critical", "public_record"],
                "vendor_id": "v-internal",
                "model_id": "m-anomaly",
            }
        ],
        "evidence": [
            {
                "id": "ev-provenance",
                "status": "verified",
                "authority": "internal_record",
                "reference": "repo://model-registry/m-anomaly/1.0",
                "sha256": "a" * 64,
                "use_case_ids": ["uc-anomaly"],
                "control_ids": ["VENDOR_MODEL_PROVENANCE"],
                "private_notes": "must never appear in output",
            }
        ],
    }


def satisfy_all(packet):
    uc = packet["use_cases"][0]
    controls = gov.required_controls(uc)
    preferred = {
        "PUBLIC_RECORDS_REVIEW": "legal_approved",
        "LEGAL_POLICY_REVIEW": "legal_approved",
        "DATA_SOVEREIGNTY_PRIVACY_REVIEW": "legal_approved",
        "SECURITY_REVIEW": "security_approved",
        "SAFETY_HAZARD_REVIEW": "independent_review",
        "INDEPENDENT_VALIDATION": "independent_review",
        "PRODUCTION_RELEASE_GATE": "owner_approved",
        "EXTERNAL_PUBLICATION_APPROVAL": "owner_approved",
        "SHADOW_AI_DISPOSITION": "owner_approved",
    }
    existing = {e["id"] for e in packet["evidence"]}
    for control in controls:
        if control == "VENDOR_MODEL_PROVENANCE":
            continue
        authority = preferred.get(control, sorted(gov.CONTROL_AUTHORITIES[control])[0])
        eid = f"ev-{control.lower()}"
        if eid in existing:
            continue
        packet["evidence"].append({
            "id": eid,
            "status": "verified",
            "authority": authority,
            "reference": f"synthetic://{control.lower()}",
            "use_case_ids": [uc["id"]],
            "control_ids": [control],
        })
    return packet


class GovernanceDossierTests(unittest.TestCase):
    def test_deterministic_and_private_notes_are_excluded(self):
        packet = base_packet()
        first = gov.compile_dossier(packet)
        second = gov.compile_dossier(copy.deepcopy(packet))
        self.assertEqual(first, second)
        rendered = json.dumps(first, sort_keys=True)
        self.assertNotIn("must never appear", rendered)
        self.assertFalse(first["summary"]["autonomous_authority"])
        self.assertFalse(first["summary"]["production_authorized"])

    def test_operational_public_record_case_escalates_and_adds_conditional_controls(self):
        packet = base_packet()
        result = gov.evaluate_use_case(packet["use_cases"][0], packet["evidence"])
        self.assertGreaterEqual(result.control_tier, 3)
        self.assertIn("PUBLIC_RECORDS_REVIEW", result.required_controls)
        self.assertIn("RECORDS_RETENTION", result.required_controls)
        self.assertIn("OPERATIONAL_FALLBACK", result.required_controls)
        self.assertEqual(result.disposition, "HOLD_CONTROLS")

    def test_wrong_authority_cannot_satisfy_public_records_review(self):
        packet = base_packet()
        packet["evidence"].append({
            "id": "ev-public-records-wrong",
            "status": "verified",
            "authority": "owner_approved",
            "reference": "synthetic://owner-note",
            "use_case_ids": ["uc-anomaly"],
            "control_ids": ["PUBLIC_RECORDS_REVIEW"],
        })
        result = gov.evaluate_control(packet["evidence"], "uc-anomaly", "PUBLIC_RECORDS_REVIEW")
        self.assertEqual(result.status, "AUTHORITY_MISMATCH")
        self.assertEqual(result.authority_mismatches, ("ev-public-records-wrong",))

    def test_full_evidence_reaches_control_ready_but_never_authorizes(self):
        packet = satisfy_all(base_packet())
        dossier = gov.compile_dossier(packet)
        uc = dossier["use_cases"][0]
        self.assertEqual(uc["blocking_controls"], [])
        self.assertEqual(uc["disposition"], "CONTROL_READY_OWNER_DECISION")
        self.assertTrue(dossier["summary"]["all_controls_satisfied"])
        self.assertFalse(dossier["summary"]["production_authorized"])
        self.assertTrue(dossier["authority_boundary"]["owner_decision_required"])

    def test_shadow_ai_requires_disposition_and_still_does_not_authorize(self):
        packet = base_packet()
        packet["use_cases"][0]["shadow_ai"] = True
        dossier = gov.compile_dossier(packet)
        self.assertEqual(dossier["shadow_ai"][0]["disposition"], "UNSANCTIONED_REQUIRES_OWNER_REVIEW")
        packet = satisfy_all(packet)
        dossier2 = gov.compile_dossier(packet)
        self.assertEqual(dossier2["shadow_ai"][0]["disposition"], "DISPOSITION_RECORDED_NOT_AUTHORIZED")
        self.assertFalse(dossier2["summary"]["production_authorized"])

    def test_safety_critical_case_requires_independent_validation_and_fail_safe(self):
        packet = base_packet()
        uc = packet["use_cases"][0]
        uc["decision_authority"] = "automated_safety_critical"
        uc["operational_impact"] = "safety_critical"
        uc["recoverability"] = "irreversible"
        controls = gov.required_controls(uc)
        self.assertEqual(gov.control_tier(uc), 4)
        self.assertIn("INDEPENDENT_VALIDATION", controls)
        self.assertIn("FAIL_SAFE", controls)
        self.assertIn("SAFETY_HAZARD_REVIEW", controls)
        self.assertIn("HUMAN_OVERRIDE", controls)

    def test_missing_model_or_vendor_fails_closed(self):
        packet = base_packet()
        packet["use_cases"][0]["model_id"] = "m-does-not-exist"
        with self.assertRaisesRegex(ValueError, "unknown model_id"):
            gov.compile_dossier(packet)
        packet = base_packet()
        packet["models"][0]["vendor_id"] = "v-missing"
        with self.assertRaisesRegex(ValueError, "unknown vendor_id"):
            gov.compile_dossier(packet)

    def test_duplicate_and_unknown_vocabulary_fail_closed(self):
        packet = base_packet()
        packet["evidence"].append(copy.deepcopy(packet["evidence"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate evidence id"):
            gov.compile_dossier(packet)
        packet = base_packet()
        packet["use_cases"][0]["decision_authority"] = "magic"
        with self.assertRaisesRegex(ValueError, "invalid value"):
            gov.compile_dossier(packet)

    def test_boolean_aliases_are_rejected(self):
        packet = base_packet()
        packet["use_cases"][0]["external_publication"] = 1
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            gov.compile_dossier(packet)
        packet = base_packet()
        packet["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "schema_version"):
            gov.compile_dossier(packet)

    def test_verify_detects_tampering(self):
        packet = base_packet()
        dossier = gov.compile_dossier(packet)
        ok, _ = gov.verify_dossier(packet, dossier)
        self.assertTrue(ok)
        dossier["summary"]["production_authorized"] = True
        ok, message = gov.verify_dossier(packet, dossier)
        self.assertFalse(ok)
        self.assertIn("does not match", message)

    def test_cli_round_trip_and_tamper_exit_code(self):
        packet = base_packet()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp = root / "packet.json"
            out = root / "dossier.json"
            md = root / "dossier.md"
            inp.write_text(json.dumps(packet), encoding="utf-8")
            self.assertEqual(gov.main(["compile", "--input", str(inp), "--json-out", str(out), "--markdown-out", str(md)]), 0)
            self.assertEqual(gov.main(["verify", "--input", str(inp), "--dossier", str(out)]), 0)
            tampered = json.loads(out.read_text(encoding="utf-8"))
            tampered["authority_boundary"]["production_release_not_inferred"] = False
            out.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertEqual(gov.main(["verify", "--input", str(inp), "--dossier", str(out)]), 3)

    def test_fail_on_hold_exit_code(self):
        packet = base_packet()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp = root / "packet.json"
            out = root / "dossier.json"
            inp.write_text(json.dumps(packet), encoding="utf-8")
            self.assertEqual(gov.main(["compile", "--input", str(inp), "--json-out", str(out), "--fail-on-hold"]), 2)


if __name__ == "__main__":
    unittest.main()
