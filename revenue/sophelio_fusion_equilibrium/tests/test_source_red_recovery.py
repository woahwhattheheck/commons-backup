from __future__ import annotations

from hashlib import sha256
import inspect
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

HERE = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(HERE))

import submission_bundle as bundle_mod  # noqa: E402
from toolkit import (  # noqa: E402
    ContractError,
    D3D_TRAIN_SHOTS,
    Prediction,
    ShotGroupedPCARidge,
    capture_public_test_lengths,
    compile_bundle,
    compile_real_bundle,
    target_storage_bytes,
    validate_prediction_arrays,
    verify_bundle,
    verify_real_bundle,
)


def _pred(t: int, value: float = 0.0) -> Prediction:
    return Prediction(
        np.full((t, 65, 65), value, dtype=np.float32),
        np.zeros(t, dtype=np.float32),
        np.zeros(t, dtype=np.float32),
    )


def _rows(count: int, length: int = 1):
    for _ in range(count):
        yield {"efit_times": np.arange(length, dtype=np.float64)}


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


class _IndexOnlyTargets:
    """Array-like that fails if the model attempts whole-fold materialization."""

    def __init__(self, data: np.ndarray):
        self.data = data
        self.shape = data.shape
        self.full_array_conversions = 0
        self.indexed_frames = 0

    def __array__(self, *args, **kwargs):
        self.full_array_conversions += 1
        raise AssertionError("whole-fold target materialization attempted")

    def __getitem__(self, index):
        result = self.data[index]
        if getattr(result, "ndim", 0) == 3:
            self.indexed_frames += int(result.shape[0])
        else:
            self.indexed_frames += 1
        return result


