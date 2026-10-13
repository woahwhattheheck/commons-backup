from __future__ import annotations

import json

import numpy as np
from scipy.ndimage import gaussian_filter

try:
    from .structure_v2 import (
        apply_structure,
        distance_weighted_tversky,
        select_config,
        selected_config,
        verify_selection,
    )
except ImportError:
    from structure_v2 import (
        apply_structure,
        distance_weighted_tversky,
        select_config,
        selected_config,
        verify_selection,
    )


def scene(seed: int, n: int = 128) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    truth = np.zeros((n, n), np.uint8)
    xs = np.arange(8, n - 8)
    y1 = (0.20 * n + 0.24 * (xs - 8) + 2.8 * np.sin(xs / 13)).astype(int)
    y2 = (0.79 * n - 0.39 * (xs - 8) + 2.2 * np.sin(xs / 17)).astype(int)
    truth[y1, xs] = 1
    truth[y2, xs] = 1
    ys = np.arange(11, n - 11)
    x3 = (0.48 * n + 0.11 * (ys - 11) + 2.2 * np.sin(ys / 12)).astype(int)
    truth[ys, x3] = 1

    probability = gaussian_filter(truth.astype(np.float64), 1.05)
    probability = probability / max(float(probability.max()), 1e-12) * 0.72

    for start in (28, 55, 82):
        cy = int(0.20 * n + 0.24 * (start - 8) + 2.8 * np.sin(start / 13))
        probability[max(cy - 1, 0) : min(cy + 2, n), start : start + 3] *= 0.05

    probability += rng.uniform(0.0, 0.035, size=(n, n))
    rr = rng.integers(0, n, 70)
    cc = rng.integers(0, n, 70)
    probability[rr, cc] = rng.uniform(0.12, 0.30, size=len(rr))
    return np.clip(probability, 0.0, 1.0).astype(np.float32), truth


def main() -> int:
    validation_probability, validation_truth = scene(20260916)
    test_probability, test_truth = scene(20260917)

    selection = select_config(validation_probability, validation_truth)
    if not verify_selection(validation_probability, validation_truth, selection):
        raise RuntimeError("selection receipt failed verification")

    config = selected_config(selection)
    test_v2 = apply_structure(test_probability, config)

    validation_base = distance_weighted_tversky(
        validation_probability, validation_truth
    )["score"]
    validation_v2 = float(selection["selected"]["score"])
    test_base = distance_weighted_tversky(test_probability, test_truth)["score"]
    test_score = distance_weighted_tversky(test_v2, test_truth)["score"]

    if validation_v2 + 1e-15 < validation_base:
        raise RuntimeError("selector regressed validation score below no-op baseline")
    if test_score <= test_base:
        raise RuntimeError("frozen V2 did not improve held synthetic scene")

    result = {
        "schema": "doe-gems-structure-synthetic-smoke/v1",
        "selection_receipt_sha256": selection["receipt_sha256"],
        "selected_config": selection["selected"]["config"],
        "validation": {
            "base_dti": float(validation_base),
            "v2_dti": float(validation_v2),
            "delta": float(validation_v2 - validation_base),
        },
        "held_synthetic": {
            "base_dti": float(test_base),
            "v2_dti": float(test_score),
            "delta": float(test_score - test_base),
        },
        "authority": {
            "official_data": False,
            "leaderboard": False,
            "submission": False,
            "prize": False,
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
