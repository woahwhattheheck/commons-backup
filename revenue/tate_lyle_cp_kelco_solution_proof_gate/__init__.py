"""Offline Tate & Lyle / CP Kelco portfolio solution-proof gate.

PASS/HOLD is evidence completeness against a separately pinned reference generation.
The package does not authenticate the host pin's external provenance and grants no
formulation, claim, regulatory, release, buyer, payment, or revenue authority.
"""

from .gate import AUTHORITY, GateInputError, digest, evaluate, reference_commitment, verify

__all__ = ["AUTHORITY", "GateInputError", "digest", "evaluate", "reference_commitment", "verify"]
