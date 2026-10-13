"""Compatibility facade for the truth-narrow Sasria readiness compiler."""

from .core_v2 import (
    BuyerTechnicalScore,
    EvidenceRef,
    PaidWorkshare,
    PrimeCandidate,
    REQUIRED_RETURNABLES,
    RECOGNIZED_FRAMEWORKS,
    ROLE_GROUPS,
    SCHEMA,
    SubmissionAuthority,
    TECHNICAL_PASS_SCORE,
    TECHNICAL_SCORE_CAPS,
    TrainingPathway,
    compile_readiness_pack,
    render_markdown,
)

__all__ = [
    "BuyerTechnicalScore",
    "EvidenceRef",
    "PaidWorkshare",
    "PrimeCandidate",
    "REQUIRED_RETURNABLES",
    "RECOGNIZED_FRAMEWORKS",
    "ROLE_GROUPS",
    "SCHEMA",
    "SubmissionAuthority",
    "TECHNICAL_PASS_SCORE",
    "TECHNICAL_SCORE_CAPS",
    "TrainingPathway",
    "compile_readiness_pack",
    "render_markdown",
]
