"""Deterministic synthetic evaluation for the abstract anomaly detector.

Synthetic fixtures test software behavior only. They are not biological data and must
not be cited as competition performance.
"""
from __future__ import annotations

import json
import random

from detector import fit_reference, score_sample

FEATURES = ("feature_a", "feature_b", "feature_c", "feature_d", "feature_e")


def _row(rng: random.Random, *, shifted: bool) -> dict[str, float]:
    row = {name: rng.gauss(0.0, 1.0) for name in FEATURES}
    if shifted:
        # Abstract distribution shift. No domain or biological semantics are encoded.
        row["feature_b"] += 6.0
        row["feature_d"] -= 5.0
    return row


def evaluate(seed: int = 20260913) -> dict[str, object]:
    rng = random.Random(seed)
    baseline = [_row(rng, shifted=False) for _ in range(300)]
    benign = [_row(rng, shifted=False) for _ in range(200)]
    anomalies = [_row(rng, shifted=True) for _ in range(200)]
    model = fit_reference(baseline, target_background_acceptance=0.99)
    benign_results = [score_sample(model, row) for row in benign]
    anomaly_results = [score_sample(model, row) for row in anomalies]
    false_positives = sum(bool(result["flagged_for_follow_on"]) for result in benign_results)
    true_positives = sum(bool(result["flagged_for_follow_on"]) for result in anomaly_results)
    return {
        "fixture": "abstract-gaussian-shift-v1",
        "seed": seed,
        "baseline_rows": len(baseline),
        "benign_rows": len(benign),
        "anomaly_rows": len(anomalies),
        "model_sha256": model.model_sha256,
        "threshold": model.threshold,
        "false_positive_rate": false_positives / len(benign_results),
        "detection_rate": true_positives / len(anomaly_results),
        "note": "Synthetic software fixture only; not biological/challenge performance.",
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), sort_keys=True, indent=2))
