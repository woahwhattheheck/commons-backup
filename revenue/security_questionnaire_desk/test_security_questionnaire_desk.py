import unittest

try:
    from . import security_questionnaire_desk as sq
    from . import test_security_questionnaire_desk_legacy as legacy
    from ._test_questionnaire_common import fixture
except ImportError:
    import security_questionnaire_desk as sq
    import test_security_questionnaire_desk_legacy as legacy
    from _test_questionnaire_common import fixture


class DeskTests(legacy.DeskTests):
    def test_certification_reference_allows_supported_answer(self):
        data = fixture()
        question = next(row for row in data["questions"] if row["question_id"] == "q-cert")
        data["evidence"].append({
            "evidence_id": "ev-cert",
            "supports_question_id": "q-cert",
            "supports_question_source_sha256": legacy.SHA_C,
            "supports_answer_sha256": sq.answer_binding_sha256(question, "YES"),
            "claim_key": "cert.requested",
            "claim_value": "yes",
            "statement": "A current third-party report reference explicitly records the certification.",
            "kind": "CERTIFICATION_REFERENCE",
            "disclosure": "PUBLIC",
            "source_ref": "public/cert/reference",
            "source_sha256": legacy.SHA_E,
            "captured_at": "2026-09-12T14:00:00Z",
            "fresh_for_days": 30,
        })
        data["proposed_answers"][1] = {
            "question_id": "q-cert", "answer": "YES",
            "state": "SUPPORTED_PROPOSED_ANSWER", "evidence_ids": ["ev-cert"],
        }
        packet = sq.compile_packet(data, legacy.NOW)
        self.assertEqual(
            legacy.row(packet, "q-cert")["state"],
            "EVIDENCE_LINKED_PROPOSED_ANSWER",
        )

    def test_stale_owner_approval_does_not_authorize(self):
        data = fixture()
        data["owner_dispositions"] = [{
            "question_id": "q-access", "answer_generation_sha256": "f" * 64,
            "disposition": "APPROVED_FOR_RETURN",
            "reviewed_at": "2026-09-13T13:59:00Z", "reviewer_ref": "owner/review-1",
        }]
        packet = sq.compile_packet(data, legacy.NOW)
        self.assertEqual(packet["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(packet["counts"]["required_approved_for_return"], 0)
        self.assertFalse(packet["review_authority"]["owner_approval_inferred"])

    def test_exact_owner_approval_binds_generation(self):
        data = fixture()
        first = sq.compile_packet(data, legacy.NOW)
        data["owner_dispositions"] = [{
            "question_id": row["question_id"],
            "answer_generation_sha256": row["answer_generation_sha256"],
            "disposition": "APPROVED_FOR_RETURN",
            "reviewed_at": "2026-09-13T13:59:00Z",
            "reviewer_ref": f"owner/{row['question_id']}",
        } for row in first["rows"] if row["required"]]
        packet = sq.compile_packet(data, legacy.NOW)
        self.assertEqual(packet["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(packet["counts"]["required_approved_for_return"], 0)
        self.assertEqual(packet["review_authority"]["candidate_disposition_count"], 3)
        self.assertFalse(packet["review_authority"]["candidate_dispositions_are_owner_authority"])

    def test_owner_input_required_cannot_be_approved_for_return(self):
        data = fixture()
        data["proposed_answers"][0].update(
            {"state": "OWNER_INPUT_REQUIRED", "answer": "YES", "evidence_ids": []}
        )
        first = sq.compile_packet(data, legacy.NOW)
        data["owner_dispositions"] = [{
            "question_id": "q-access",
            "answer_generation_sha256": legacy.row(first, "q-access")["answer_generation_sha256"],
            "disposition": "APPROVED_FOR_RETURN",
            "reviewed_at": "2026-09-13T13:59:00Z", "reviewer_ref": "owner/q-access",
        }]
        packet = sq.compile_packet(data, legacy.NOW)
        self.assertEqual(packet["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(packet["counts"]["required_approved_for_return"], 0)
        self.assertEqual(
            legacy.row(packet, "q-access")["owner_disposition_status"],
            "UNTRUSTED_CANDIDATE_CONTEXT_IGNORED",
        )

    def test_answer_change_invalidates_owner_approval(self):
        data = fixture()
        first = sq.compile_packet(data, legacy.NOW)
        generation = legacy.row(first, "q-access")["answer_generation_sha256"]
        data["owner_dispositions"] = [{
            "question_id": "q-access", "answer_generation_sha256": generation,
            "disposition": "APPROVED_FOR_RETURN",
            "reviewed_at": "2026-09-13T13:59:00Z", "reviewer_ref": "owner/q-access",
        }]
        data["evidence"][0]["statement"] = (
            "The public policy documents restricted admin access with a revised statement."
        )
        packet = sq.compile_packet(data, legacy.NOW)
        self.assertEqual(packet["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(packet["counts"]["required_approved_for_return"], 0)
        self.assertNotEqual(
            generation, legacy.row(packet, "q-access")["answer_generation_sha256"]
        )


try:
    from .test_questionnaire_binding import BindingTests
    from .test_questionnaire_public import PublicProjectionTests
    from .test_questionnaire_publication import PublicationTests
except ImportError:
    from test_questionnaire_binding import BindingTests
    from test_questionnaire_public import PublicProjectionTests
    from test_questionnaire_publication import PublicationTests


if __name__ == "__main__":
    unittest.main()
