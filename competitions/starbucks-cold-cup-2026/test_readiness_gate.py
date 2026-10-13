import unittest

from readiness_gate import REQUIRED_EVIDENCE, SCHEMA, evaluate


def ready_packet():
    return {
        "schema": SCHEMA,
        "candidate": {"name": "ClearFiber Shell", "version": "pilot-1"},
        "evidence": {
            key: {"status": "verified", "references": [f"lab://{key}/report"]}
            for key in REQUIRED_EVIDENCE
        },
        "release": {
            "external_submission_authorized": True,
            "solver_identity_verified": True,
            "solver_eligibility_verified": True,
        },
    }


class ReadinessGateTests(unittest.TestCase):
    def test_complete_packet_ready(self):
        result = evaluate(ready_packet())
        self.assertTrue(result["ready"])
        self.assertEqual(result["errors"], [])

    def test_checked_in_shape_blocks_unverified(self):
        packet = ready_packet()
        packet["evidence"]["astm_d1003_haze_le_5"] = {
            "status": "unverified",
            "references": [],
        }
        result = evaluate(packet)
        self.assertFalse(result["ready"])
        self.assertTrue(any("astm_d1003_haze_le_5" in e for e in result["errors"]))

    def test_missing_hard_gate_blocks(self):
        packet = ready_packet()
        del packet["evidence"]["liquid_hold_24h"]
        result = evaluate(packet)
        self.assertFalse(result["ready"])
        self.assertTrue(any("missing evidence keys" in e for e in result["errors"]))

    def test_human_contribution_is_mandatory(self):
        packet = ready_packet()
        packet["evidence"]["substantive_human_contribution"] = {
            "status": "unverified",
            "references": ["notes://draft-only"],
        }
        self.assertFalse(evaluate(packet)["ready"])

    def test_external_submission_authority_required(self):
        packet = ready_packet()
        packet["release"]["external_submission_authorized"] = False
        self.assertFalse(evaluate(packet)["ready"])

    def test_identity_and_eligibility_are_required(self):
        for key in ("solver_identity_verified", "solver_eligibility_verified"):
            packet = ready_packet()
            packet["release"][key] = False
            self.assertFalse(evaluate(packet)["ready"])

    def test_extra_evidence_key_rejected(self):
        packet = ready_packet()
        packet["evidence"]["invented_shortcut"] = {
            "status": "verified",
            "references": ["fake://claim"],
        }
        self.assertFalse(evaluate(packet)["ready"])

    def test_bool_or_string_cannot_replace_evidence_object(self):
        for replacement in (True, "verified", [], None):
            packet = ready_packet()
            packet["evidence"]["filled_drop_1m"] = replacement
            self.assertFalse(evaluate(packet)["ready"])

    def test_empty_reference_rejected(self):
        packet = ready_packet()
        packet["evidence"]["forming_trial"]["references"] = [""]
        self.assertFalse(evaluate(packet)["ready"])

    def test_wrong_candidate_rejected(self):
        packet = ready_packet()
        packet["candidate"]["name"] = "Anything Else"
        self.assertFalse(evaluate(packet)["ready"])

    def test_unknown_top_level_key_rejected(self):
        packet = ready_packet()
        packet["trust_me"] = True
        self.assertFalse(evaluate(packet)["ready"])


if __name__ == "__main__":
    unittest.main()
