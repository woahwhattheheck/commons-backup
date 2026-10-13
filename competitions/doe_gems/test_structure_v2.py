from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from scipy.ndimage import gaussian_filter

try:
    from . import structure_v2 as v2
except ImportError:
    import structure_v2 as v2


def make_scene(seed: int = 1, n: int = 96) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    truth = np.zeros((n, n), np.uint8)

    xs = np.arange(7, n - 7)
    y1 = (0.20 * n + 0.22 * (xs - 7) + 2.2 * np.sin(xs / 11)).astype(int)
    truth[y1, xs] = 1
    y2 = (0.76 * n - 0.34 * (xs - 7) + 1.7 * np.sin(xs / 13)).astype(int)
    truth[y2, xs] = 1

    ys = np.arange(9, n - 9)
    x3 = (0.49 * n + 0.10 * (ys - 9) + 1.8 * np.sin(ys / 10)).astype(int)
    truth[ys, x3] = 1

    base = gaussian_filter(truth.astype(float), 1.0)
    base = base / max(float(base.max()), 1e-12) * 0.72

    # Bounded missing segments that a continuity decoder can plausibly bridge.
    for start in (22, 44, 66):
        if start < n - 3:
            cy = int(0.20 * n + 0.22 * (start - 7) + 2.2 * np.sin(start / 11))
            base[max(0, cy - 1) : min(n, cy + 2), start : start + 3] *= 0.06

    base += rng.uniform(0.0, 0.035, size=(n, n))
    rr = rng.integers(0, n, 45)
    cc = rng.integers(0, n, 45)
    base[rr, cc] = rng.uniform(0.12, 0.30, size=len(rr))
    return np.clip(base, 0.0, 1.0).astype(np.float32), truth


