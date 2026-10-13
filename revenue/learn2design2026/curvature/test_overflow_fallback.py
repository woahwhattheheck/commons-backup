"""Numerical regressions for the curvature overflow fallback.

These are analytic control-flow tests, not organizer physics or competition evidence.
"""
from pathlib import Path
import unittest

import jax
import jax.numpy as jnp
import numpy as np

from synthetic import load_candidate

MOD = load_candidate(Path(__file__).with_name("submission.py"), "_curvature_overflow_fallback")


def kernel(armijo=1e-4):
    return MOD._kernels(4, 0.5, 4.0, armijo, 0.5, 1e-8, 16, 256, 1e-10)


def state_with(f, g, direction, dtype):
    g = jnp.asarray(g, dtype=dtype)
    direction = jnp.asarray(direction, dtype=dtype)
    x = jnp.zeros_like(g)
    st = MOD._empty(x, 4, 0.5)
    f = jnp.asarray(f, dtype=dtype)
    st = st._replace(
        f=f,
        g=g,
        direction=direction,
        trial=x + direction,
        step=jnp.ones(f.shape, dtype=dtype),
    )
    return st, jnp.full_like(x, 3.0)


class CurvatureOverflowFallbackTests(unittest.TestCase):
    def test_scale_first_underflow_does_not_accept_insufficient_decrease(self):
        dtype = jnp.float32
        n = 200
        f = jnp.full((2,), 1e-32, dtype=dtype)
        g = jnp.full((2, n), 1e-35, dtype=dtype)
        direction = jnp.full((2, n), -0.25, dtype=dtype)
        st, fresh = state_with(f, g, direction, dtype)
        losses = jnp.full((2,), 1e-32 - 1e-38, dtype=dtype)

        slope = jnp.sum(g * direction, axis=1)
        threshold = f + jnp.asarray(1e-4, dtype) * slope
        self.assertTrue(bool(jnp.all(jnp.isfinite(slope))))
        self.assertTrue(bool(jnp.all(jnp.isfinite(threshold))))
        self.assertTrue(bool(jnp.all(losses > threshold)))

        # Regression for the rejected repair: multiplying g first flushes to zero
        # on this JAX CPU path and would incorrectly accept losses <= f.
        scale_first = jnp.sum((jnp.asarray(1e-4, dtype) * g) * direction, axis=1)
        self.assertTrue(bool(jnp.all(scale_first == 0)))

        result, accepted, restarted = kernel()(st, losses, g, fresh)
        self.assertFalse(bool(jnp.any(accepted)))
        self.assertFalse(bool(jnp.any(restarted)))
        np.testing.assert_array_equal(result.x, st.x)
        np.testing.assert_array_equal(result.g, st.g)

    def test_overflow_fallback_accepts_sufficient_improvement(self):
        dtype = jnp.float32
        n = 64
        f = jnp.full((2,), 1e38, dtype=dtype)
        g = jnp.full((2, n), 1e38, dtype=dtype)
        direction = jnp.full((2, n), -0.0625, dtype=dtype)
        st, fresh = state_with(f, g, direction, dtype)
        losses = f * jnp.asarray(0.99, dtype)

        self.assertTrue(bool(jnp.all(jnp.isneginf(jnp.sum(g * direction, axis=1)))))
        result, accepted, restarted = kernel()(st, losses, g, fresh)
        self.assertTrue(bool(jnp.all(accepted)))
        self.assertFalse(bool(jnp.any(restarted)))
        np.testing.assert_array_equal(result.x, st.trial)

    def test_overflow_fallback_rejects_insufficient_improvement(self):
        dtype = jnp.float32
        n = 64
        f = jnp.full((2,), 1e38, dtype=dtype)
        g = jnp.full((2, n), 1e38, dtype=dtype)
        direction = jnp.full((2, n), -0.0625, dtype=dtype)
        st, fresh = state_with(f, g, direction, dtype)
        # Scaled Armijo threshold is 1 - 0.0004 = 0.9996 of f.
        losses = f * jnp.asarray(0.9999, dtype)

        result, accepted, restarted = kernel()(st, losses, g, fresh)
        self.assertFalse(bool(jnp.any(accepted)))
        self.assertFalse(bool(jnp.any(restarted)))
        np.testing.assert_array_equal(result.x, st.x)

    def test_finite_original_path_matches_predecessor_decision(self):
        dtype = jnp.float32
        rng = np.random.default_rng(20260918)
        g = jnp.asarray(rng.normal(size=(8, 17)), dtype=dtype)
        direction = jnp.asarray(rng.normal(size=(8, 17)) * 0.02, dtype=dtype)
        f = jnp.asarray(np.linspace(1.0, 2.0, 8), dtype=dtype)
        st, fresh = state_with(f, g, direction, dtype)
        slope = jnp.sum(g * direction, axis=1)
        threshold = f + jnp.asarray(1e-4, dtype) * slope
        losses = threshold + jnp.asarray(
            [-1e-5, 1e-5, -2e-5, 2e-5, -3e-5, 3e-5, -4e-5, 4e-5],
            dtype=dtype,
        )
        expected = losses <= threshold
        self.assertTrue(bool(jnp.all(jnp.isfinite(slope))))
        self.assertTrue(bool(jnp.all(jnp.isfinite(threshold))))

        _, accepted, _ = kernel()(st, losses, g, fresh)
        np.testing.assert_array_equal(accepted, expected)

    @unittest.skipUnless(jax.config.x64_enabled, "requires JAX_ENABLE_X64=true")
    def test_float64_overflow_fallback(self):
        dtype = jnp.float64
        n = 64
        f = jnp.full((2,), 6e307, dtype=dtype)
        g = jnp.full((2, n), 6e307, dtype=dtype)
        direction = jnp.full((2, n), -0.0625, dtype=dtype)
        st, fresh = state_with(f, g, direction, dtype)
        losses = f * jnp.asarray(0.99, dtype)

        self.assertTrue(bool(jnp.all(jnp.isneginf(jnp.sum(g * direction, axis=1)))))
        result, accepted, restarted = kernel()(st, losses, g, fresh)
        self.assertTrue(bool(jnp.all(accepted)))
        self.assertFalse(bool(jnp.any(restarted)))
        np.testing.assert_array_equal(result.x, st.trial)


if __name__ == "__main__":
    unittest.main()
