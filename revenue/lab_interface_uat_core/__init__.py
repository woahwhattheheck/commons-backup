"""Synthetic laboratory-interface UAT evidence core."""
from .engine import AUTHORITY, UATError, evaluate, verify_receipt

__all__ = ["AUTHORITY", "UATError", "evaluate", "verify_receipt"]
