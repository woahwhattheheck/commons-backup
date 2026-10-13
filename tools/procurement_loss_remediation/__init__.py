"""Evidence-bound procurement loss/debrief remediation planning."""

from . import core as _core
from .core import RemediationError, normalize_input
from .policy import compile_plan, derive_semantics

# Keep package-qualified imports of ``tools.procurement_loss_remediation.core``
# on the same truth-ceiling policy as the public package surface. policy.py
# captures the frozen predecessor derive_semantics before these assignments.
_core.compile_plan = compile_plan
_core.derive_semantics = derive_semantics

from .verifier import RemediationVerificationError, verify_plan

__all__ = [
    "RemediationError",
    "RemediationVerificationError",
    "compile_plan",
    "derive_semantics",
    "normalize_input",
    "verify_plan",
]
