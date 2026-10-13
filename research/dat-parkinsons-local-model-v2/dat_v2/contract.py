"""Competition-only software contract; not for diagnosis, treatment, or patient care."""

from __future__ import annotations

import hashlib
import json

SCHEMA_VERSION = "dat-parkinsons-local-model-v2/model-v1"
FEATURE_VERSION = "dat-v2-features/v2"
RUNTIME_COMMIT = "976fdcea1e6e586ca8af13bdab703de4a6c260a4"
EPS = 1e-6
MAX_INPUT_VOXELS = 256 * 256 * 256
MAX_WORKING_AXIS = 96
BRANCH_NAMES = ("logreg_c025", "logreg_c1", "logreg_c4_balanced")


def _public_feature_names() -> tuple[str, ...]:
    names: list[str] = []
    for q in (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99):
        names.append(f"q{int(q * 100):02d}")
    names.extend(["mean", "std"])
    for threshold in (0.25, 0.50, 0.75, 0.90):
        names.append(f"fraction_ge_{threshold:.2f}")
    for bins in (2, 3):
        for iz in range(bins):
            for iy in range(bins):
                for ix in range(bins):
                    names.extend([
                        f"grid{bins}_mean_z{iz}y{iy}x{ix}",
                        f"grid{bins}_massfrac_z{iz}y{iy}x{ix}",
                    ])
    names.extend([
        "com_z", "com_y", "com_x", "var_z", "var_y", "var_x",
        "cov_zy", "cov_zx", "cov_yx",
    ])
    for label in ("z", "y", "x"):
        names.extend([f"half_{label}_signed", f"half_{label}_abs"])
    names.extend(["grad_mean", "grad_std", "grad_q90", "grad_q99"])
    names.extend(["top10_volume_fraction", "top10_mean"])
    if len(names) != len(set(names)):
        raise RuntimeError("public feature schema contains duplicates")
    return tuple(names)


FEATURE_NAMES = _public_feature_names()


class ModelContractError(ValueError):
    """Input, split, or artifact violates a fail-closed competition contract."""


def canonical_json(value: object) -> str:
    """Return deterministic finite JSON suitable for hashing and model artifacts."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
