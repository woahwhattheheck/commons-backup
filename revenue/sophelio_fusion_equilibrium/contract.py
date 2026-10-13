"""Pinned external contract and shared data structures for the Sophelio carrier."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

OFFICIAL_STARTER_REPO = "Sophelio/fusion-equilibrium-challenge-starter"
OFFICIAL_STARTER_SHA = "a67429165b09eb81c311d44db6ff11743f108b0e"
OFFICIAL_SCORING_VERSION = "3.2.0"
HF_DATASET = "Sophelio/fusion-equilibrium-challenge"
D3D_TRAIN_SHOTS = 7041
D3D_PUBLIC_TEST_SHOTS = 874
MAST_PUBLIC_TEST_SHOTS = 1206
GRID_SHAPE = (65, 65)
D3D_COMPOSITE_GATE = 0.85
BREAKDOWN_WINDOW_MS = (-500.0, 1000.0)
SCALARS = ("q95", "betaN")
CONFIG_TO_MACHINE = {
    "diii_d_public_test": "DIII-D",
    "mast_public_test": "MAST",
}


class ContractError(ValueError):
    """Raised when source or submission bytes violate the pinned contract."""


@dataclass(frozen=True)
class Prediction:
    psirz: np.ndarray
    q95: np.ndarray
    betaN: np.ndarray


@dataclass(frozen=True)
class Fold:
    train_shots: tuple[str, ...]
    valid_shots: tuple[str, ...]


@dataclass(frozen=True)
class ProxyScore:
    r2_psi: float
    r2_scalars: float
    partial_composite: float
    n_frames: int
    n_shots: int


@dataclass(frozen=True)
class BundleReceipt:
    d3d_sha256: str
    mast_sha256: str
    manifest_sha256: str
    bundle_sha256: str


def contract_snapshot() -> dict:
    """Return the immutable external assumptions this carrier is built against."""
    return {
        "starter_repo": OFFICIAL_STARTER_REPO,
        "starter_sha": OFFICIAL_STARTER_SHA,
        "scoring_version": OFFICIAL_SCORING_VERSION,
        "dataset": HF_DATASET,
        "shots": {
            "diii_d_train": D3D_TRAIN_SHOTS,
            "diii_d_public_test": D3D_PUBLIC_TEST_SHOTS,
            "mast_public_test": MAST_PUBLIC_TEST_SHOTS,
        },
        "grid": list(GRID_SHAPE),
        "submitted_scalars": list(SCALARS),
        "challenge2_d3d_gate": D3D_COMPOSITE_GATE,
        "split_unit": "shot",
    }


