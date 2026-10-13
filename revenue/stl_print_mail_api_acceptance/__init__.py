"""Deterministic acceptance evidence for print/mail API integrations."""

from .validator import evaluate_fixture, verify_receipt_integrity

__all__ = ["evaluate_fixture", "verify_receipt_integrity"]
