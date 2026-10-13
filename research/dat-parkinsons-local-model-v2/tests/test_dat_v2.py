from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dat_v2.artifact import validate_model_artifact
from dat_v2.contract import FEATURE_NAMES, FEATURE_VERSION, MAX_WORKING_AXIS, ModelContractError, canonical_json
from dat_v2.core import extract_features, predict_volume, prepare_volume, train_feature_model
from dat_v2.io import parse_json_strict, write_model_json
from dat_v2.pack import build_bundle, verify_bundle


def synthetic_matrix() -> tuple[np.ndarray, np.ndarray, list[str]]:
    rng = np.random.default_rng(20260914)
    y = np.asarray([index % 2 for index in range(24)], dtype=np.int64)
    X = rng.normal(0.0, 0.35, size=(24, len(FEATURE_NAMES)))
    X[:, 0] += y * 0.65
    X[:, 5] -= y * 0.20
    groups = [f"group-{index // 2:02d}" for index in range(24)]
    return X, y, groups


def trained_artifact(*, grouped: bool = True) -> tuple[dict, dict]:
    X, y, groups = synthetic_matrix()
    return train_feature_model(
        X,
        y,
        FEATURE_NAMES,
        groups=groups if grouped else None,
        n_splits=4,
        seed=20260914,
    )


