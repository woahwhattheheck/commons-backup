from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np
from sklearn.metrics import r2_score

HERE = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(HERE))

from toolkit import (  # noqa: E402
    BREAKDOWN_WINDOW_MS,
    ContractError,
    D3D_COMPOSITE_GATE,
    GRID_SHAPE,
    OFFICIAL_SCORING_VERSION,
    OFFICIAL_STARTER_SHA,
    Prediction,
    ShotGroupedPCARidge,
    align_mast_thomson_core,
    balanced_frame_indices,
    bounded_interp,
    compile_bundle,
    compile_submission_npz,
    contract_snapshot,
    extract_features,
    grouped_cross_validate,
    read_npz_strict,
    repair_d3d_ip_times,
    shot_group_folds,
    transfer_retention,
    validate_prediction_arrays,
    verify_bundle,
    write_deterministic_npz,
)


def _base_geometry(machine: str, t: np.ndarray) -> dict:
    if machine == "DIII-D":
        cols = np.array(["magnetics_F1A", "magnetics_F1A", "magnetics_F2A", "magnetics_F2A", "magnetics_ECOILA"])
        keys = {
            "magnetics_F1A": 200_000 * np.sin(t / 400),
            "magnetics_F2A": -150_000 * np.cos(t / 500),
            "magnetics_ECOILA": 90_000 * np.sin(t / 300),
        }
        rgrid = np.linspace(0.8, 2.8, 65)
        zgrid = np.linspace(-1.6, 1.6, 65)
    else:
        cols = np.array(["magnetics_p2l_current", "magnetics_p2l_current", "magnetics_p3u_current", "magnetics_sol_current", "magnetics_sol_current"])
        keys = {
            "magnetics_p2l_current": 18 * np.sin(t / 400),
            "magnetics_p3u_current": -12 * np.cos(t / 500),
            "magnetics_sol_current": 8 * np.sin(t / 300),
        }
        rgrid = np.linspace(0.06, 2.0, 65)
        zgrid = np.linspace(-2.0, 2.0, 65)
    row = {
        "source": machine,
        "efit_times": np.linspace(0, 900, 7),
        "efit_grid_R": rgrid,
        "efit_grid_Z": zgrid,
        "coil_input_column": cols,
        "coil_R": np.linspace(rgrid.min() + 0.1, rgrid.max() - 0.1, len(cols)),
        "coil_Z": np.linspace(zgrid.min() + 0.2, zgrid.max() - 0.2, len(cols)),
        "magnetics_time": t,
    }
    row.update(keys)
    return row


def synthetic_row(machine: str = "DIII-D") -> dict:
    t = np.linspace(-1000, 1500, 251)
    row = _base_geometry(machine, t)
    ip = 1_000_000 / (1 + np.exp(-(t - 0) / 35))
    if machine == "DIII-D":
        row["magnetics_plasma_current"] = ip
        row["magnetics_plasma_current_times"] = t.copy()
        row["magnetics_bcoil"] = 350_000 + 20_000 * np.cos(t / 700)
    else:
        # MAST early-campaign style union axis holes: different columns finite on
        # different native samples, but every finite native grid spans the plasma.
        ip = ip / 1000
        tf = 350 + 20 * np.cos(t / 700)
        ip[::5] = np.nan
        tf[1::5] = np.nan
        row["magnetics_plasma_current"] = ip
        row["magnetics_tf_current"] = tf

    ts_t = np.linspace(-100, 1000, 18)
    core = np.vstack([np.linspace(100 + i, 700 + i, 8) for i in range(ts_t.size)])
    edge = np.vstack([np.linspace(80 + i, 450 + i, 5) for i in range(ts_t.size)])
    if machine == "MAST":
        core = np.column_stack([np.full(ts_t.size, np.nan), core])
        row["thomson_core_R"] = np.linspace(0.25, 1.5, 8)
    else:
        row["thomson_core_R"] = np.full(8, 1.94)
    row.update({
        "thomson_core_times": ts_t,
        "thomson_core_Te": core,
        "thomson_core_ne": core * 1e16,
        "thomson_edge_times": ts_t,
        "thomson_edge_Te": edge,
        "thomson_edge_ne": edge * 1e16,
    })
    return row


