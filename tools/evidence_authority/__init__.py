"""Fail-closed source-bound evidence authority kernel."""

from .codec import GateError, loads_strict_json, sha256_bytes
from .engine import compile_current, verify_current, verify_receipt
from .schema import validate_candidate, validate_manifest

__all__ = [
    "GateError",
    "compile_current",
    "loads_strict_json",
    "sha256_bytes",
    "validate_candidate",
    "validate_manifest",
    "verify_current",
    "verify_receipt",
]
