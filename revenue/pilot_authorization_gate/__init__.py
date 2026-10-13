"""Deterministic evidence gate for paid-pilot execution authorization."""
from .gate import GateInputError, HOLD, PROPOSAL_READY, READY, digest, evaluate, verify
__all__ = ["GateInputError", "HOLD", "PROPOSAL_READY", "READY", "digest", "evaluate", "verify"]
