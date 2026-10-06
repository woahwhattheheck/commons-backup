from __future__ import annotations

import hashlib
import json
import time

import numpy as np

from solar_filament_baseline import panoptic_quality, segment_dark_filaments


def case(seed: int):
    rng = np.random.default_rng(seed)
    image = 0.82 + 0.06 * rng.standard_normal((128, 128), dtype=np.float32)
    truth = np.zeros((128, 128), dtype=np.int32)
    specs = [
        (1, 24, 31, 16, 104),
        (2, 58, 65, 8, 73),
        (3, 91, 99, 48, 119),
    ]
    for label, y0, y1, x0, x1 in specs:
        truth[y0:y1, x0:x1] = label
        image[y0:y1, x0:x1] -= 0.55
    return image, truth


def main():
    metrics = []
    latencies = []
    for seed in (7, 17, 29):
        image, truth = case(seed)
        t0 = time.perf_counter()
        pred = segment_dark_filaments(image, dark_quantile=0.16, min_area=20)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        result = panoptic_quality(pred, truth)
        metrics.append({
            "seed": seed,
            "pq": round(result.pq, 8),
            "dice": round(result.dice_foreground, 8),
            "fragmentation": result.fragmentation_count,
            "overmerge": result.overmerge_count,
            "instances_pred": int(pred.max()),
        })
    stable = {"schema": "solar-filament-synthetic-r1", "cases": metrics}
    stable_json = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    receipt = {
        **stable,
        "mean_pq": round(float(np.mean([m["pq"] for m in metrics])), 8),
        "mean_dice": round(float(np.mean([m["dice"] for m in metrics])), 8),
        "latency_ms_median": round(float(np.median(latencies)), 6),
        "latency_ms_p95": round(float(np.quantile(latencies, 0.95)), 6),
        "stable_receipt_sha256": hashlib.sha256(stable_json.encode()).hexdigest(),
        "evidence_boundary": "synthetic plumbing benchmark only; not MAGFiLO or competition performance",
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
