# SPDX-License-Identifier: MIT
"""Fail-closed placeholder for an eligible locally developed model backend."""
from pathlib import Path

def predict_probability(scan_path: Path) -> float:
    raise RuntimeError(
        "No model is bundled in this public readiness template. Replace model_backend.py "
        "with an eligible local model implementation and package its required assets."
    )
