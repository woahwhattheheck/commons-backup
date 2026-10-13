"""Dependency-free pre-launch baselines for the NIH/NLM SPARK dbGaP Challenge."""

from .baseline import (
    ContractError,
    Corpus,
    ResourceManifest,
    build_run_receipt,
    evaluate_track1,
    evaluate_track2,
    scan_source_for_query_keyed_hardcoding,
    track1_predict,
    track2_rank,
    verify_run_receipt,
)

__all__ = [
    "ContractError",
    "Corpus",
    "ResourceManifest",
    "build_run_receipt",
    "evaluate_track1",
    "evaluate_track2",
    "scan_source_for_query_keyed_hardcoding",
    "track1_predict",
    "track2_rank",
    "verify_run_receipt",
]
