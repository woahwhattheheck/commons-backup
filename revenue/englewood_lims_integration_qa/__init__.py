"""Provider-free evidence gate for the Englewood LIMS integration-QA teaming seam."""

from .gate import EvidenceError, evaluate, verify_receipt

__all__ = ["EvidenceError", "evaluate", "verify_receipt"]