class ContractTests(unittest.TestCase):
    def test_contract_is_pinned(self):
        c = contract_snapshot()
        self.assertEqual(c["starter_sha"], OFFICIAL_STARTER_SHA)
        self.assertEqual(c["scoring_version"], OFFICIAL_SCORING_VERSION)
        self.assertEqual(c["split_unit"], "shot")
        self.assertEqual(c["grid"], [65, 65])

    def test_group_folds_are_deterministic_and_disjoint(self):
        ids = [f"s{i}" for i in range(11)] * 3
        a = shot_group_folds(ids, 4, 17)
        b = shot_group_folds(ids, 4, 17)
        self.assertEqual(a, b)
        seen = set()
        for fold in a:
            self.assertFalse(set(fold.train_shots) & set(fold.valid_shots))
            seen.update(fold.valid_shots)
        self.assertEqual(seen, {f"s{i}" for i in range(11)})

    def test_group_folds_reject_too_few_shots(self):
        with self.assertRaises(ValueError):
            shot_group_folds(["a", "a"], 2)

    def test_transfer_gate(self):
        self.assertEqual(transfer_retention(D3D_COMPOSITE_GATE - 1e-6, 0.9), 0.0)
        self.assertAlmostEqual(transfer_retention(0.9, 0.72), 0.8)


class ErrataAndResamplingTests(unittest.TestCase):
    def test_ip_axis_kept_when_breakdown_near_zero(self):
        t = np.linspace(-1000, 1000, 201)
        ip = 1_000_000 / (1 + np.exp(-t / 20))
        row = {"magnetics_plasma_current_times": t, "magnetics_plasma_current": ip, "magnetics_time": t - 3000}
        fixed = repair_d3d_ip_times(row)
        np.testing.assert_allclose(fixed, t)

    def test_ip_axis_rebased_when_breakdown_seconds_off(self):
        true_t = np.linspace(-1000, 1000, 201)
        shipped = true_t + 3000
        ip = 1_000_000 / (1 + np.exp(-true_t / 20))
        row = {"magnetics_plasma_current_times": shipped, "magnetics_plasma_current": ip, "magnetics_time": true_t}
        fixed = repair_d3d_ip_times(row)
        np.testing.assert_allclose(fixed, true_t)

    def test_mast_ghost_channel_dropped(self):
        row = {
            "thomson_core_R": [0.2, 0.3],
            "thomson_core_Te": [[np.nan, 1, 2], [np.nan, 3, 4]],
            "thomson_core_ne": [[np.nan, 5, 6], [np.nan, 7, 8]],
        }
        r, te, ne = align_mast_thomson_core(row)
        self.assertEqual(te.shape, (2, 2))
        self.assertTrue(np.isfinite(te).all())
        np.testing.assert_array_equal(r, [0.2, 0.3])
        np.testing.assert_array_equal(ne[:, 0], [5, 7])

    def test_sparse_union_axis_uses_only_finite_samples(self):
        t = np.arange(6.0)
        y = np.array([0.0, np.nan, 2.0, np.nan, 4.0, np.nan])
        out, covered = bounded_interp(t, y, [1.0, 2.0, 3.0, 5.0])
        np.testing.assert_allclose(out[:3], [1, 2, 3])
        self.assertTrue(covered[:3].all())
        self.assertFalse(covered[-1])
        self.assertEqual(out[-1], 4.0)

    def test_duplicate_native_times_are_not_ambiguous(self):
        out, covered = bounded_interp([0, 1, 1, 2], [0, 1, 3, 4], [1])
        self.assertEqual(float(out[0]), 2.0)
        self.assertTrue(bool(covered[0]))


class FeatureTests(unittest.TestCase):
    def test_d3d_features_are_finite_and_fixed_width(self):
        x = extract_features(synthetic_row("DIII-D"))
        self.assertEqual(x.shape, (7, 46))
        self.assertTrue(np.isfinite(x).all())

    def test_mast_features_handle_sparse_magnetics_and_ghost_channel(self):
        x = extract_features(synthetic_row("MAST"))
        self.assertEqual(x.shape, (7, 46))
        self.assertTrue(np.isfinite(x).all())

    def test_targets_cannot_change_features(self):
        row = synthetic_row("DIII-D")
        x1 = extract_features(row)
        row["efit_psirz"] = np.random.default_rng(1).normal(size=(7, 65, 65))
        row["efit_q95"] = np.arange(7.0) + 99
        row["efit_beta_n"] = np.arange(7.0) - 99
        x2 = extract_features(row)
        np.testing.assert_array_equal(x1, x2)

    def test_other_shot_cannot_change_row_features(self):
        row = synthetic_row("MAST")
        before = extract_features(row)
        other = synthetic_row("DIII-D")
        other["magnetics_F1A"] *= 1e12
        _ = extract_features(other)
        after = extract_features(row)
        np.testing.assert_array_equal(before, after)

    def test_unknown_machine_fails_closed(self):
        row = synthetic_row("DIII-D")
        row["source"] = "mystery"
        with self.assertRaises(ContractError):
            extract_features(row)


