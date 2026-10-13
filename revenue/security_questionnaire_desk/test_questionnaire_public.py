import copy
import unittest

try:
    from . import security_questionnaire_desk as sq
    from . import test_security_questionnaire_desk_legacy as legacy
    from ._test_questionnaire_common import fixture
except ImportError:
    import security_questionnaire_desk as sq
    import test_security_questionnaire_desk_legacy as legacy
    from _test_questionnaire_common import fixture


class PublicProjectionTests(unittest.TestCase):
    def test_private_stale_failure_is_publicly_redacted(self):
        data = fixture()
        private = next(row for row in data["evidence"] if row["disclosure"] == "NON_PUBLIC")
        private["fresh_for_days"] = 0
        packet = sq.compile_packet(data, legacy.NOW)
        public_blob = sq.render_public_safe_json(packet)
        self.assertNotIn("A retention practice is documented", public_blob)
        self.assertNotIn(private["evidence_id"], public_blob)
        self.assertNotIn(private["claim_key"], public_blob)
        public = next(
            row for row in packet["public_safe_projection"]["rows"]
            if row["question_id"] == "q-retention"
        )
        self.assertEqual(public["state"], "UNMEASURED")
        self.assertEqual(public["reasons"], ["NON_PUBLIC_EVIDENCE_STRIPPED"])

    def test_private_conflict_failure_is_publicly_redacted(self):
        data = fixture()
        private = next(row for row in data["evidence"] if row["disclosure"] == "NON_PUBLIC")
        conflict = copy.deepcopy(private)
        conflict.update({
            "evidence_id": "ev-retention-private-conflict",
            "claim_value": "not-documented", "source_sha256": legacy.SHA_E,
        })
        data["evidence"].append(conflict)
        answer = next(
            row for row in data["proposed_answers"] if row["question_id"] == "q-retention"
        )
        answer["evidence_ids"].append(conflict["evidence_id"])
        public_blob = sq.render_public_safe_json(sq.compile_packet(data, legacy.NOW))
        self.assertNotIn(private["evidence_id"], public_blob)
        self.assertNotIn(conflict["evidence_id"], public_blob)
        self.assertNotIn(private["claim_key"], public_blob)

    def test_private_owner_input_is_publicly_redacted(self):
        data = fixture()
        answer = next(
            row for row in data["proposed_answers"] if row["question_id"] == "q-retention"
        )
        answer["state"] = "OWNER_INPUT_REQUIRED"
        answer["answer"] = "Private owner context that must not enter public bytes."
        public_blob = sq.render_public_safe_json(sq.compile_packet(data, legacy.NOW))
        self.assertNotIn("Private owner context", public_blob)
        self.assertNotIn("ev-retention-private", public_blob)

    def test_public_status_never_claims_owner_approval(self):
        packet = sq.compile_packet(fixture(), legacy.NOW)
        self.assertEqual(
            packet["public_safe_projection"]["status"],
            "PUBLIC_OWNER_REVIEW_REQUIRED",
        )
        self.assertNotIn("OWNER_APPROVED", sq.render_public_safe_json(packet))
