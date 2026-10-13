"""Deterministic compound-transfer provenance evidence gate."""

from .gate import (
    DEFECT_CODES,
    HOLD,
    READY_FOR_SCREEN,
    GateArtifacts,
    build_gate_artifacts,
    verify_gate_artifacts,
)

__all__ = [
    "DEFECT_CODES",
    "HOLD",
    "READY_FOR_SCREEN",
    "GateArtifacts",
    "build_gate_artifacts",
    "verify_gate_artifacts",
]
