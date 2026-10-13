from __future__ import annotations

import copy
import importlib
import threading
import unittest

import research.nih_spark_pubmed_2026 as nih_package
from research.nih_spark_pubmed_2026 import (
    ContractError,
    RETRIEVAL_TOP_K,
    SCHEMA_ANSWER,
    bm25_retrieve,
    build_run_receipt,
    evaluate_bundle,
    text_sha256,
    verify_run_receipt,
)
from research.nih_spark_pubmed_2026 import _baseline_core as baseline_core
from research.nih_spark_pubmed_2026 import baseline
from research.nih_spark_pubmed_2026 import retrieval_authority as authority


def _document(document_id: str, text: str) -> dict:
    return {
        "document_id": document_id,
        "version": "v1",
        "license": "synthetic-test-only",
        "provenance": "post-merge predecessor killer",
        "title": document_id,
        "text_sha256": text_sha256(text),
        "passages": [{"passage_id": "P1", "text": text}],
    }


CORPUS = {
    "schema": "nih.spark.pubmed.corpus/v1",
    "documents": [
        *[_document(f"D-DECOY-{index}", "alpha alpha alpha alpha") for index in range(5)],
        _document("D-TARGET", "alpha"),
    ],
}
CASES = {
    "schema": "nih.spark.pubmed.cases/v1",
    "cases": [
        {
            "query_id": "Q-DEPTH",
            "query": "alpha",
            "expected_document_ids": ["D-TARGET"],
            "expected_answerability": "UNANSWERABLE",
            "expected_contradiction_document_sets": [],
        }
    ],
}
ANSWERS = {
    "Q-DEPTH": {
        "schema": SCHEMA_ANSWER,
        "query_id": "Q-DEPTH",
        "answerability": "UNANSWERABLE",
        "claims": [],
        "contradiction_groups": [],
        "follow_up_actions": [
            "Inspect the highest-ranked source passage.",
            "Compare another independently sourced document.",
            "Record unresolved uncertainty before acting.",
        ],
    }
}


