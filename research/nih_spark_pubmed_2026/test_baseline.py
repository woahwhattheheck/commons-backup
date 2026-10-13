from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from research.nih_spark_pubmed_2026 import (
    ContractError,
    SCHEMA_ANSWER,
    bm25_retrieve,
    build_run_receipt,
    corpus_digest,
    evaluate_bundle,
    load_cases,
    load_corpus,
    load_json_strict_bytes,
    semantic_sha256,
    text_sha256,
    verify_exploratory_answer,
    verify_run_receipt,
)

ROOT = Path(__file__).resolve().parent
CORPUS = json.loads((ROOT / "fixtures" / "synthetic_corpus.json").read_text(encoding="utf-8"))
CASES = json.loads((ROOT / "fixtures" / "synthetic_cases.json").read_text(encoding="utf-8"))


def answer(query_id, *, claims, contradiction_groups=None, answerability="ANSWERED"):
    return {
        "schema": SCHEMA_ANSWER,
        "query_id": query_id,
        "answerability": answerability,
        "claims": claims,
        "contradiction_groups": contradiction_groups or [],
        "follow_up_actions": [
            "Inspect the highest-ranked source passage.",
            "Compare another independently sourced document.",
            "Record unresolved uncertainty before acting.",
        ],
    }


def claim(claim_id, text, *citations):
    return {
        "claim_id": claim_id,
        "text": text,
        "citations": [
            {"document_id": document_id, "passage_id": passage_id}
            for document_id, passage_id in citations
        ],
    }


