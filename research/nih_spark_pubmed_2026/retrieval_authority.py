from __future__ import annotations

from typing import Any, Mapping

from . import _baseline_core as _base

RETRIEVAL_TOP_K = 5

# `_baseline_core` is a private, byte-exact copy of the landed predecessor logic.
# Public callers use baseline.py, whose tiny facade imports this hardened module on
# every generation. Keeping the predecessor evaluator here lets malformed evidence
# retain the exact original schema/citation/error contract before authority checks.
_BASE_EVALUATE = _base.evaluate_bundle
_BASE_BUILD_RUN_RECEIPT = _base.build_run_receipt


def _canonical_retrievals(corpus: Any, cases: Any) -> dict[str, list[dict[str, Any]]]:
    normalized_cases = _base.load_cases(cases)
    return {
        case["query_id"]: _base.bm25_retrieve(
            corpus,
            case["query"],
            top_k=RETRIEVAL_TOP_K,
        )
        for case in normalized_cases["cases"]
    }


def evaluate_bundle(
    corpus: Any,
    cases: Any,
    retrievals: Mapping[str, list[dict[str, Any]]],
    answers: Mapping[str, Any],
) -> dict[str, Any]:
    # Run the byte-exact landed evaluator first so its structural contract is
    # preserved. Only structurally valid evidence reaches deterministic retrieval
    # authority below.
    evaluation = _BASE_EVALUATE(corpus, cases, retrievals, answers)

    if type(retrievals) is not dict:
        raise _base.ContractError("retrievals must be an exact object")
    canonical = _canonical_retrievals(corpus, cases)
    if retrievals != canonical:
        raise _base.ContractError(
            "retrievals differ from canonical BM25 evidence at retrieval_top_k=5"
        )

    return {
        **evaluation,
        "retrieval_top_k": RETRIEVAL_TOP_K,
    }


def build_run_receipt(
    *,
    corpus: Any,
    cases: Any,
    retrievals: Mapping[str, Any],
    answers: Mapping[str, Any],
    evaluation: Any,
    source_version: str,
) -> dict[str, Any]:
    # Build the landed receipt shape directly, but resolve deterministic evaluation
    # through this hardened generation rather than through mutable module globals.
    source_version = _base._identifier(source_version, "source_version")
    normalized_corpus = _base.load_corpus(corpus)
    normalized_cases = _base.load_cases(cases)
    expected_evaluation = evaluate_bundle(
        normalized_corpus,
        normalized_cases,
        retrievals,
        answers,
    )
    if evaluation != expected_evaluation:
        raise _base.ContractError("evaluation differs from deterministic recomputation")

    payload = {
        "schema": _base.SCHEMA_RECEIPT,
        "corpus_sha256": _base.semantic_sha256(normalized_corpus),
        "cases_sha256": _base.semantic_sha256(normalized_cases),
        "retrievals_sha256": _base.semantic_sha256(dict(sorted(retrievals.items()))),
        "answers_sha256": _base.semantic_sha256(dict(sorted(answers.items()))),
        "evaluation_sha256": _base.semantic_sha256(evaluation),
        "source_version": source_version,
        "official_corpus_used": False,
        "nih_registration_claimed": False,
        "official_score_claimed": False,
        "submission_claimed": False,
        "award_or_payment_claimed": False,
        "retrieval_top_k": RETRIEVAL_TOP_K,
    }
    payload["receipt_sha256"] = _base.semantic_sha256(payload)
    return payload


def verify_run_receipt(receipt: Any, **kwargs: Any) -> bool:
    return type(receipt) is dict and receipt == build_run_receipt(**kwargs)