class DaTV2HostileTests(unittest.TestCase):
    def test_01_feature_schema_is_unique_and_versioned(self):
        self.assertEqual(FEATURE_VERSION, "dat-v2-features/v2")
        self.assertGreater(len(FEATURE_NAMES), 100)
        self.assertEqual(len(FEATURE_NAMES), len(set(FEATURE_NAMES)))

    def test_02_bounded_preprocessing_caps_each_axis(self):
        rng = np.random.default_rng(2)
        volume = rng.normal(size=(130, 101, 99)).astype(np.float32)
        prepared = prepare_volume(volume)
        self.assertEqual(prepared.ndim, 3)
        self.assertLessEqual(max(prepared.shape), MAX_WORKING_AXIS)
        self.assertGreaterEqual(min(prepared.shape), 4)
        self.assertTrue(np.isfinite(prepared).all())

    def test_03_nonfinite_volume_fails_closed(self):
        volume = np.zeros((8, 8, 8), dtype=np.float32)
        volume[0, 0, 0] = np.nan
        with self.assertRaises(ModelContractError):
            extract_features(volume)

    def test_04_shape_and_orientation_variants_are_finite_and_fixed_width(self):
        rng = np.random.default_rng(4)
        base = rng.random((11, 13, 17), dtype=np.float32)
        variants = [base, base[::-1], np.transpose(base, (2, 0, 1)), np.flip(base, axis=2)]
        for volume in variants:
            vector, names = extract_features(volume)
            self.assertEqual(tuple(names), FEATURE_NAMES)
            self.assertEqual(vector.shape, (len(FEATURE_NAMES),))
            self.assertTrue(np.isfinite(vector).all())

    def test_05_feature_extraction_is_deterministic(self):
        rng = np.random.default_rng(5)
        volume = rng.random((17, 19, 23), dtype=np.float32)
        first, names1 = extract_features(volume)
        second, names2 = extract_features(volume.copy())
        np.testing.assert_array_equal(first, second)
        self.assertEqual(names1, names2)

    def test_06_grouped_training_records_group_authority_and_excludes_rows(self):
        artifact, receipt = trained_artifact(grouped=True)
        self.assertEqual(receipt["split"]["kind"], "stratified_group")
        self.assertTrue(receipt["split"]["group_authority_supplied"])
        self.assertEqual(receipt["split"]["unique_group_count"], 12)
        self.assertEqual(artifact["privacy_contract"], {
            "contains_training_rows": False,
            "contains_row_identifiers": False,
            "contains_groups_or_sites": False,
            "contains_paths": False,
        })
        validate_model_artifact(artifact)

    def test_07_missing_group_authority_is_explicit_fallback(self):
        _, receipt = trained_artifact(grouped=False)
        self.assertEqual(receipt["split"]["kind"], "stratified_fallback")
        self.assertFalse(receipt["split"]["group_authority_supplied"])
        self.assertIn("cannot be ruled out", receipt["split"]["warning"])

    def test_08_training_is_deterministic_for_same_public_synthetic_inputs(self):
        artifact1, receipt1 = trained_artifact(grouped=True)
        artifact2, receipt2 = trained_artifact(grouped=True)
        self.assertEqual(canonical_json(artifact1), canonical_json(artifact2))
        self.assertEqual(canonical_json(receipt1), canonical_json(receipt2))

    def test_09_artifact_tamper_fails_digest_validation(self):
        artifact, _ = trained_artifact(grouped=True)
        tampered = copy.deepcopy(artifact)
        tampered["branches"][0]["coef"][0] += 0.1
        with self.assertRaises(ModelContractError):
            validate_model_artifact(tampered)

    def test_10_single_volume_inference_is_finite_probability(self):
        artifact, _ = trained_artifact(grouped=True)
        rng = np.random.default_rng(10)
        probability = predict_volume(rng.random((12, 14, 16), dtype=np.float32), artifact)
        self.assertTrue(np.isfinite(probability))
        self.assertGreaterEqual(probability, 0.0)
        self.assertLessEqual(probability, 1.0)

    def test_11_strict_json_rejects_duplicate_keys_and_nonfinite_constants(self):
        with self.assertRaises(ModelContractError):
            parse_json_strict('{"a":1,"a":2}')
        with self.assertRaises(ModelContractError):
            parse_json_strict('{"a":NaN}')

    def test_12_bundle_is_deterministic_verified_and_whitelist_only(self):
        artifact, _ = trained_artifact(grouped=True)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            model = td / "model.json"
            one = td / "one.zip"
            two = td / "two.zip"
            write_model_json(model, artifact)
            build_bundle(model, one, source_root=ROOT)
            build_bundle(model, two, source_root=ROOT)
            self.assertEqual(one.read_bytes(), two.read_bytes())
            manifest = verify_bundle(one)
            self.assertEqual(manifest["model_sha256"], artifact["model_sha256"])
            with zipfile.ZipFile(one, "r") as archive:
                names = set(archive.namelist())
            self.assertNotIn("training.csv", names)
            self.assertNotIn("manifest.csv", names)
            self.assertNotIn("oof.npy", names)
            self.assertIn("main.py", names)
            self.assertIn("model_backend.py", names)
            self.assertIn("model.json", names)

    def test_13_bundle_rejects_extra_member(self):
        artifact, _ = trained_artifact(grouped=True)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            model = td / "model.json"
            good = td / "good.zip"
            bad = td / "bad.zip"
            write_model_json(model, artifact)
            build_bundle(model, good, source_root=ROOT)
            with zipfile.ZipFile(good, "r") as source, zipfile.ZipFile(bad, "w") as target:
                for info in source.infolist():
                    target.writestr(info, source.read(info.filename))
                target.writestr("private-training.csv", b"forbidden")
            with self.assertRaises(ModelContractError):
                verify_bundle(bad)

    def test_14_public_tree_contains_no_data_or_fitted_model_artifact(self):
        forbidden_suffixes = (".nii", ".nii.gz", ".npy", ".npz", ".pt", ".pth", ".joblib")
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            lower = path.name.lower()
            self.assertFalse(any(lower.endswith(suffix) for suffix in forbidden_suffixes), str(path))
            self.assertNotEqual(path.name, "model.json", str(path))

    def test_15_entrypoint_remains_single_scan_and_no_training_api(self):
        main_text = (ROOT / "submission_template/main.py").read_text(encoding="utf-8")
        backend_text = (ROOT / "submission_template/model_backend.py").read_text(encoding="utf-8")
        self.assertIn("predict_probability(scan)", main_text)
        self.assertIn("predict_volume(volume, _MODEL)", backend_text)
        self.assertNotIn("train_feature_model", main_text + backend_text)
        self.assertNotIn("fit(", main_text + backend_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
