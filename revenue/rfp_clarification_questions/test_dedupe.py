from __future__ import annotations
from ._test_support import S2, ClarificationTestBase, question, raw_input


class ClarificationDedupeTests(ClarificationTestBase):
    def test_semantic_intent_deduplicates_paraphrases(self):
        def change(v):
            v["candidate_questions"].append(question(
                qid="q-a-2",
                priority=2,
                text="Which security artifacts must accompany the mandatory response?",
            ))
        packet = self.packet(self.compile(self.mutate(raw_input(), change)))
        self.assertEqual(1, packet["counts"]["retained"])
        self.assertEqual(1, packet["counts"]["suppressed"])
        self.assertEqual(["q-a-1", "q-a-2"], packet["questions"][0]["merged_question_ids"])
        self.assertEqual("SEMANTIC_DUPLICATE", packet["suppressed"][0]["reason"])

    def test_internal_only_and_leaky_question_are_suppressed_without_leakage(self):
        def change(v):
            v["candidate_questions"] = [
                question(qid="q-private", safe=False, text="Should not project"),
                question(qid="q-secret", intent="intent-secret", text="Please send details to buyer@example.com"),
            ]
        output = self.compile(self.mutate(raw_input(), change))
        packet = self.packet(output)
        reasons = {row["reason"] for row in packet["suppressed"]}
        self.assertEqual({"INTERNAL_ONLY_NOT_PROJECTED", "BUYER_SAFE_LEAKAGE_GUARD"}, reasons)
        self.assertNotIn("buyer@example.com", output.markdown.decode("utf-8"))

    def test_multiple_active_question_deadlines_hold_source_conflict(self):
        def change(v):
            v["question_deadlines"].append({
                "deadline_id": "questions-v2",
                "source_id": "amend-1",
                "source_sha256": S2,
                "section_id": "sec-questions-2",
                "value": "2099-12-21T17:00:00-05:00",
                "supersedes_deadline_ids": [],
            })
        output = self.compile(self.mutate(raw_input(), change))
        self.assertEqual("HOLD_SOURCE_CONFLICT", output.status)
        self.assertIn("ACTIVE_QUESTION_DEADLINE_COUNT:2", self.packet(output)["source_conflicts"])

    def test_contradictory_same_source_resolutions_hold(self):
        def change(v):
            for rid, text in [("r1", "Answer A"), ("r2", "Answer B")]:
                v["resolutions"].append({
                    "resolution_id": rid,
                    "intent_id": "intent-security-proof",
                    "gap_id": "human-evidence:req-a",
                    "source_id": "amend-1",
                    "source_sha256": S2,
                    "section_id": "sec-answer",
                    "answer_summary": text,
                })
        output = self.compile(self.mutate(raw_input(), change))
        self.assertEqual("HOLD_SOURCE_CONFLICT", output.status)
        self.assertTrue(any(x.startswith("CONTRADICTORY_RESOLUTION") for x in self.packet(output)["source_conflicts"]))

    def test_secondary_sequence_may_match_official_without_false_conflict(self):
        def change(v):
            v["solicitation_pack"]["sources"].append({
                "source_id": "mirror-1",
                "source_class": "SECONDARY",
                "kind": "SOLICITATION",
                "identity": "secondary-mirror",
                "ref": "mirror-copy.pdf",
                "sha256": "3" * 64,
                "captured_at": "2026-09-16T11:15:00Z",
                "sequence": 1,
                "supersedes_sources": [],
                "supersedes_lineages": [],
                "requirements": [],
                "deadline": None,
                "attachments": [],
            })
        # Local execution stub ignores secondary semantics; this pins this module's
        # contract to the real upstream rule: sequence uniqueness is official-only.
        output = self.compile(self.mutate(raw_input(), change))
        self.assertEqual("READY_FOR_OWNER_REVIEW", output.status)
