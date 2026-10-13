from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from competitions.doe_gems.gems_solver import (
    distance_weighted_tversky,
    predict_raster,
    score_rasters,
    train_from_rasters,
    validate_submission,
)


def _write(path: Path, array: np.ndarray, dtype: str) -> None:
    data = np.asarray(array)
    if data.ndim == 2:
        data = data[None, ...]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype=dtype,
        crs="EPSG:32611",
        transform=from_origin(500000, 4500000, 100, 100),
    ) as dst:
        dst.write(data.astype(dtype))


def main() -> int:
    size = 64
    yy, xx = np.mgrid[:size, :size]
    fault_x = 20 + (yy // 6)
    dist = np.abs(xx - fault_x)
    labels = (dist <= 1).astype(np.uint8)
    features = np.stack(
        [
            np.tanh((xx - fault_x) / 2.0) + 0.08 * np.sin(yy / 4.0),
            np.exp(-(dist**2) / 8.0) + 0.06 * np.cos(xx / 7.0),
            (xx + yy).astype(np.float32) / (2 * size),
        ]
    ).astype(np.float32)

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        feature_path = root / "training_features.tif"
        label_path = root / "labels.tif"
        model_path = root / "model.joblib"
        output_path = root / "submission.tif"
        _write(feature_path, features, "float32")
        _write(label_path, labels, "uint8")
        bundle = train_from_rasters(
            feature_path,
            label_path,
            model_path,
            max_positive=160,
            negatives_per_positive=2.5,
            seed=20260913,
        )
        predict_raster(feature_path, model_path, output_path, tile_size=32)
        receipt = validate_submission(feature_path, output_path)
        score = score_rasters(output_path, label_path)
        constant = distance_weighted_tversky(
            np.full(labels.shape, 0.10, dtype=np.float32),
            labels,
        )
        if score["score"] <= constant["score"]:
            raise SystemExit(
                f"synthetic regression: model={score['score']:.6f} <= constant={constant['score']:.6f}"
            )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "samples": bundle["training"]["samples"],
                    "holdout_brier": bundle["training"]["holdout_brier"],
                    "submission": receipt,
                    "synthetic_dti": score["score"],
                    "constant_dti": constant["score"],
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
