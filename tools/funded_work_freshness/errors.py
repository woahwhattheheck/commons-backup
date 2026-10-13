"""Typed fail-closed errors."""
from __future__ import annotations


class PreflightInputError(ValueError):
    """The caller supplied an invalid candidate contract."""


class EvidenceError(RuntimeError):
    """Canonical evidence could not be read completely."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail
