"""Commercial acceptance evidence bridge."""

from .gate import AcceptanceError, receipt_self_digest_matches, reconcile, verify_receipt

__all__ = ["AcceptanceError", "receipt_self_digest_matches", "reconcile", "verify_receipt"]
