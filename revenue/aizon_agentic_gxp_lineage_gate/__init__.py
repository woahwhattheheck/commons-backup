"""Synthetic, evidence-only agentic lineage gate."""
from .gate import AUTHORITY, EvidenceError, compute_lineage_digest, evaluate, verify_receipt

__all__ = ["AUTHORITY", "EvidenceError", "compute_lineage_digest", "evaluate", "verify_receipt"]
