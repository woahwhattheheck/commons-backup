"""New Mexico OCS2026.01 TPRM reference carrier."""

from .qualification import compile_qualification, verify_receipt
from .tprm import compile_assessment, compile_portfolio, verify_assessment_packet, verify_portfolio_packet

__all__ = [
    "compile_assessment",
    "compile_portfolio",
    "verify_assessment_packet",
    "verify_portfolio_packet",
    "compile_qualification",
    "verify_receipt",
]