class SparkPubMedBaselineTests(unittest.TestCase):
    def test_corpus_is_order_invariant_and_digest_bound(self):
        first = load_corpus(CORPUS)
        shuffled = copy.deepcopy(CORPUS)
        shuffled["documents"].reverse()
        for document in shuffled["documents"]:
            document["passages"].reverse()
        self.assertEqual(load_corpus(shuffled), first)
        self.assertEqual(corpus_digest(shuffled), corpus_digest(CORPUS))

    def test_corpus_rejects_duplicate_ids_and_stale_digest(self):
        bad = copy.deepcopy(CORPUS)
        bad["documents"][1]["document_id"] = bad["documents"][0]["document_id"]
        with self.assertRaises(ContractError):
            load_corpus(bad)
        bad = copy.deepcopy(CORPUS)
        bad["documents"][0]["passages"][0]["text"] += " changed"
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            load_corpus(bad)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite(self):
        with self.assertRaisesRegex(ContractError, "duplicate JSON key"):
            load_json_strict_bytes(b'{"schema":"x","schema":"y"}')
        with self.assertRaisesRegex(ContractError, "non-finite"):
            load_json_strict_bytes(b'{"x":NaN}')

    def test_bm25_is_deterministic_and_ties_are_stable(self):
        first = bm25_retrieve(CORPUS, "ceramic token box seven", top_k=10)
        second = bm25_retrieve(CORPUS, "ceramic token box seven", top_k=10)
        self.assertEqual(first, second)
        tied = [row["document_id"] for row in first if row["document_id"].startswith("D-TIE")]
        self.assertEqual(tied, ["D-TIE-A", "D-TIE-B"])

    def test_retrieval_finds_expected_synthetic_documents(self):
        self.assertEqual(bm25_retrieve(CORPUS, "blue shuttle Harbor", top_k=1)[0]["document_id"], "D-BUS-01")
        self.assertEqual(bm25_retrieve(CORPUS, "orchard irrigation battery", top_k=1)[0]["document_id"], "D-GARDEN-01")
        self.assertEqual(bm25_retrieve(CORPUS, "planetary observatory fee", top_k=5), [])

    def test_answer_contract_rejects_nonexistent_citation(self):
        candidate = answer(
            "Q-BUS",
            claims=[claim("C1", "Synthetic claim.", ("D-BUS-01", "NOPE"))],
        )
        with self.assertRaisesRegex(ContractError, "unknown citation"):
            verify_exploratory_answer(CORPUS, candidate)

    def test_unanswerable_must_have_zero_claims_and_groups(self):
        candidate = answer(
            "Q-MISSING",
            answerability="UNANSWERABLE",
            claims=[claim("C1", "Should not exist.", ("D-BUS-01", "P1"))],
        )
        with self.assertRaisesRegex(ContractError, "zero claims"):
            verify_exploratory_answer(CORPUS, candidate)

    def test_follow_up_actions_are_three_to_five_unique_items(self):
        candidate = answer(
            "Q-BUS",
            claims=[claim("C1", "Blue line terminates at Harbor Gate.", ("D-BUS-01", "P1"))],
        )
        candidate["follow_up_actions"] = ["same", "same", "third"]
        with self.assertRaisesRegex(ContractError, "unique"):
            verify_exploratory_answer(CORPUS, candidate)
        candidate["follow_up_actions"] = ["only", "two"]
        with self.assertRaises(ContractError):
            verify_exploratory_answer(CORPUS, candidate)

    def test_contradiction_group_requires_distinct_document_evidence(self):
        candidate = answer(
            "Q-LIBRARY",
            claims=[
                claim("C-OLD", "The older notice says 18:00.", ("D-LIBRARY-OLD", "P1")),
                claim("C-NEW", "The revised notice says 20:00.", ("D-LIBRARY-NEW", "P1")),
            ],
            contradiction_groups=[{"group_id": "G1", "claim_ids": ["C-OLD", "C-NEW"]}],
        )
        verified = verify_exploratory_answer(CORPUS, candidate)
        self.assertEqual(verified["contradiction_groups"][0]["claim_ids"], ["C-NEW", "C-OLD"])

        bad = answer(
            "Q-LIBRARY",
            claims=[
                claim("C1", "One reading.", ("D-LIBRARY-OLD", "P1")),
                claim("C2", "Another reading.", ("D-LIBRARY-OLD", "P1")),
            ],
            contradiction_groups=[{"group_id": "G1", "claim_ids": ["C1", "C2"]}],
        )
        with self.assertRaisesRegex(ContractError, "at least two documents"):
            verify_exploratory_answer(CORPUS, bad)

    def test_bundle_metrics_and_receipt_detect_tampering(self):
        retrievals = {
            case["query_id"]: bm25_retrieve(CORPUS, case["query"], top_k=5)
            for case in load_cases(CASES)["cases"]
        }
        answers = {
            "Q-BUS": answer(
                "Q-BUS",
                claims=[claim("C1", "The blue shuttle terminates at Harbor Gate.", ("D-BUS-01", "P1"))],
            ),
            "Q-GARDEN": answer(
                "Q-GARDEN",
                claims=[claim("C1", "The sensor battery chemistry is lithium iron phosphate.", ("D-GARDEN-01", "P1"))],
            ),
            "Q-LIBRARY": answer(
                "Q-LIBRARY",
                claims=[
                    claim("C-OLD", "The January notice says 18:00.", ("D-LIBRARY-OLD", "P1")),
                    claim("C-NEW", "The August revised notice says 20:00.", ("D-LIBRARY-NEW", "P1")),
                ],
                contradiction_groups=[{"group_id": "G1", "claim_ids": ["C-OLD", "C-NEW"]}],
            ),
            "Q-MISSING": answer("Q-MISSING", answerability="UNANSWERABLE", claims=[]),
        }
        evaluation = evaluate_bundle(CORPUS, CASES, retrievals, answers)
        self.assertEqual(evaluation["retrieval_hit_at_k"], 1.0)
        self.assertEqual(evaluation["answerability_accuracy"], 1.0)
        self.assertEqual(evaluation["contradiction_coverage"], 1.0)
        receipt = build_run_receipt(
            corpus=CORPUS,
            cases=CASES,
            retrievals=retrievals,
            answers=answers,
            evaluation=evaluation,
            source_version="synthetic-v1",
        )
        self.assertTrue(
            verify_run_receipt(
                receipt,
                corpus=CORPUS,
                cases=CASES,
                retrievals=retrievals,
                answers=answers,
                evaluation=evaluation,
                source_version="synthetic-v1",
            )
        )
        tampered = copy.deepcopy(receipt)
        tampered["official_score_claimed"] = True
        self.assertFalse(
            verify_run_receipt(
                tampered,
                corpus=CORPUS,
                cases=CASES,
                retrievals=retrievals,
                answers=answers,
                evaluation=evaluation,
                source_version="synthetic-v1",
            )
        )

    def test_bundle_rejects_unknown_retrieval_passage_and_extra_queries(self):
        retrievals = {
            case["query_id"]: bm25_retrieve(CORPUS, case["query"], top_k=5)
            for case in load_cases(CASES)["cases"]
        }
        answers = {
            "Q-BUS": answer(
                "Q-BUS",
                claims=[claim("C1", "The blue shuttle terminates at Harbor Gate.", ("D-BUS-01", "P1"))],
            ),
            "Q-GARDEN": answer(
                "Q-GARDEN",
                claims=[claim("C1", "The sensor battery chemistry is lithium iron phosphate.", ("D-GARDEN-01", "P1"))],
            ),
            "Q-LIBRARY": answer(
                "Q-LIBRARY",
                claims=[
                    claim("C-OLD", "The January notice says 18:00.", ("D-LIBRARY-OLD", "P1")),
                    claim("C-NEW", "The August revised notice says 20:00.", ("D-LIBRARY-NEW", "P1")),
                ],
                contradiction_groups=[{"group_id": "G1", "claim_ids": ["C-OLD", "C-NEW"]}],
            ),
            "Q-MISSING": answer("Q-MISSING", answerability="UNANSWERABLE", claims=[]),
        }
        poisoned = copy.deepcopy(retrievals)
        poisoned["Q-BUS"][0]["passage_id"] = "P-NOT-REAL"
        with self.assertRaisesRegex(ContractError, "unknown document/passage pair"):
            evaluate_bundle(CORPUS, CASES, poisoned, answers)

        extra = copy.deepcopy(retrievals)
        extra["Q-SHADOW"] = []
        with self.assertRaisesRegex(ContractError, "query_id set differs"):
            evaluate_bundle(CORPUS, CASES, extra, answers)

    def test_receipt_recomputes_evaluation_and_rejects_unknown_expected_docs(self):
        retrievals = {
            case["query_id"]: bm25_retrieve(CORPUS, case["query"], top_k=5)
            for case in load_cases(CASES)["cases"]
        }
        answers = {
            "Q-BUS": answer(
                "Q-BUS",
                claims=[claim("C1", "The blue shuttle terminates at Harbor Gate.", ("D-BUS-01", "P1"))],
            ),
            "Q-GARDEN": answer(
                "Q-GARDEN",
                claims=[claim("C1", "The sensor battery chemistry is lithium iron phosphate.", ("D-GARDEN-01", "P1"))],
            ),
            "Q-LIBRARY": answer(
                "Q-LIBRARY",
                claims=[
                    claim("C-OLD", "The January notice says 18:00.", ("D-LIBRARY-OLD", "P1")),
                    claim("C-NEW", "The August revised notice says 20:00.", ("D-LIBRARY-NEW", "P1")),
                ],
                contradiction_groups=[{"group_id": "G1", "claim_ids": ["C-OLD", "C-NEW"]}],
            ),
            "Q-MISSING": answer("Q-MISSING", answerability="UNANSWERABLE", claims=[]),
        }
        evaluation = evaluate_bundle(CORPUS, CASES, retrievals, answers)
        forged = copy.deepcopy(evaluation)
        forged["retrieval_mrr"] = 0.0
        with self.assertRaisesRegex(ContractError, "deterministic recomputation"):
            build_run_receipt(
                corpus=CORPUS,
                cases=CASES,
                retrievals=retrievals,
                answers=answers,
                evaluation=forged,
                source_version="synthetic-v1",
            )

        bad_cases = copy.deepcopy(CASES)
        bad_cases["cases"][0]["expected_document_ids"] = ["D-NOT-REAL"]
        with self.assertRaisesRegex(ContractError, "unknown expected document"):
            evaluate_bundle(CORPUS, bad_cases, retrievals, answers)

    def test_case_contract_rejects_bool_alias_and_duplicate_query(self):
        bad = copy.deepcopy(CASES)
        bad["cases"].append(copy.deepcopy(bad["cases"][0]))
        with self.assertRaisesRegex(ContractError, "duplicate query_id"):
            load_cases(bad)
        self.assertNotEqual(semantic_sha256({"x": True}), semantic_sha256({"x": 1}))
        self.assertEqual(text_sha256("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


if __name__ == "__main__":
    unittest.main()
