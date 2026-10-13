"""Run: python -m unittest discover -s revenue/learn2design2026/curvature -v."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

import jax
import jax.numpy as jnp
import numpy as np

from synthetic import SyntheticObjective, load_candidate, problem

ROOT = Path(__file__).resolve().parent
MOD = load_candidate(ROOT / "submission.py")
ALGORITHM = MOD.BatchedCurvaturePortfolio


def kernel(memory=4, backtracks=4, restart_after=256):
    return MOD._kernels(memory, 0.5, 4.0, 1e-4, 0.5, 1e-8,
                        backtracks, restart_after, 1e-10)


def seed_state(n=2, d=3, memory=4):
    params = jnp.zeros((n, d), dtype=jnp.float32)
    fresh = jnp.full_like(params, 3.0)
    st = MOD._empty(params, memory, 0.5)
    return st, fresh


class CurvatureTests(unittest.TestCase):
    def run_algo(self, seed=7, batches=10, **kwargs):
        obj = SyntheticObjective(problem("sphere", 5), 5, batches, dtype=np.float32)
        ALGORITHM().optimize(obj, random_seed=seed, population_size=4, **kwargs)
        return obj

    def test_abstract_constructor_contract_fixture(self):
        self.assertIsInstance(ALGORITHM(), MOD.OptimizationAlgorithm)
        self.assertEqual(ALGORITHM.__abstractmethods__, frozenset())

    def test_lifecycle_and_final_budget_fence(self):
        obj = self.run_algo(batches=3)
        self.assertEqual(len(obj.history), 3)
        self.assertEqual(obj.events[:3], ["prepare", "warmup", "start_logging"])
        self.assertEqual(obj.events[3:], ["evaluate"] * 3)
        self.assertTrue(all(np.isfinite(x).all() for x in obj.history))

    def test_max_iterations_counts_initial_batch(self):
        obj = self.run_algo(batches=100, max_iterations=2)
        self.assertEqual(len(obj.history), 2)
        self.assertFalse(obj.budget_exceeded)

    def test_one_batch_does_not_sample_after_budget(self):
        obj = self.run_algo(batches=1)
        self.assertEqual(obj.samples, 2)
        self.assertEqual(len(obj.history), 1)

    def test_seed_replay_including_restarts(self):
        one = self.run_algo(restart_after=3)
        two = self.run_algo(restart_after=3)
        other = self.run_algo(seed=11, restart_after=3)
        np.testing.assert_array_equal(one.history, two.history)
        self.assertFalse(np.array_equal(one.history, other.history))
        self.assertGreater(one.samples, 2)

    def test_init_params_and_shape(self):
        initial = np.arange(5, dtype=np.float32)
        obj = self.run_algo(batches=1, init_params=initial)
        np.testing.assert_array_equal(obj.history[0][0], initial)
        with self.assertRaises(ValueError):
            self.run_algo(init_params=[1, 2])
        with self.assertRaises(ValueError):
            self.run_algo(init_params=[1, 2, 3, 4, np.nan])

    def test_independent_acceptance_and_rejection(self):
        st, fresh = seed_state()
        advance = kernel()
        st, _, _ = advance(st, jnp.full(2, 5.0), jnp.ones_like(st.g), fresh)
        old = st
        st, accepted, restarted = advance(st, jnp.array([4.0, 6.0]),
                                           jnp.full_like(st.g, 0.5), fresh)
        np.testing.assert_array_equal(accepted, [True, False])
        np.testing.assert_array_equal(restarted, [False, False])
        np.testing.assert_array_equal(st.x[0], old.trial[0])
        for field in ("x", "f", "g", "s", "y", "rho", "head", "count"):
            np.testing.assert_array_equal(getattr(st, field)[1], getattr(old, field)[1])
        self.assertEqual(float(st.step[1]), 0.5)
        self.assertEqual(int(st.count[0]), 1)
        self.assertEqual(int(st.count[1]), 0)

    def test_negative_curvature_not_stored(self):
        st, fresh = seed_state()
        advance = kernel()
        st, _, _ = advance(st, jnp.full(2, 5.0), jnp.ones_like(st.g), fresh)
        st, accepted, _ = advance(st, jnp.full(2, 4.0), jnp.full_like(st.g, 2.0), fresh)
        self.assertTrue(bool(jnp.all(accepted)))
        np.testing.assert_array_equal(st.count, [0, 0])
        np.testing.assert_array_equal(st.rho, np.zeros((2, 4)))
        self.assertTrue(bool(jnp.all(jnp.sum(st.direction * st.g, axis=1) < 0)))

    def test_nonfinite_initial_lane_isolated(self):
        st, fresh = seed_state()
        advance = kernel()
        good, _, _ = advance(st, jnp.array([5.0, 5.0]), jnp.ones_like(st.g), fresh)
        grads = jnp.ones_like(st.g).at[0].set(jnp.nan)
        bad, accepted, restarted = advance(st, jnp.array([jnp.nan, 5.0]), grads, fresh)
        np.testing.assert_array_equal(accepted, [False, True])
        np.testing.assert_array_equal(restarted, [True, False])
        for a, b in zip(bad, good):
            np.testing.assert_array_equal(a[1], b[1])
        np.testing.assert_array_equal(bad.trial[0], fresh[0])
        np.testing.assert_array_equal(bad.count, [0, 0])

    def test_repeated_bad_trial_resets_all_lane_state(self):
        st, fresh = seed_state()
        advance = kernel(backtracks=2)
        st, _, _ = advance(st, jnp.full(2, 5.0), jnp.ones_like(st.g), fresh)
        st, _, _ = advance(st, jnp.full(2, 4.0), jnp.full_like(st.g, 0.5), fresh)
        self.assertTrue(bool(jnp.all(st.count > 0)))
        for _ in range(2):
            st, _, restarted = advance(st, jnp.full(2, jnp.inf),
                                        jnp.full_like(st.g, jnp.nan), fresh)
        self.assertTrue(bool(jnp.all(restarted)))
        blank = MOD._empty(fresh, 4, 0.5)
        for a, b in zip(st, blank):
            np.testing.assert_array_equal(a, b)

    def test_restart_age_is_bounded(self):
        st, fresh = seed_state()
        advance = kernel(restart_after=2)
        st, _, _ = advance(st, jnp.full(2, 5.0), jnp.ones_like(st.g), fresh)
        st, _, restarted = advance(st, jnp.full(2, 4.0), jnp.full_like(st.g, 0.5), fresh)
        np.testing.assert_array_equal(restarted, [True, True])
        np.testing.assert_array_equal(st.age, [0, 0])

    def test_stationary_lane_restarts_without_erasing_objective_best(self):
        obj = SyntheticObjective(lambda x: jnp.sum(x * 0) + 2, 3, 3, dtype=np.float32)
        ALGORITHM().optimize(obj, population_size=2, random_seed=8)
        self.assertEqual(obj.best_loss, 2)
        self.assertEqual(len(obj.history), 3)
        self.assertGreater(obj.samples, 2)
        self.assertFalse(np.array_equal(obj.history[0], obj.history[1]))

    def test_float32_runtime_nonfinite_trial(self):
        def injected(batch, loss, grad):
            if batch in (0, 3):
                return loss.at[0].set(jnp.nan), grad.at[0].set(jnp.inf)
            return loss, grad
        obj = SyntheticObjective(problem("sphere", 3), 3, 8, dtype=np.float32, injected=injected)
        ALGORITHM().optimize(obj, population_size=4, random_seed=12)
        self.assertEqual(len(obj.history), 8)
        self.assertTrue(all(np.isfinite(x).all() for x in obj.history))
        self.assertIsNotNone(obj.best_loss)

    def test_cap_does_not_square_overflowing_coordinates(self):
        arr = jnp.array([[1e30, -1e30, 1e30], [0, 0, 0]], dtype=jnp.float32)
        capped = MOD._cap(arr, jnp.array([0.5, 0.5]))
        self.assertTrue(bool(jnp.all(jnp.isfinite(capped))))
        self.assertLessEqual(float(jnp.linalg.norm(capped[0])), 0.500001)
        np.testing.assert_array_equal(capped[1], [0, 0, 0])

    def test_two_loop_matches_numpy_with_wrapped_history(self):
        rng = np.random.default_rng(61)
        st, fresh = seed_state(d=5, memory=3)
        s = rng.normal(size=(2, 3, 5)).astype(np.float32)
        y = s * np.array([1, 2, 4, 8, 16], dtype=np.float32)
        rho = 1 / np.sum(s * y, axis=2)
        g = rng.normal(size=(2, 5)).astype(np.float32)
        heads, counts = np.array([1, 2], np.int32), np.array([3, 2], np.int32)
        st = st._replace(f=jnp.ones(2), g=jnp.asarray(g), s=jnp.asarray(s),
                         y=jnp.asarray(y), rho=jnp.asarray(rho), head=jnp.asarray(heads),
                         count=jnp.asarray(counts))
        result, accepted, _ = kernel(memory=3)(st, st.f, st.g, fresh)
        self.assertTrue(bool(jnp.all(accepted)))
        for lane in range(2):
            q = g[lane].astype(np.float64)
            aa = []
            slots = [(heads[lane] - 1 - i) % 3 for i in range(counts[lane])]
            for slot in slots:
                a = rho[lane, slot] * np.dot(s[lane, slot], q)
                aa.append(a)
                q = q - a * y[lane, slot]
            latest = slots[0]
            scale = np.dot(s[lane, latest], y[lane, latest]) / np.dot(y[lane, latest], y[lane, latest])
            r = scale * q
            for slot, a in reversed(list(zip(slots, aa))):
                r += s[lane, slot] * (a - rho[lane, slot] * np.dot(y[lane, slot], r))
            expected = -r
            expected *= min(1, 0.625 / np.linalg.norm(expected))
            np.testing.assert_allclose(result.direction[lane], expected, rtol=1e-5, atol=1e-6)

    def test_history_count_never_exceeds_memory(self):
        st, fresh = seed_state(d=3, memory=2)
        advance = kernel(memory=2)
        for _ in range(40):
            losses = jnp.sum((st.trial - 1) ** 2, axis=1)
            grads = 2 * (st.trial - 1)
            st, _, _ = advance(st, losses, grads, fresh)
            self.assertTrue(bool(jnp.all((st.count >= 0) & (st.count <= 2))))
            self.assertTrue(bool(jnp.all((st.head >= 0) & (st.head < 2))))
            self.assertTrue(bool(jnp.all(jnp.isfinite(st.trial))))

    def test_bad_configuration_rejected_before_logging(self):
        for kwargs in ({"population_size": True}, {"memory_size": 0}, {"memory_size": 33},
                       {"max_iterations": False}, {"max_iterations": 0},
                       {"max_backtracks": 0}, {"restart_after": 1},
                       {"initial_radius": np.inf}, {"max_radius": np.nan},
                       {"initial_radius": 5.0, "max_radius": 1.0},
                       {"armijo": 0.5}, {"shrink": 1.0}, {"min_step": 0.0},
                       {"gradient_tolerance": -1.0}, {"armijo": True}):
            with self.subTest(kwargs=kwargs):
                obj = SyntheticObjective(problem("sphere", 3), 3, 1, dtype=np.float32)
                with self.assertRaises(ValueError):
                    ALGORITHM().optimize(obj, **kwargs)
                self.assertFalse(obj.logged)
                self.assertEqual(obj.history, [])

    def test_bad_sampler_shape_and_dtype(self):
        for sample in (jnp.ones(3), jnp.ones((2, 0)), jnp.ones((2, 3), dtype=jnp.int32),
                       jnp.full((2, 3), jnp.nan)):
            obj = SyntheticObjective(problem("sphere", 3), 3, 1)
            obj.random_params_unbounded = lambda n_samples: sample
            with self.assertRaises(ValueError):
                ALGORITHM().optimize(obj, population_size=2)
            self.assertFalse(obj.logged)

    def test_bad_restart_pool_rejected_before_logging(self):
        obj = SyntheticObjective(problem("sphere", 3), 3, 1)
        original = obj.random_params_unbounded
        def sampler(n_samples):
            value = original(n_samples)
            return value if obj.samples == 1 else value.at[0, 0].set(jnp.nan)
        obj.random_params_unbounded = sampler
        with self.assertRaises(ValueError):
            ALGORITHM().optimize(obj, population_size=2)
        self.assertFalse(obj.logged)

    def test_invalid_objective_output_shape_stops(self):
        obj = SyntheticObjective(problem("sphere", 3), 3, 3, dtype=np.float32,
                                 injected=lambda i, f, g: (f[:, None], g))
        with self.assertRaises(ValueError):
            ALGORITHM().optimize(obj, population_size=2)
        self.assertEqual(len(obj.history), 1)

    def test_kernel_cache_has_no_objective_capture(self):
        advance = kernel()
        self.assertIs(advance, kernel())
        self.assertNotIn("objective", str(advance))
        self.assertEqual(MOD._kernels.cache_info().maxsize, 32)

    def test_static_single_class_and_no_direct_problem_calls(self):
        tree = ast.parse((ROOT / "submission.py").read_text())
        subclasses = [n for n in tree.body if isinstance(n, ast.ClassDef)
                      and any(isinstance(b, ast.Name) and b.id == "OptimizationAlgorithm" for b in n.bases)]
        self.assertEqual(len(subclasses), 1)
        forbidden = {"get_value_fn", "get_value_and_grad_fn", "log_evaluation", "value_and_grad", "value"}
        calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                 and n.func.value.id in {"obj", "objective"}]
        self.assertTrue(forbidden.isdisjoint(calls))
        self.assertIn("vmap_value_and_grad", calls)


if __name__ == "__main__":
    unittest.main()
