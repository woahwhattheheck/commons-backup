"""Deterministic ARC3 SAGE ablation harness."""

from .harness import (
    AblationKind,
    ArmConfig,
    TrialRow,
    ExperimentReceipt,
    compile_experiment,
    verify_experiment,
)

__all__ = [
    "AblationKind",
    "ArmConfig",
    "TrialRow",
    "ExperimentReceipt",
    "compile_experiment",
    "verify_experiment",
]