class MemoryBoundedTrainingTests(unittest.TestCase):
    def test_batch_fit_selects_before_target_conversion(self):
        rng = np.random.default_rng(11)
        shots = 160
        ids = np.repeat([f"s{i}" for i in range(shots)], 2)
        x = rng.normal(size=(ids.size, 4))
        y = rng.normal(scale=0.01, size=(ids.size, 65, 65)).astype(np.float32)
        q = rng.normal(size=ids.size)
        b = rng.normal(size=ids.size)
        guarded = _IndexOnlyTargets(y)
        model = ShotGroupedPCARidge(
            n_components=2,
            max_frames_per_shot=2,
            max_retained_frames=180,
            pca_batch_size=32,
        ).fit(x, guarded, q, b, ids)
        self.assertEqual(guarded.full_array_conversions, 0)
        self.assertEqual(guarded.indexed_frames, 180)
        self.assertEqual(model.retained_frame_count, 180)
        self.assertLessEqual(model.retained_target_bytes, target_storage_bytes(180))

    def test_stream_fit_has_hard_global_target_budget(self):
        rng = np.random.default_rng(12)
        expected_shots = 9

        def stream():
            for shot in range(expected_shots):
                n = 8
                x = rng.normal(size=(n, 5))
                y = rng.normal(scale=0.01, size=(n, 65, 65)).astype(np.float32)
                q = rng.normal(size=n)
                b = rng.normal(size=n)
                yield f"s{shot}", x, y, q, b

        model = ShotGroupedPCARidge(
            n_components=3,
            max_frames_per_shot=8,
            max_retained_frames=20,
            pca_batch_size=8,
        ).fit_shot_stream(stream(), expected_shots=expected_shots)
        self.assertEqual(model.retained_frame_count, 20)
        self.assertLessEqual(model.retained_target_bytes, target_storage_bytes(20))

    def test_real_scale_memory_receipt_closes_predecessor_shape(self):
        lower_bound_frames = ((D3D_TRAIN_SHOTS + 1) // 2) * 241 + (D3D_TRAIN_SHOTS // 2)
        self.assertGreater(target_storage_bytes(lower_bound_frames, itemsize=8), 20 * 1024**3)
        self.assertLess(target_storage_bytes(8192), 256 * 1024**2)


class FullFoldBundleAuthorityTests(unittest.TestCase):
    def test_incomplete_and_extra_public_fold_streams_fail(self):
        with self.assertRaises(ContractError):
            capture_public_test_lengths(_rows(873), "DIII-D", source_receipt_sha256="a" * 64)
        with self.assertRaises(ContractError):
            capture_public_test_lengths(_rows(1205), "MAST", source_receipt_sha256="b" * 64)
        with self.assertRaises(ContractError):
            capture_public_test_lengths(_rows(875), "DIII-D", source_receipt_sha256="a" * 64)

    def test_length_order_is_receipt_bound(self):
        a = capture_public_test_lengths(
            ({"efit_times": np.arange(1 if i < 873 else 2, dtype=np.float64)} for i in range(874)),
            "DIII-D",
            source_receipt_sha256="a" * 64,
        )
        b = capture_public_test_lengths(
            ({"efit_times": np.arange(2 if i == 0 else 1, dtype=np.float64)} for i in range(874)),
            "DIII-D",
            source_receipt_sha256="a" * 64,
        )
        self.assertNotEqual(a.sha256, b.sha256)

    def test_fixture_bundle_is_never_real_terminal_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            compile_bundle(out, [_pred(2)], [2], [_pred(3)], [3])
            fixture = verify_bundle(out)
            self.assertTrue(fixture["truth"]["fixture_only"])
            with self.assertRaises(ContractError):
                verify_real_bundle(out)

    def test_real_compiler_has_no_caller_supplied_authority_parameters(self):
        params = tuple(inspect.signature(compile_real_bundle).parameters)
        self.assertEqual(params, ("out_dir", "d3d_predictions", "mast_predictions"))

    def test_full_cardinality_self_mint_cannot_unlock_terminal_compiler(self):
        # These candidate manifests are internally consistent and exactly match
        # the organizer row cardinalities. They are deliberately NOT authority.
        d3d = capture_public_test_lengths(_rows(874), "DIII-D", source_receipt_sha256="a" * 64)
        mast = capture_public_test_lengths(_rows(1206), "MAST", source_receipt_sha256="b" * 64)
        self.assertEqual(len(d3d.lengths), 874)
        self.assertEqual(len(mast.lengths), 1206)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "terminal"
            with self.assertRaisesRegex(ContractError, "provider fold authority is not verified"):
                compile_real_bundle(out, [], [])
            self.assertFalse(out.exists())

    def test_checked_in_authority_is_source_pinned_and_capture_required(self):
        raw = (HERE / "provider_fold_authority.json").read_bytes()
        self.assertEqual(
            sha256(raw).hexdigest(),
            "cb40cf0f0a764a3e23cbb59626503d4b02e2c303bcf48c66e1761cbc87343a21",
        )
        with self.assertRaisesRegex(ContractError, "provider fold authority is not verified"):
            bundle_mod._parse_provider_authority_bytes(
                raw,
                "cb40cf0f0a764a3e23cbb59626503d4b02e2c303bcf48c66e1761cbc87343a21",
            )

    def test_positive_verified_parser_uses_independently_pinned_bytes(self):
        # Synthetic architecture fixture only. The literal digest is pinned
        # independently of the parser call; these bytes are never accepted by
        # compile_real_bundle, whose production pin is a different source literal.
        fixture = {
            "schema": "sophelio-fusion-equilibrium/provider-fold-authority-v1",
            "status": "verified",
            "dataset": "Sophelio/fusion-equilibrium-challenge",
            "starter_sha": "a67429165b09eb81c311d44db6ff11743f108b0e",
            "provider_revision": "1" * 40,
            "folds": {
                "diii_d_public_test": {
                    "machine": "DIII-D",
                    "shots": 874,
                    "lengths": [1] * 874,
                    "shards": [{
                        "path": "data/diii_d_public_test-00000-of-00001.parquet",
                        "size": 101,
                        "sha256": "2" * 64,
                    }],
                },
                "mast_public_test": {
                    "machine": "MAST",
                    "shots": 1206,
                    "lengths": [1] * 1206,
                    "shards": [{
                        "path": "data/mast_public_test-00000-of-00001.parquet",
                        "size": 202,
                        "sha256": "3" * 64,
                    }],
                },
            },
        }
        raw = _canonical(fixture)
        pinned = "2bcdf8071bc713b01e1e67b6399234db3074284ffbd13aa774b4e97c04cc7d6f"
        self.assertEqual(sha256(raw).hexdigest(), pinned)
        authority = bundle_mod._parse_provider_authority_bytes(raw, pinned)
        self.assertEqual(authority.provider_revision, "1" * 40)
        self.assertEqual(len(authority.d3d_fold.lengths), 874)
        self.assertEqual(len(authority.mast_fold.lengths), 1206)
        self.assertNotEqual(authority.d3d_fold.source_receipt_sha256, "a" * 64)

        tampered = raw.replace(b'"size":101', b'"size":102', 1)
        self.assertNotEqual(sha256(tampered).hexdigest(), pinned)
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            bundle_mod._parse_provider_authority_bytes(tampered, pinned)

    def test_mast_nonfinite_prediction_fails_closed(self):
        p = _pred(2)
        bad = p.psirz.copy()
        bad[0, 0, 0] = np.nan
        arrays = {
            "shot_0000_psirz": bad,
            "shot_0000_q95": p.q95,
            "shot_0000_betaN": p.betaN,
        }
        with self.assertRaises(ContractError):
            validate_prediction_arrays(arrays, [2], "MAST")


if __name__ == "__main__":
    unittest.main(verbosity=2)
