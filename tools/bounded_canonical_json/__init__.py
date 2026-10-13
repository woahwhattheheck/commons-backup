"""Reusable bounded canonical JSON boundary."""

from .core import (
    BoundaryError,
    DEFAULT_LIMITS,
    Limits,
    canonical_bytes,
    canonical_equal,
    canonical_sha256,
    loads_strict,
)

__all__ = [
    "BoundaryError",
    "DEFAULT_LIMITS",
    "Limits",
    "canonical_bytes",
    "canonical_equal",
    "canonical_sha256",
    "loads_strict",
]
