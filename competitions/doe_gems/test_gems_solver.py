from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import rasterio
from rasterio.transform import from_origin

from competitions.doe_gems.gems_solver import (
    GemsError,
    blocked_fold_ids,
    choose_training_coordinates,
    distance_weighted_tversky,
    feature_stack,
    fit_model,
    predict_matrix,
    predict_raster,
    robust_band_stats,
    score_rasters,
    train_from_rasters,
    validate_feature_raster,
    validate_label_alignment,
    validate_submission,
)


def write_raster(path: Path, arr: np.ndarray, *, crs: str = "EPSG:32611", dtype: str = "float32") -> None:
    data = np.asarray(arr)
    if data.ndim == 2:
        data = data[None, ...]
    transform = from_origin(500000.0, 4500000.0, 100.0, 100.0)
    profile = {
        "driver": "GTiff",
        "height": data.shape[1],
        "width": data.shape[2],
        "count": data.shape[0],
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(dtype))


def synthetic_features_labels(size: int = 64) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[:size, :size]
    fault_x = size // 2 + (yy // 16)
    distance = np.abs(xx - fault_x)
    labels = (distance <= 1).astype(np.uint8)
    band0 = np.tanh((xx - fault_x) / 2.0) + 0.05 * np.sin(yy / 3.0)
    band1 = np.exp(-(distance**2) / 6.0) + 0.05 * np.cos(xx / 5.0)
    return np.stack([band0, band1]).astype(np.float32), labels


class MetricTests(unittest.TestCase):
    def test_perfect_prediction_scores_one(self):
        truth = np.zeros((20, 20), dtype=np.uint8)
        truth[3:17, 9] = 1
        result = distance_weighted_tversky(truth.astype(np.float32), truth)
        self.assertGreater(result["score"], 0.999999999)
        self.assertAlmostEqual(result["fp_w"], 0.0, places=12)
        self.assertAlmostEqual(result["fn_w"], 0.0, places=12)

    def test_near_miss_gets_partial_credit(self):
        truth = np.zeros((24, 24), dtype=np.uint8)
        truth[4:20, 10] = 1
        near = np.zeros_like(truth, dtype=np.float32)
        far = np.zeros_like(truth, dtype=np.float32)
        near[4:20, 11] = 1.0
        far[4:20, 18] = 1.0
        near_score = distance_weighted_tversky(near, truth)["score"]
        far_score = distance_weighted_tversky(far, truth)["score"]
        self.assertGreater(near_score, far_score)
        self.assertGreater(near_score, 0.1)

    def test_false_positive_penalty_is_bounded(self):
        truth = np.zeros((30, 30), dtype=np.uint8)
        truth[5:25, 10] = 1
        pred = truth.astype(np.float32)
        pred[2, 28] = 1.0
        result = distance_weighted_tversky(pred, truth)
        self.assertGreater(result["score"], 0.98)
        self.assertGreater(result["fp_w"], 0.9)

    def test_metric_rejects_bad_probabilities(self):
        truth = np.zeros((3, 3), dtype=np.uint8)
        with self.assertRaises(GemsError):
            distance_weighted_tversky(np.full((3, 3), 1.1), truth)
        with self.assertRaises(GemsError):
            distance_weighted_tversky(np.full((3, 3), np.nan), truth)


class FeatureTests(unittest.TestCase):
    def test_feature_shape_and_finiteness(self):
        arr, _ = synthetic_features_labels(32)
        med, scale = robust_band_stats(arr)
        feats = feature_stack(arr, med, scale)
        self.assertEqual(feats.shape, (12, 32, 32))
        self.assertTrue(np.isfinite(feats).all())

    def test_line_features_respond_to_fault_structure(self):
        arr = np.zeros((1, 48, 48), dtype=np.float32)
        arr[0, :, 24:] = 3.0
        med, scale = robust_band_stats(arr)
        feats = feature_stack(arr, med, scale)
        gradient = feats[1]
        line = feats[3]
        self.assertGreater(float(gradient[:, 22:27].mean()), float(gradient[:, :8].mean()) + 0.05)
        self.assertGreater(float(line[:, 22:27].mean()), float(line[:, :8].mean()) + 0.01)

    def test_spatial_folds_keep_same_block_together(self):
        rows = np.array([1, 2, 129, 130])
        cols = np.array([5, 6, 5, 6])
        folds = blocked_fold_ids(rows, cols, block_size=128, n_splits=5)
        self.assertEqual(int(folds[0]), int(folds[1]))
        self.assertEqual(int(folds[2]), int(folds[3]))

    def test_sampler_includes_hard_negatives_and_is_deterministic(self):
        truth = np.zeros((40, 40), dtype=np.uint8)
        truth[:, 20] = 1
        a = choose_training_coordinates(truth, max_positive=30, negatives_per_positive=2, seed=7)
        b = choose_training_coordinates(truth, max_positive=30, negatives_per_positive=2, seed=7)
        for left, right in zip(a, b):
            np.testing.assert_array_equal(left, right)
        rows, cols, target = a
        self.assertEqual(int((target == 1).sum()), 30)
        self.assertEqual(int((target == 0).sum()), 60)
        negative_distance = np.abs(cols[target == 0] - 20)
        self.assertTrue(np.any((negative_distance > 0) & (negative_distance <= 8)))


