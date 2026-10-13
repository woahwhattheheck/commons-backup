import unittest

try:
    from . import security_questionnaire_desk as sq
    from . import test_security_questionnaire_desk_legacy as legacy
    from ._test_questionnaire_common import fixture
except ImportError:
    import security_questionnaire_desk as sq
    import test_security_questionnaire_desk_legacy as legacy
    from _test_questionnaire_common import fixture


class BindingTests(unittest.TestCase):
    def test_answer_binding_mismatch_holds(self):
        data = fixture()
        data["evidence"][0]["supports_answer_sha256"] = "0" * 64
        packet = sq.compile_packet(data, legacy.NOW)
        access = legacy.row(packet, "q-access")
        self.assertEqual(access["state"], "HOLD")
        self.assertIn("ANSWER_BINDING_MISMATCH:ev-access", access["reasons"])
        self.assertEqual(packet["status"], "HOLD")

    def test_certification_transplant_binding_holds(self):
        data = fixture()
        access_question = next(
            row for row in data["questions"] if row["question_id"] == "q-access"
        )
        data["evidence"].append({
            "evidence_id": "ev-cert-transplant",
            "supports_question_id": "q-cert",
            "supports_question_source_sha256": legacy.SHA_C,
            "supports_answer_sha256": sq.answer_binding_sha256(access_question, "YES"),
            "claim_key": "cert.other", "claim_value": "yes",
            "statement": "A reference concerns a different exact question contract.",
            "kind": "CERTIFICATION_REFERENCE", "disclosure": "PUBLIC",
            "source_ref": "public/cert/other", "source_sha256": legacy.SHA_E,
            "captured_at": "2026-09-12T14:00:00Z", "fresh_for_days": 30,
        })
        data["proposed_answers"][1] = {
            "question_id": "q-cert", "answer": "YES",
            "state": "SUPPORTED_PROPOSED_ANSWER",
            "evidence_ids": ["ev-cert-transplant"],
        }
        packet = sq.compile_packet(data, legacy.NOW)
        cert = legacy.row(packet, "q-cert")
        self.assertEqual(cert["state"], "HOLD")
        self.assertIn("ANSWER_BINDING_MISMATCH:ev-cert-transplant", cert["reasons"])

    def test_parsed_object_alias_rejected_before_snapshot(self):
        data = fixture()
        data["questions"] = tuple(data["questions"])
        with self.assertRaisesRegex(sq.DeskError, "plain JSON"):
            sq.compile_packet(data, legacy.NOW)

    def test_success_state_is_linked_not_authenticated(self):
        packet = sq.compile_packet(fixture(), legacy.NOW)
        access = legacy.row(packet, "q-access")
        self.assertEqual(access["state"], "EVIDENCE_LINKED_PROPOSED_ANSWER")
        self.assertFalse(packet["evidence_authority"]["authenticated_source_provenance"])
        self.assertIn("supports_answer_sha256", access["evidence"][0])

    def test_binding_is_order_invariant(self):
        first = fixture()
        second = fixture()
        second["questions"].reverse()
        second["evidence"].reverse()
        second["proposed_answers"].reverse()
        self.assertEqual(
            sq.canonical_bytes(sq.compile_packet(first, legacy.NOW)),
            sq.canonical_bytes(sq.compile_packet(second, legacy.NOW)),
        )
