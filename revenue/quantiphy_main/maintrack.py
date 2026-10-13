"""Compatibility facade for the QuantiPhy 2026 Main-track carrier.

Implementation is split by authority boundary: common custody, scoring/calibration,
recipe selection/application, and deterministic submission bundling. No module
performs provider calls, account actions, paid spend, or competition submission.
"""
from .common import (
    CATEGORIES, GROUND_TRUTH, MANIFEST_SCHEMA, MAX_SAFE_INT, RECEIPT_SCHEMA, SCHEMA,
    QuantiPhyMainError, canonical_bytes, canonical_sha, category_of, model_name,
    parse_quantity, row_key, sha256_bytes, strict_json_loads, validate_dataset,
    validate_receipts,
)
from .scoring import _grouped_folds, apply_scales, fit_scales, score_rows
from .recipe import apply_recipe, build_recipe
from .bundle import (
    build_submission_bundle, load_json_file, verify_submission_bundle,
    write_bundle_exclusive,
)

__all__ = [
    "CATEGORIES", "GROUND_TRUTH", "MANIFEST_SCHEMA", "MAX_SAFE_INT",
    "RECEIPT_SCHEMA", "SCHEMA", "QuantiPhyMainError", "canonical_bytes",
    "canonical_sha", "category_of", "model_name", "parse_quantity", "row_key",
    "sha256_bytes", "strict_json_loads", "validate_dataset", "validate_receipts",
    "apply_scales", "fit_scales", "score_rows", "apply_recipe", "build_recipe",
    "build_submission_bundle", "load_json_file", "verify_submission_bundle",
    "write_bundle_exclusive",
]
