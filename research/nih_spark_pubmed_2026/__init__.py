"""Pre-launch deterministic baseline for the NIH/NLM SPARK PubMed/PMC Challenge."""

from .baseline import (
    ContractError,
    SCHEMA_ANSWER,
    SCHEMA_CASES,
    SCHEMA_CORPUS,
    bm25_retrieve,
    corpus_digest,
    load_cases,
    load_corpus,
    load_json_strict_bytes,
    semantic_sha256,
    text_sha256,
    verify_exploratory_answer,
)
from .retrieval_authority import (
    RETRIEVAL_TOP_K,
    build_run_receipt,
    evaluate_bundle,
    verify_run_receipt,
)

__all__ = [
    "ContractError",
    "RETRIEVAL_TOP_K",
    "SCHEMA_ANSWER",
    "SCHEMA_CASES",
    "SCHEMA_CORPUS",
    "bm25_retrieve",
    "build_run_receipt",
    "corpus_digest",
    "evaluate_bundle",
    "load_cases",
    "load_corpus",
    "load_json_strict_bytes",
    "semantic_sha256",
    "text_sha256",
    "verify_exploratory_answer",
    "verify_run_receipt",
]
