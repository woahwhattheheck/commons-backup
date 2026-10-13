import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import security_questionnaire_desk as sq

NOW = datetime(2026, 9, 13, 14, 0, 0, tzinfo=timezone.utc)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


def fixture():
    return {
        "schema_version": 1,
        "questionnaire_id": "sq-demo-001",
        "questionnaire_source_ref": "buyer-file/sq-demo-001",
        "questionnaire_sha256": SHA_A,
        "questions": [
            {
                "question_id": "q-access",
                "section": "Access Control",
                "prompt": "Is administrative access restricted by an explicit policy?",
                "mode": "BOOLEAN",
                "assurance_kind": "GENERAL",
                "required": True,
                "allowed_values": [],
                "source_ref": "buyer-row/q-access",
                "source_sha256": SHA_B,
            },
            {
                "question_id": "q-cert",
                "section": "Assurance",
                "prompt": "Do you hold the requested third-party certification?",
                "mode": "BOOLEAN",
                "assurance_kind": "CERTIFICATION",
                "required": True,
                "allowed_values": [],
                "source_ref": "buyer-row/q-cert",
                "source_sha256": SHA_C,
            },
            {
                "question_id": "q-retention",
                "section": "Data",
                "prompt": "Describe the documented retention practice.",
                "mode": "TEXT",
                "assurance_kind": "GENERAL",
                "required": True,
                "allowed_values": [],
                "source_ref": "buyer-row/q-retention",
                "source_sha256": SHA_D,
            },
        ],
        "evidence": [
            {
                "evidence_id": "ev-access",
                "supports_question_id": "q-access",
                "supports_question_source_sha256": SHA_B,
                "claim_key": "access.policy",
                "claim_value": "yes",
                "statement": "The public policy documents restricted administrative access.",
                "kind": "PUBLIC_POLICY",
                "disclosure": "PUBLIC",
                "source_ref": "commons/policy/access",
                "source_sha256": SHA_B,
                "captured_at": "2026-09-12T14:00:00Z",
                "fresh_for_days": 30,
            },
            {
                "evidence_id": "ev-retention-private",
                "supports_question_id": "q-retention",
                "supports_question_source_sha256": SHA_D,
                "claim_key": "data.retention",
                "claim_value": "documented",
                "statement": "Owner-attested retention practice is documented internally.",
                "kind": "OWNER_ATTESTATION",
                "disclosure": "NON_PUBLIC",
                "source_ref": "owner-record/retention-v1",
                "source_sha256": SHA_C,
                "captured_at": "2026-09-12T14:00:00Z",
                "fresh_for_days": 30,
            },
        ],
        "proposed_answers": [
            {
                "question_id": "q-access",
                "answer": "YES",
                "state": "SUPPORTED_PROPOSED_ANSWER",
                "evidence_ids": ["ev-access"],
            },
            {
                "question_id": "q-cert",
                "answer": "UNMEASURED",
                "state": "UNMEASURED",
                "evidence_ids": [],
            },
            {
                "question_id": "q-retention",
                "answer": "A retention practice is documented for owner review.",
                "state": "SUPPORTED_PROPOSED_ANSWER",
                "evidence_ids": ["ev-retention-private"],
            },
        ],
        "owner_dispositions": [],
    }


def row(packet, qid):
    return next(r for r in packet["rows"] if r["question_id"] == qid)