class RetrievalAuthorityTests(unittest.TestCase):
    def canonical(self) -> dict:
        return {
            "Q-DEPTH": bm25_retrieve(
                CORPUS,
                "alpha",
                top_k=RETRIEVAL_TOP_K,
            )
        }

    def forged_rank_one(self) -> dict:
        forged = self.canonical()
        forged["Q-DEPTH"] = [
            {"document_id": "D-TARGET", "passage_id": "P1", "score": 999.0},
            *forged["Q-DEPTH"][: RETRIEVAL_TOP_K - 1],
        ]
        return forged

    def test_canonical_retrieval_depth_is_receipt_bound(self):
        retrievals = self.canonical()
        self.assertEqual(len(retrievals["Q-DEPTH"]), RETRIEVAL_TOP_K)
        self.assertNotIn(
            "D-TARGET",
            {row["document_id"] for row in retrievals["Q-DEPTH"]},
        )
        evaluation = evaluate_bundle(CORPUS, CASES, retrievals, ANSWERS)
        self.assertEqual(evaluation["retrieval_top_k"], RETRIEVAL_TOP_K)
        self.assertEqual(evaluation["retrieval_hit_at_k"], 0.0)
        receipt = build_run_receipt(
            corpus=CORPUS,
            cases=CASES,
            retrievals=retrievals,
            answers=ANSWERS,
            evaluation=evaluation,
            source_version="authority-v1",
        )
        self.assertEqual(receipt["retrieval_top_k"], RETRIEVAL_TOP_K)
        self.assertTrue(
            verify_run_receipt(
                receipt,
                corpus=CORPUS,
                cases=CASES,
                retrievals=retrievals,
                answers=ANSWERS,
                evaluation=evaluation,
                source_version="authority-v1",
            )
        )

    def test_injected_expected_document_cannot_mint_perfect_receipt(self):
        forged = self.forged_rank_one()
        predecessor = authority._BASE_EVALUATE(CORPUS, CASES, forged, ANSWERS)
        self.assertEqual(predecessor["retrieval_hit_at_k"], 1.0)
        self.assertEqual(predecessor["retrieval_mrr"], 1.0)
        with self.assertRaisesRegex(ContractError, "canonical BM25 evidence"):
            evaluate_bundle(CORPUS, CASES, forged, ANSWERS)

    def test_rank_after_k_and_rescored_rows_are_rejected(self):
        over_depth = self.canonical()
        over_depth["Q-DEPTH"].append(
            {"document_id": "D-TARGET", "passage_id": "P1", "score": 0.000001}
        )
        predecessor = authority._BASE_EVALUATE(CORPUS, CASES, over_depth, ANSWERS)
        self.assertEqual(predecessor["retrieval_hit_at_k"], 1.0)
        with self.assertRaisesRegex(ContractError, "retrieval_top_k=5"):
            evaluate_bundle(CORPUS, CASES, over_depth, ANSWERS)

        rescored = copy.deepcopy(self.canonical())
        rescored["Q-DEPTH"][0]["score"] += 1.0
        with self.assertRaisesRegex(ContractError, "canonical BM25 evidence"):
            evaluate_bundle(CORPUS, CASES, rescored, ANSWERS)

    def test_y_concurrent_reload_never_publishes_predecessor_authority(self):
        # importlib.reload() executes into the already-published module object.
        # Freeze the facade copy loop on an appended core sentinel after every
        # historical definition has been visited, then inspect the live module
        # from this thread while reload is still in progress. Before the fix the
        # three predecessor authority callables were visible in this window.
        entered = threading.Event()
        release = threading.Event()
        failures: list[BaseException] = []

        class ReloadBarrier:
            @property
            def __module__(self) -> str:
                entered.set()
                if not release.wait(5.0):
                    raise RuntimeError("reload barrier timed out")
                return "reload_barrier"

        barrier = ReloadBarrier()
        setattr(baseline_core, "_reload_authority_test_barrier", barrier)

        def do_reload() -> None:
            try:
                importlib.reload(baseline)
            except BaseException as exc:  # pragma: no cover - surfaced below
                failures.append(exc)

        worker = threading.Thread(target=do_reload, name="nih-baseline-reload-hostile")
        try:
            worker.start()
            self.assertTrue(entered.wait(5.0), "reload never reached hostile barrier")

            self.assertIs(baseline.evaluate_bundle, authority.evaluate_bundle)
            self.assertIs(baseline.build_run_receipt, authority.build_run_receipt)
            self.assertIs(baseline.verify_run_receipt, authority.verify_run_receipt)
            self.assertIsNot(baseline.evaluate_bundle, authority._BASE_EVALUATE)
            self.assertIsNot(baseline.build_run_receipt, authority._BASE_BUILD_RUN_RECEIPT)
            self.assertIsNot(baseline.verify_run_receipt, baseline_core.verify_run_receipt)
        finally:
            release.set()
            worker.join(5.0)
            if hasattr(baseline_core, "_reload_authority_test_barrier"):
                delattr(baseline_core, "_reload_authority_test_barrier")
            if hasattr(baseline, "_reload_authority_test_barrier"):
                delattr(baseline, "_reload_authority_test_barrier")

        self.assertFalse(worker.is_alive(), "reload thread did not complete")
        self.assertEqual(failures, [])
        self.assertIs(baseline.evaluate_bundle, authority.evaluate_bundle)
        self.assertIs(baseline.build_run_receipt, authority.build_run_receipt)
        self.assertIs(baseline.verify_run_receipt, authority.verify_run_receipt)

    def test_z_baseline_reload_and_repeated_reload_preserve_authority(self):
        # This is the exact post-merge predecessor killer for #14607. Before the
        # repair, ordinary reload restored the untouched vulnerable baseline
        # definitions and a forged ranking could mint a self-validating receipt.
        for generation in range(2):
            reloaded = importlib.reload(baseline)
            self.assertIs(reloaded, baseline)
            self.assertIs(reloaded.evaluate_bundle, authority.evaluate_bundle)
            self.assertIs(reloaded.build_run_receipt, authority.build_run_receipt)
            self.assertIs(reloaded.verify_run_receipt, authority.verify_run_receipt)

            # Package aliases must remain coherent with the direct submodule
            # generation, including historical public module identity used by
            # introspection and pickle lookup.
            self.assertIs(nih_package.ContractError, reloaded.ContractError)
            self.assertIs(nih_package.bm25_retrieve, reloaded.bm25_retrieve)
            self.assertIs(nih_package.load_cases, reloaded.load_cases)
            self.assertIs(nih_package.evaluate_bundle, authority.evaluate_bundle)
            self.assertIs(nih_package.build_run_receipt, authority.build_run_receipt)
            self.assertIs(nih_package.verify_run_receipt, authority.verify_run_receipt)
            self.assertEqual(reloaded.ContractError.__module__, reloaded.__name__)
            self.assertEqual(reloaded.bm25_retrieve.__module__, reloaded.__name__)
            self.assertEqual(reloaded.load_cases.__module__, reloaded.__name__)

            forged = {
                "Q-DEPTH": [
                    {"document_id": "D-TARGET", "passage_id": "P1", "score": 999.0},
                    *nih_package.bm25_retrieve(
                        CORPUS,
                        "alpha",
                        top_k=RETRIEVAL_TOP_K,
                    )[: RETRIEVAL_TOP_K - 1],
                ]
            }
            with self.assertRaisesRegex(
                reloaded.ContractError,
                "canonical BM25 evidence",
            ):
                reloaded.evaluate_bundle(CORPUS, CASES, forged, ANSWERS)

            canonical = {
                "Q-DEPTH": nih_package.bm25_retrieve(
                    CORPUS,
                    "alpha",
                    top_k=RETRIEVAL_TOP_K,
                )
            }
            evaluation = reloaded.evaluate_bundle(CORPUS, CASES, canonical, ANSWERS)
            self.assertEqual(evaluation["retrieval_top_k"], RETRIEVAL_TOP_K)
            self.assertEqual(evaluation["retrieval_hit_at_k"], 0.0)
            receipt = reloaded.build_run_receipt(
                corpus=CORPUS,
                cases=CASES,
                retrievals=canonical,
                answers=ANSWERS,
                evaluation=evaluation,
                source_version=f"reload-authority-v{generation + 1}",
            )
            self.assertTrue(
                reloaded.verify_run_receipt(
                    receipt,
                    corpus=CORPUS,
                    cases=CASES,
                    retrievals=canonical,
                    answers=ANSWERS,
                    evaluation=evaluation,
                    source_version=f"reload-authority-v{generation + 1}",
                )
            )

            over_depth = copy.deepcopy(canonical)
            over_depth["Q-DEPTH"].append(
                {"document_id": "D-TARGET", "passage_id": "P1", "score": 0.000001}
            )
            with self.assertRaisesRegex(
                reloaded.ContractError,
                "retrieval_top_k=5",
            ):
                reloaded.evaluate_bundle(CORPUS, CASES, over_depth, ANSWERS)

            rescored = copy.deepcopy(canonical)
            rescored["Q-DEPTH"][0]["score"] += 1.0
            with self.assertRaisesRegex(
                reloaded.ContractError,
                "canonical BM25 evidence",
            ):
                reloaded.evaluate_bundle(CORPUS, CASES, rescored, ANSWERS)


if __name__ == "__main__":
    unittest.main()
