# SPDX-License-Identifier: Apache-2.0
"""Public API for TITAN behavior-equivalence evidence."""
from .analysis import analyze_equivalence
from .cli import build_parser, main
from .core import (
    BehaviorGateError,
    CLOSURE_SCHEMA,
    FAMILY_SCHEMA,
    LEDGER_ENTRY_SCHEMA,
    OBSERVATIONS_SCHEMA,
    PREFLIGHT_SCHEMA,
    REPORT_SCHEMA,
    ZERO_SHA256,
    CandidateSpec,
    ClosureMember,
    FamilySpec,
    canonical_bytes,
    load_strict,
    loads_strict,
    preflight_family,
    sha256_json,
    validate_family,
)
from .observations import (
    CandidateObservation,
    CellEvidence,
    CellKey,
    canonical_schedule,
    schedule_sha256,
    validate_observations,
)
from .receipts import append_ledger, render_markdown, verify_ledger

__all__ = [
    "BehaviorGateError",
    "CLOSURE_SCHEMA",
    "FAMILY_SCHEMA",
    "LEDGER_ENTRY_SCHEMA",
    "OBSERVATIONS_SCHEMA",
    "PREFLIGHT_SCHEMA",
    "REPORT_SCHEMA",
    "ZERO_SHA256",
    "CandidateObservation",
    "CandidateSpec",
    "CellEvidence",
    "CellKey",
    "ClosureMember",
    "FamilySpec",
    "analyze_equivalence",
    "append_ledger",
    "build_parser",
    "canonical_bytes",
    "canonical_schedule",
    "load_strict",
    "loads_strict",
    "main",
    "preflight_family",
    "render_markdown",
    "schedule_sha256",
    "sha256_json",
    "validate_family",
    "validate_observations",
    "verify_ledger",
]
