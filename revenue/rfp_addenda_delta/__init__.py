"""Exact RFP/Addenda generation delta desk."""

from .schema import (
    DECISION_SCHEMA, GEN_SCHEMA, SCHEMA, DeltaError, canonical, loads_strict,
    normalize_decisions, normalize_generation, requirement_identity,
)
from .engine import compile_current, compile_historical, markdown, verify_report

__all__ = [
    "SCHEMA", "GEN_SCHEMA", "DECISION_SCHEMA", "DeltaError", "canonical",
    "loads_strict", "normalize_generation", "normalize_decisions",
    "requirement_identity", "compile_current", "compile_historical", "verify_report",
    "markdown",
]
