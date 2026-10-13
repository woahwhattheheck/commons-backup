from __future__ import annotations
from unittest.mock import patch
from ._test_support import AFTER, NOW, S1, S2, ClarificationTestBase, compiler, question, raw_input


class ClarificationCompilerTests(ClarificationTestBase):
    def test_ready_packet_is_buyer_safe_and_authority_negative(self):
        output = self.compile()
        packet = self.packet(output)
        self.assertEqual("READY_FOR_OWNER_REVIEW", output.status)
        self.assertEqual(1, packet["counts"]["retained"])
        self.assertTrue(all(value is False for value in packet["authority"].values()))
        self.assertTrue(packet["classification"]["outbound_not_authorized"])
        markdown = output.markdown.decode("utf-8")
        self.assertIn("Please clarify which security evidence", markdown)
        self.assertNotIn("owner scoring strategy", markdown)
        self.assertNotIn("Ambiguity may cause", markdown)

    def test_deadline_passed_is_hold(self):
        output = self.compile(when=AFTER)
        self.assertEqual("HOLD_DEADLINE_PASSED", output.status)
        self.assertEqual("HOLD_DEADLINE_PASSED", self.packet(output)["status"])

    def test_old_verified_packet_surfaces_current_deadline_hold(self):
        output = self.compile(when=NOW)
        with patch.object(compiler, "_clock", return_value=AFTER):
            result = compiler.verify(raw_input(), output.packet, output.markdown, output.receipt)
        self.assertEqual("READY_FOR_OWNER_REVIEW", result["recorded_status"])
        self.assertEqual("HOLD_DEADLINE_PASSED", result["current_status"])
        self.assertTrue(all(value is False for value in result["authority"].values()))

    def test_missing_timezone_is_source_conflict(self):
        raw = self.mutate(raw_input(), lambda v: v["question_deadlines"][0].__setitem__("value", "2099-12-20T17:00:00"))
        output = self.compile(raw)
        packet = self.packet(output)
        self.assertEqual("HOLD_SOURCE_CONFLICT", output.status)
        self.assertTrue(any(x.startswith("DEADLINE_TIMEZONE_OR_FORMAT") for x in packet["source_conflicts"]))

    def test_candidate_source_digest_drift_is_source_conflict(self):
        raw = self.mutate(raw_input(), lambda v: v["candidate_questions"][0].__setitem__("source_sha256", "9" * 64))
        output = self.compile(raw)
        self.assertEqual("HOLD_SOURCE_CONFLICT", output.status)
        self.assertTrue(any("QUESTION_SOURCE_DRIFT" in x or "QUESTION_GAP_BINDING_DRIFT" in x for x in self.packet(output)["source_conflicts"]))

    def test_invented_gap_is_source_conflict(self):
        raw = self.mutate(raw_input(), lambda v: v["candidate_questions"][0].__setitem__("gap_id", "human-evidence:invented"))
        output = self.compile(raw)
        self.assertEqual("HOLD_SOURCE_CONFLICT", output.status)
        self.assertTrue(any(x.startswith("UNKNOWN_GAP") for x in self.packet(output)["source_conflicts"]))

    def test_later_amendment_resolution_suppresses_answered_question(self):
        def change(v):
            v["resolutions"].append({
                "resolution_id": "answer-1",
                "intent_id": "intent-security-proof",
                "gap_id": "human-evidence:req-a",
                "source_id": "amend-1",
                "source_sha256": S2,
                "section_id": "sec-answer-a",
                "answer_summary": "Amendment 1 specifies the accepted evidence types.",
            })
        output = self.compile(self.mutate(raw_input(), change))
        packet = self.packet(output)
        self.assertEqual("READY_FOR_OWNER_REVIEW", output.status)
        self.assertEqual([], packet["questions"])
        self.assertEqual("ANSWERED_BY_LATER_AMENDMENT", packet["suppressed"][0]["reason"])
        self.assertEqual("answer-1", packet["suppressed"][0]["resolution_id"])

    def test_later_solicitation_cannot_masquerade_as_amendment_resolution(self):
        s3 = "3" * 64

        def change(v):
            v["solicitation_pack"]["sources"].append({
                "source_id": "sol-2",
                "source_class": "BUYER_OFFICIAL",
                "kind": "SOLICITATION",
                "identity": "buyer-rfp-v2",
                "ref": "buyer-rfp-v2.pdf",
                "sha256": s3,
                "captured_at": "2026-09-16T11:45:00Z",
                "sequence": 3,
                "supersedes_sources": [],
                "supersedes_lineages": [],
                "requirements": [],
                "deadline": None,
                "attachments": [],
            })
            v["resolutions"].append({
                "resolution_id": "answer-wrong-doc-kind",
                "intent_id": "intent-security-proof",
                "gap_id": "human-evidence:req-a",
                "source_id": "sol-2",
                "source_sha256": s3,
                "section_id": "sec-answer-wrong",
                "answer_summary": "A later solicitation generation must not erase the unresolved question.",
            })

        output = self.compile(self.mutate(raw_input(), change))
        packet = self.packet(output)
        self.assertEqual("HOLD_SOURCE_CONFLICT", output.status)
        self.assertIn(
            "RESOLUTION_SOURCE_NOT_AMENDMENT:answer-wrong-doc-kind",
            packet["source_conflicts"],
        )
        self.assertFalse(any(row.get("reason") == "ANSWERED_BY_LATER_AMENDMENT" for row in packet["suppressed"]))

    def test_same_generation_amendment_resolution_does_not_suppress(self):
        def change(v):
            v["candidate_questions"] = [
                question(
                    qid="q-b-1",
                    intent="intent-delivery-proof",
                    gap_id="human-evidence:req-b",
                    qclass="SCORED_AMBIGUITY",
                    text="Please clarify the amended delivery evidence expected for scoring.",
                    source_id="amend-1",
                    source_sha=S2,
                    section="sec-b2",
                )
            ]
            v["resolutions"].append({
                "resolution_id": "answer-same-amendment",
                "intent_id": "intent-delivery-proof",
                "gap_id": "human-evidence:req-b",
                "source_id": "amend-1",
                "source_sha256": S2,
                "section_id": "sec-answer-same",
                "answer_summary": "Same-generation amendment note.",
            })

        output = self.compile(self.mutate(raw_input(), change))
        packet = self.packet(output)
        self.assertEqual("READY_FOR_OWNER_REVIEW", output.status)
        self.assertEqual(1, packet["counts"]["retained"])
        self.assertFalse(any(row.get("reason") == "ANSWERED_BY_LATER_AMENDMENT" for row in packet["suppressed"]))