class DeskTests(unittest.TestCase):
    def test_happy_compile(self):
        packet = sq.compile_packet(fixture(), NOW)
        self.assertEqual(packet["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(packet["counts"], {"questions": 3, "required": 3, "holds": 0, "required_approved_for_return": 0})
        self.assertTrue(all(v is False for v in packet["authority"].values()))
        self.assertEqual(len(packet["receipt_sha256"]), 64)

    def test_order_invariant_questions_evidence_answers(self):
        a = fixture()
        b = fixture()
        b["questions"].reverse()
        b["evidence"].reverse()
        b["proposed_answers"].reverse()
        self.assertEqual(sq.canonical_bytes(sq.compile_packet(a, NOW)), sq.canonical_bytes(sq.compile_packet(b, NOW)))

    def test_deterministic_repeat(self):
        a = sq.compile_packet(fixture(), NOW)
        b = sq.compile_packet(copy.deepcopy(fixture()), NOW)
        self.assertEqual(a, b)

    def test_required_answers_must_cover_exactly(self):
        data = fixture()
        data["proposed_answers"].pop()
        with self.assertRaisesRegex(sq.DeskError, "cover questions exactly"):
            sq.compile_packet(data, NOW)

    def test_duplicate_question_id_rejected(self):
        data = fixture()
        data["questions"].append(copy.deepcopy(data["questions"][0]))
        with self.assertRaisesRegex(sq.DeskError, "duplicate identity"):
            sq.compile_packet(data, NOW)

    def test_duplicate_evidence_id_rejected(self):
        data = fixture()
        data["evidence"].append(copy.deepcopy(data["evidence"][0]))
        with self.assertRaisesRegex(sq.DeskError, "duplicate identity"):
            sq.compile_packet(data, NOW)

    def test_unknown_field_rejected(self):
        data = fixture()
        data["questions"][0]["surprise"] = True
        with self.assertRaisesRegex(sq.DeskError, "key mismatch"):
            sq.compile_packet(data, NOW)

    def test_bool_as_int_rejected(self):
        data = fixture()
        data["evidence"][0]["fresh_for_days"] = True
        with self.assertRaisesRegex(sq.DeskError, "expected integer"):
            sq.compile_packet(data, NOW)

    def test_float_json_rejected(self):
        with self.assertRaisesRegex(sq.DeskError, "floats are not accepted"):
            sq.loads_strict('{"schema_version":1.0}')

    def test_oversized_json_integer_rejected(self):
        with self.assertRaisesRegex(sq.DeskError, "token too long|safe range"):
            sq.loads_strict('{"n":99999999999999999}')

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(sq.DeskError, "duplicate JSON key"):
            sq.loads_strict('{"a":1,"a":2}')

    def test_control_text_rejected(self):
        data = fixture()
        data["questions"][0]["prompt"] = "bad\u0007prompt"
        with self.assertRaisesRegex(sq.DeskError, "control character"):
            sq.compile_packet(data, NOW)

    def test_email_pii_rejected(self):
        data = fixture()
        data["evidence"][0]["statement"] = "Contact alice@example.com for proof."
        with self.assertRaisesRegex(sq.DeskError, "PII"):
            sq.compile_packet(data, NOW)

    def test_secret_shape_rejected(self):
        data = fixture()
        data["evidence"][0]["statement"] = "api_key=abcdefghijklmnopqrstuvwx"
        with self.assertRaisesRegex(sq.DeskError, "secret-shaped"):
            sq.compile_packet(data, NOW)

    def test_supported_requires_evidence(self):
        data = fixture()
        data["proposed_answers"][0]["evidence_ids"] = []
        with self.assertRaisesRegex(sq.DeskError, "requires evidence"):
            sq.compile_packet(data, NOW)

    def test_unsupported_certification_holds(self):
        data = fixture()
        data["proposed_answers"][1] = {
            "question_id": "q-cert",
            "answer": "YES",
            "state": "SUPPORTED_PROPOSED_ANSWER",
            "evidence_ids": ["ev-access"],
        }
        packet = sq.compile_packet(data, NOW)
        cert = row(packet, "q-cert")
        self.assertEqual(cert["state"], "HOLD")
        self.assertIn("CERTIFICATION_REFERENCE_REQUIRED", cert["reasons"])
        self.assertEqual(packet["status"], "HOLD")

    def test_certification_reference_allows_supported_answer(self):
        data = fixture()
        data["evidence"].append({
            "evidence_id": "ev-cert",
            "supports_question_id": "q-cert",
            "supports_question_source_sha256": SHA_C,
            "claim_key": "cert.requested",
            "claim_value": "yes",
            "statement": "A current third-party report reference explicitly records the certification.",
            "kind": "CERTIFICATION_REFERENCE",
            "disclosure": "PUBLIC",
            "source_ref": "public/cert/reference",
            "source_sha256": SHA_E,
            "captured_at": "2026-09-12T14:00:00Z",
            "fresh_for_days": 30,
        })
        data["proposed_answers"][1] = {"question_id": "q-cert", "answer": "YES", "state": "SUPPORTED_PROPOSED_ANSWER", "evidence_ids": ["ev-cert"]}
        packet = sq.compile_packet(data, NOW)
        self.assertEqual(row(packet, "q-cert")["state"], "SUPPORTED_PROPOSED_ANSWER")

    def test_stale_evidence_holds(self):
        data = fixture()
        data["evidence"][0]["fresh_for_days"] = 0
        packet = sq.compile_packet(data, NOW)
        access = row(packet, "q-access")
        self.assertEqual(access["state"], "HOLD")
        self.assertIn("STALE_EVIDENCE:ev-access", access["reasons"])

    def test_future_evidence_holds(self):
        data = fixture()
        data["evidence"][0]["captured_at"] = "2026-09-14T14:00:00Z"
        packet = sq.compile_packet(data, NOW)
        self.assertIn("FUTURE_EVIDENCE:ev-access", row(packet, "q-access")["reasons"])

    def test_conflicting_evidence_holds(self):
        data = fixture()
        conflict = copy.deepcopy(data["evidence"][0])
        conflict.update({"evidence_id": "ev-access-no", "claim_value": "no", "source_sha256": SHA_E})
        data["evidence"].append(conflict)
        data["proposed_answers"][0]["evidence_ids"].append("ev-access-no")
        packet = sq.compile_packet(data, NOW)
        self.assertIn("CONFLICTING_EVIDENCE:access.policy", row(packet, "q-access")["reasons"])

    def test_cross_question_evidence_scope_holds(self):
        data = fixture()
        data["proposed_answers"][2]["evidence_ids"] = ["ev-access"]
        packet = sq.compile_packet(data, NOW)
        retention = row(packet, "q-retention")
        self.assertEqual(retention["state"], "HOLD")
        self.assertIn("EVIDENCE_SCOPE_MISMATCH:ev-access", retention["reasons"])

    def test_cross_question_unknown_evidence_rejected(self):
        data = fixture()
        data["proposed_answers"][0]["evidence_ids"] = ["no-such-evidence"]
        with self.assertRaisesRegex(sq.DeskError, "unknown evidence"):
            sq.compile_packet(data, NOW)

    def test_boolean_answer_shape(self):
        data = fixture()
        data["proposed_answers"][0]["answer"] = "MAYBE"
        with self.assertRaisesRegex(sq.DeskError, "BOOLEAN"):
            sq.compile_packet(data, NOW)

    def test_private_evidence_stripped_from_public_projection(self):
        packet = sq.compile_packet(fixture(), NOW)
        public = next(r for r in packet["public_safe_projection"]["rows"] if r["question_id"] == "q-retention")
        self.assertEqual(public["state"], "UNMEASURED")
        self.assertEqual(public["answer"], "UNMEASURED")
        self.assertEqual(public["public_evidence"], [])
        blob = sq.render_public_safe_json(packet)
        self.assertNotIn("Owner-attested", blob)
        self.assertNotIn("owner-record/retention-v1", blob)

    def test_public_evidence_retained_in_public_projection(self):
        packet = sq.compile_packet(fixture(), NOW)
        public = next(r for r in packet["public_safe_projection"]["rows"] if r["question_id"] == "q-access")
        self.assertEqual(public["answer"], "YES")
        self.assertEqual(public["public_evidence"][0]["evidence_id"], "ev-access")

    def test_stale_owner_approval_does_not_authorize(self):
        data = fixture()
        provisional = sq.compile_packet(data, NOW)
        data["owner_dispositions"] = [{
            "question_id": "q-access",
            "answer_generation_sha256": "f" * 64,
            "disposition": "APPROVED_FOR_RETURN",
            "reviewed_at": "2026-09-13T13:59:00Z",
            "reviewer_ref": "owner/review-1",
        }]
        packet = sq.compile_packet(data, NOW)
        self.assertEqual(row(packet, "q-access")["owner_disposition_status"], "STALE_GENERATION")
        self.assertEqual(packet["counts"]["required_approved_for_return"], 0)
        self.assertNotEqual(row(provisional, "q-access")["answer_generation_sha256"], "f" * 64)

    def test_exact_owner_approval_binds_generation(self):
        data = fixture()
        first = sq.compile_packet(data, NOW)
        data["owner_dispositions"] = [
            {
                "question_id": r["question_id"],
                "answer_generation_sha256": r["answer_generation_sha256"],
                "disposition": "APPROVED_FOR_RETURN",
                "reviewed_at": "2026-09-13T13:59:00Z",
                "reviewer_ref": f"owner/{r['question_id']}",
            }
            for r in first["rows"] if r["required"]
        ]
        packet = sq.compile_packet(data, NOW)
        self.assertEqual(packet["status"], "OWNER_APPROVED_RETURN_SET")
        self.assertEqual(packet["counts"]["required_approved_for_return"], 3)

    def test_owner_input_required_cannot_be_approved_for_return(self):
        data = fixture()
        data["proposed_answers"][0]["state"] = "OWNER_INPUT_REQUIRED"
        data["proposed_answers"][0]["answer"] = "YES"
        data["proposed_answers"][0]["evidence_ids"] = []
        first = sq.compile_packet(data, NOW)
        gen = row(first, "q-access")["answer_generation_sha256"]
        data["owner_dispositions"] = [{
            "question_id": "q-access",
            "answer_generation_sha256": gen,
            "disposition": "APPROVED_FOR_RETURN",
            "reviewed_at": "2026-09-13T13:59:00Z",
            "reviewer_ref": "owner/q-access",
        }]
        packet = sq.compile_packet(data, NOW)
        self.assertEqual(row(packet, "q-access")["owner_disposition_status"], "INVALID_APPROVAL_REQUIRES_RESOLUTION")
        self.assertEqual(packet["counts"]["required_approved_for_return"], 0)
        self.assertNotEqual(packet["status"], "OWNER_APPROVED_RETURN_SET")

    def test_answer_change_invalidates_owner_approval(self):
        data = fixture()
        first = sq.compile_packet(data, NOW)
        gen = row(first, "q-access")["answer_generation_sha256"]
        data["owner_dispositions"] = [{"question_id": "q-access", "answer_generation_sha256": gen, "disposition": "APPROVED_FOR_RETURN", "reviewed_at": "2026-09-13T13:59:00Z", "reviewer_ref": "owner/q-access"}]
        data["evidence"][0]["statement"] = "The public policy documents restricted admin access with a revised statement."
        packet = sq.compile_packet(data, NOW)
        self.assertEqual(row(packet, "q-access")["owner_disposition_status"], "STALE_GENERATION")

    def test_receipt_tamper_rejected(self):
        data = fixture()
        packet = sq.compile_packet(data, NOW)
        packet["rows"][0]["answer"] = "NO"
        with self.assertRaisesRegex(sq.DeskError, "receipt mismatch"):
            sq.verify_packet(data, packet, NOW)

    def test_input_tamper_rejected_by_verify(self):
        data = fixture()
        packet = sq.compile_packet(data, NOW)
        changed = copy.deepcopy(data)
        changed["questions"][0]["prompt"] = "Is administrative access restricted according to policy?"
        with self.assertRaisesRegex(sq.DeskError, "does not match exact inputs"):
            sq.verify_packet(changed, packet, NOW)

    def test_verify_later_before_expiry_passes(self):
        data = fixture()
        packet = sq.compile_packet(data, NOW)
        result = sq.verify_packet(data, packet, NOW + timedelta(days=1))
        self.assertTrue(result["verified"])
        self.assertEqual(result["verified_at"], "2026-09-14T14:00:00Z")

    def test_verify_after_evidence_expiry_rejects(self):
        data = fixture()
        packet = sq.compile_packet(data, NOW)
        with self.assertRaisesRegex(sq.DeskError, "no longer current"):
            sq.verify_packet(data, packet, NOW + timedelta(days=31))

    def test_verify_rejects_future_packet_time(self):
        data = fixture()
        packet = sq.compile_packet(data, NOW)
        with self.assertRaisesRegex(sq.DeskError, "trusted future"):
            sq.verify_packet(data, packet, NOW - timedelta(seconds=1))

    def test_artifacts_deterministic(self):
        packet = sq.compile_packet(fixture(), NOW)
        a = sq.artifact_bytes(packet)
        b = sq.artifact_bytes(copy.deepcopy(packet))
        self.assertEqual(a, b)
        self.assertIn(b"offline owner-review artifact", a["review.md"])

    def test_publish_create_exclusive(self):
        packet = sq.compile_packet(fixture(), NOW)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            paths = sq.publish_artifacts(packet, out)
            self.assertEqual(len(paths), 5)
            with self.assertRaisesRegex(sq.DeskError, "refusing existing output"):
                sq.publish_artifacts(packet, out)

    @unittest.skipIf(os.name == "nt", "symlink creation may require privilege on Windows")
    def test_publish_refuses_final_symlink(self):
        packet = sq.compile_packet(fixture(), NOW)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            out.mkdir()
            sentinel = Path(td) / "sentinel"
            sentinel.write_text("safe")
            (out / "packet.json").symlink_to(sentinel)
            with self.assertRaisesRegex(sq.DeskError, "final symlink"):
                sq.publish_artifacts(packet, out)
            self.assertEqual(sentinel.read_text(), "safe")

    @unittest.skipIf(os.name == "nt", "symlink creation may require privilege on Windows")
    def test_input_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "real.json"
            target.write_text(json.dumps(fixture()))
            link = Path(td) / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(sq.DeskError, "non-symlink"):
                sq.load_json_file(link)

    def test_cli_has_no_as_of_override(self):
        parser = sq.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["compile", "in.json", "out", "--as-of", "2020-01-01T00:00:00Z"])

    def test_cli_compile_and_verify_same_second_contract(self):
        # Library path is deterministic; production CLI clock behavior is smoke-tested for no override.
        data = fixture()
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "input.json"
            inp.write_text(json.dumps(data, sort_keys=True))
            out = Path(td) / "out"
            rc = sq.main(["compile", str(inp), str(out)])
            self.assertIn(rc, (0, 2))
            packet = sq.load_json_file(out / "packet.json")
            self.assertIn("as_of", packet)
            self.assertTrue((out / "public-safe.json").exists())


if __name__ == "__main__":
    unittest.main()