class ModelTests(unittest.TestCase):
    def _toy(self):
        rng = np.random.default_rng(7)
        frames_per = 8
        shots = 9
        ids = np.repeat([f"s{i}" for i in range(shots)], frames_per)
        x = rng.normal(size=(ids.size, 6))
        # Deliberately low-rank maps so PCA+ridge has a learnable exact-ish task.
        basis = rng.normal(size=(3, 65 * 65)) * 0.1
        z = np.column_stack([x[:, 0] + 0.2*x[:, 1], x[:, 2]-x[:, 3], x[:, 4]+0.5*x[:, 5]])
        psi = (z @ basis).reshape((-1, 65, 65))
        q = 2*x[:, 0] - x[:, 2]
        b = -x[:, 1] + 0.3*x[:, 5]
        return x, psi, q, b, ids

    def test_balanced_sampling_caps_each_shot(self):
        ids = ["a"] * 100 + ["b"] * 3
        idx = balanced_frame_indices(ids, 5, 9)
        got = np.asarray(ids, dtype=object)[idx]
        self.assertEqual(int(np.sum(got == "a")), 5)
        self.assertEqual(int(np.sum(got == "b")), 3)

    def test_fit_predict_shapes_and_quality(self):
        x, psi, q, b, ids = self._toy()
        m = ShotGroupedPCARidge(n_components=6, max_frames_per_shot=20).fit(x, psi, q, b, ids)
        p = m.predict(x)
        self.assertEqual(p.psirz.shape, psi.shape)
        self.assertGreater(r2_score(psi.reshape(-1), p.psirz.reshape(-1)), 0.95)
        self.assertGreater(r2_score(q, p.q95), 0.95)

    def test_grouped_cv_runs_on_disjoint_shots(self):
        x, psi, q, b, ids = self._toy()
        scores = grouped_cross_validate(x, psi, q, b, ids, n_splits=3, n_components=3)
        self.assertEqual(len(scores), 3)
        self.assertTrue(all(s.n_shots == 3 for s in scores))
        self.assertTrue(all(np.isfinite(s.partial_composite) for s in scores))

    def test_fit_rejects_one_shot(self):
        x, psi, q, b, ids = self._toy()
        with self.assertRaises(ContractError):
            ShotGroupedPCARidge().fit(x[:8], psi[:8], q[:8], b[:8], ["one"] * 8)


class PackagingTests(unittest.TestCase):
    @staticmethod
    def _pred(t: int, value: float = 0.25) -> Prediction:
        return Prediction(
            np.full((t, 65, 65), value, dtype=np.float32),
            np.linspace(2, 3, t, dtype=np.float32),
            np.linspace(1, 2, t, dtype=np.float32),
        )

    def test_deterministic_npz_is_byte_identical(self):
        arrays = {"b": np.arange(3, dtype=np.float32), "a": np.arange(2, dtype=np.float32)}
        with tempfile.TemporaryDirectory() as td:
            p1, p2 = Path(td)/"a.npz", Path(td)/"b.npz"
            h1 = write_deterministic_npz(p1, arrays)
            h2 = write_deterministic_npz(p2, arrays)
            self.assertEqual(h1, h2)
            self.assertEqual(p1.read_bytes(), p2.read_bytes())

    def test_compile_npz_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"diii_d_public_test.npz"
            compile_submission_npz(p, [self._pred(2), self._pred(3)], [2, 3], "DIII-D")
            arrays = read_npz_strict(p)
            validate_prediction_arrays(arrays, [2, 3], "DIII-D")
            self.assertEqual(len(arrays), 6)

    def test_validator_rejects_extra_key(self):
        arrays = {
            "shot_0000_psirz": np.zeros((2, 65, 65), np.float32),
            "shot_0000_q95": np.zeros(2, np.float32),
            "shot_0000_betaN": np.zeros(2, np.float32),
            "shot_0000_li": np.zeros(2, np.float32),
        }
        with self.assertRaises(ContractError):
            validate_prediction_arrays(arrays, [2], "DIII-D")

    def test_validator_rejects_d3d_nonfinite(self):
        p = self._pred(2)
        bad = p.psirz.copy(); bad[0, 0, 0] = np.nan
        arrays = {
            "shot_0000_psirz": bad,
            "shot_0000_q95": p.q95,
            "shot_0000_betaN": p.betaN,
        }
        with self.assertRaises(ContractError):
            validate_prediction_arrays(arrays, [2], "DIII-D")

    def test_bundle_is_deterministic_and_manifest_bound(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td)/"one", Path(td)/"two"
            r1 = compile_bundle(a, [self._pred(2)], [2], [self._pred(3)], [3])
            r2 = compile_bundle(b, [self._pred(2)], [2], [self._pred(3)], [3])
            self.assertEqual(r1, r2)
            verify_bundle(a)
            verify_bundle(b)

    def test_bundle_tamper_fails(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            compile_bundle(out, [self._pred(2)], [2], [self._pred(3)], [3])
            p = out / "mast_public_test.npz"
            p.write_bytes(p.read_bytes() + b"tamper")
            with self.assertRaises(ContractError):
                verify_bundle(out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