class ModelTests(unittest.TestCase):
    def test_small_synthetic_model_learns_fault_signal(self):
        arr, truth = synthetic_features_labels(64)
        med, scale = robust_band_stats(arr)
        cube = feature_stack(arr, med, scale)
        rows, cols, target = choose_training_coordinates(
            truth, max_positive=120, negatives_per_positive=2.0, seed=11
        )
        x = cube[:, rows, cols].T
        bundle = fit_model(
            x,
            target,
            rows,
            cols,
            block_size=16,
            n_splits=4,
            holdout_fold=0,
            random_state=11,
        )
        matrix = np.moveaxis(cube, 0, -1).reshape(-1, cube.shape[0])
        pred = predict_matrix(bundle, matrix).reshape(truth.shape)
        learned = distance_weighted_tversky(pred, truth)["score"]
        constant = distance_weighted_tversky(np.full(truth.shape, 0.1, dtype=np.float32), truth)["score"]
        self.assertGreater(learned, constant)
        self.assertGreater(learned, 0.25)

    def test_joblib_roundtrip_preserves_predictions(self):
        arr, truth = synthetic_features_labels(32)
        med, scale = robust_band_stats(arr)
        cube = feature_stack(arr, med, scale)
        rows, cols, target = choose_training_coordinates(
            truth, max_positive=60, negatives_per_positive=1.5, seed=19
        )
        x = cube[:, rows, cols].T
        bundle = fit_model(x, target, rows, cols, block_size=8, n_splits=4, random_state=19)
        expected = predict_matrix(bundle, x[:20])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.joblib"
            joblib.dump(bundle, path)
            loaded = joblib.load(path)
            actual = predict_matrix(loaded, x[:20])
        np.testing.assert_allclose(actual, expected, rtol=0, atol=0)


class RasterContractTests(unittest.TestCase):
    def test_contract_rejects_wrong_crs(self):
        arr, truth = synthetic_features_labels(16)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.tif"
            write_raster(path, arr, crs="EPSG:4326")
            with rasterio.open(path) as src:
                with self.assertRaises(GemsError):
                    validate_feature_raster(src)

    def test_label_alignment_rejects_shape_drift(self):
        arr, _ = synthetic_features_labels(16)
        with tempfile.TemporaryDirectory() as temp:
            feature = Path(temp) / "features.tif"
            label = Path(temp) / "labels.tif"
            write_raster(feature, arr)
            write_raster(label, np.zeros((8, 8), dtype=np.uint8), dtype="uint8")
            with self.assertRaises(GemsError):
                validate_label_alignment(feature, label)

    def test_end_to_end_train_predict_verify_and_score(self):
        arr, truth = synthetic_features_labels(48)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            feature = root / "features.tif"
            label = root / "labels.tif"
            model = root / "model.joblib"
            submission = root / "submission.tif"
            write_raster(feature, arr)
            write_raster(label, truth, dtype="uint8")
            bundle = train_from_rasters(
                feature,
                label,
                model,
                max_positive=100,
                negatives_per_positive=2.0,
                seed=23,
            )
            self.assertGreater(bundle["training"]["samples"], 100)
            predict_raster(feature, model, submission, tile_size=24)
            receipt = validate_submission(feature, submission)
            self.assertEqual(receipt["dtype"], "float32")
            self.assertEqual(receipt["finite_pixels"], 48 * 48)
            score = score_rasters(submission, label)
            self.assertGreater(score["score"], 0.15)

    def test_submission_validator_rejects_float64(self):
        arr, _ = synthetic_features_labels(12)
        with tempfile.TemporaryDirectory() as temp:
            feature = Path(temp) / "features.tif"
            submission = Path(temp) / "submission.tif"
            write_raster(feature, arr)
            write_raster(submission, np.zeros((12, 12)), dtype="float64")
            with self.assertRaises(GemsError):
                validate_submission(feature, submission)


if __name__ == "__main__":
    unittest.main()