class StructureV2Tests(unittest.TestCase):
    def test_gap_bridge_needs_bilateral_support(self):
        p = np.zeros((31, 31), np.float32)
        p[15, 4:27] = 0.8
        p[15, 14:17] = 0.03
        cfg = v2.StructureConfig(
            radius_steps=3,
            min_side_support=0.10,
            seed_floor=0.02,
            seed_neighborhood=0.2,
            coherence_power=0.5,
            blend=0.75,
        )
        out = v2.apply_structure(p, cfg)
        self.assertGreater(float(out[15, 15]), 0.25)
        self.assertEqual(float(out[5, 5]), 0.0)

    def test_one_sided_endpoint_does_not_extrapolate(self):
        p = np.zeros((31, 31), np.float32)
        p[15, 5:16] = 0.85
        cfg = v2.StructureConfig(
            radius_steps=3,
            min_side_support=0.10,
            seed_floor=0.0,
            seed_neighborhood=0.1,
            blend=1.0,
        )
        out = v2.apply_structure(p, cfg)
        self.assertEqual(float(out[15, 18]), 0.0)
        self.assertEqual(float(out[15, 20]), 0.0)

    def test_nan_mask_is_preserved(self):
        p = np.zeros((15, 15), np.float32)
        p[7, 2:13] = 0.8
        p[0:3, 0:3] = np.nan
        out = v2.apply_structure(p, v2.StructureConfig())
        self.assertTrue(np.isnan(out[0:3, 0:3]).all())
        self.assertTrue(np.isfinite(out[3:, 3:]).all())

    def test_noop_config_is_exact(self):
        p, _ = make_scene()
        cfg = v2.StructureConfig(blend=0.0)
        out = v2.apply_structure(p, cfg)
        np.testing.assert_array_equal(out, p)

    def test_invalid_probabilities_fail_closed(self):
        p = np.zeros((10, 10), np.float32)
        p[3, 4] = 1.1
        with self.assertRaises(v2.GemsError):
            v2.apply_structure(p, v2.StructureConfig())

    def test_directional_structure_finds_horizontal_axis(self):
        p = np.zeros((21, 21), np.float32)
        p[10, 2:19] = 0.9
        result = v2.directional_structure(p, radius_steps=2)
        self.assertEqual(int(result["direction_index"][10, 10]), 0)
        self.assertGreater(float(result["coherence"][10, 10]), 0.9)

    def test_default_selection_never_worse_than_baseline_on_validation(self):
        p, truth = make_scene(2)
        receipt = v2.select_config(p, truth)
        selected = float(receipt["selected"]["score"])
        baseline = float(receipt["baseline_score"])
        self.assertGreaterEqual(selected + 1e-15, baseline)

    def test_structure_selection_improves_broken_fault_fixture(self):
        p, truth = make_scene(3)
        receipt = v2.select_config(p, truth)
        self.assertGreater(
            float(receipt["selected"]["score"]),
            float(receipt["baseline_score"]) + 0.01,
        )

    def test_selection_is_deterministic_and_self_verifying(self):
        p, truth = make_scene(4)
        a = v2.select_config(p, truth)
        b = v2.select_config(p, truth)
        self.assertEqual(v2.canonical_json(a), v2.canonical_json(b))
        self.assertTrue(v2.verify_selection(p, truth, a))
        self.assertTrue(v2.receipt_integrity_valid(a))
        cfg = v2.selected_config(a)
        self.assertIsInstance(cfg, v2.StructureConfig)

    def test_receipt_tamper_is_rejected(self):
        p, truth = make_scene(5)
        receipt = v2.select_config(p, truth)
        tampered = copy.deepcopy(receipt)
        tampered["selected"]["config"]["blend"] = 1.0
        self.assertFalse(v2.receipt_integrity_valid(tampered))
        self.assertFalse(v2.verify_selection(p, truth, tampered))
        with self.assertRaises(v2.GemsError):
            v2.selected_config(tampered)

    def test_truth_on_null_probability_is_rejected(self):
        p, truth = make_scene(6)
        p = p.copy()
        fault = np.argwhere(truth == 1)[0]
        p[tuple(fault)] = np.nan
        with self.assertRaises(v2.GemsError):
            v2.select_config(p, truth)

    def test_role_other_than_validation_is_rejected(self):
        p, truth = make_scene(7)
        with self.assertRaises(v2.GemsError):
            v2.select_config(p, truth, holdout_role="test")

    def test_frozen_validation_config_generalizes_on_second_synthetic_scene(self):
        train_p, train_truth = make_scene(8)
        test_p, test_truth = make_scene(9)
        receipt = v2.select_config(train_p, train_truth)
        cfg = v2.selected_config(receipt)
        decoded = v2.apply_structure(test_p, cfg)
        base_score = v2.distance_weighted_tversky(test_p, test_truth)["score"]
        decoded_score = v2.distance_weighted_tversky(decoded, test_truth)["score"]
        self.assertGreater(decoded_score, base_score)

    def test_raster_apply_preserves_grid_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "base.tif"
            output = root / "v2.tif"
            arr, _ = make_scene(10, n=48)
            arr = arr.astype(np.float32)
            arr[0:2, 0:3] = np.nan
            profile = {
                "driver": "GTiff",
                "width": arr.shape[1],
                "height": arr.shape[0],
                "count": 1,
                "dtype": "float32",
                "crs": v2.CRS,
                "transform": from_origin(500000, 4500000, 100, 100),
                "nodata": np.nan,
            }
            with rasterio.open(source, "w", **profile) as dst:
                dst.write(arr, 1)
            result = v2.apply_raster(source, output, v2.StructureConfig())
            self.assertEqual(result["crs"], v2.CRS)
            with rasterio.open(source) as src, rasterio.open(output) as dst:
                self.assertEqual(src.shape, dst.shape)
                self.assertEqual(src.crs, dst.crs)
                self.assertTrue(src.transform.almost_equals(dst.transform))
                self.assertEqual(dst.dtypes[0], "float32")
                self.assertTrue(np.isnan(dst.read(1)[0:2, 0:3]).all())
            with self.assertRaises(v2.GemsError):
                v2.apply_raster(source, output, v2.StructureConfig())

    def test_strict_json_rejects_duplicate_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as td:
            dup = Path(td) / "dup.json"
            dup.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            with self.assertRaises(v2.GemsError):
                v2._read_json(dup)
            bad = Path(td) / "bad.json"
            bad.write_text('{"x":NaN}', encoding="utf-8")
            with self.assertRaises(v2.GemsError):
                v2._read_json(bad)

    def test_cli_select_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p, truth = make_scene(11, n=56)
            p_path = root / "p.npy"
            t_path = root / "t.npy"
            receipt_path = root / "selection.json"
            np.save(p_path, p, allow_pickle=False)
            np.save(t_path, truth, allow_pickle=False)
            select_rc = v2.main(
                [
                    "select",
                    "--probability-npy",
                    str(p_path),
                    "--truth-npy",
                    str(t_path),
                    "--selection",
                    str(receipt_path),
                ]
            )
            self.assertEqual(select_rc, 0)
            self.assertEqual(
                v2.main(
                    [
                        "verify-selection",
                        "--probability-npy",
                        str(p_path),
                        "--truth-npy",
                        str(t_path),
                        "--selection",
                        str(receipt_path),
                    ]
                ),
                0,
            )
            value = json.loads(receipt_path.read_text())
            value["baseline_score"] = 0.999
            receipt_path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(
                v2.main(
                    [
                        "verify-selection",
                        "--probability-npy",
                        str(p_path),
                        "--truth-npy",
                        str(t_path),
                        "--selection",
                        str(receipt_path),
                    ]
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
