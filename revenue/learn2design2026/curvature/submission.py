"""An optional Learn2Design batched L-BFGS candidate, not the promoted entry.

Each lane runs its own Armijo line search. Rejected trials do not alter the
accepted point or curvature history; other lanes can advance in the same batch.
Only the supplied Objective evaluates the problem or owns the benchmark clock.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import NamedTuple

from dfbench import Objective, OptimizationAlgorithm
import jax
import jax.numpy as jnp


class _State(NamedTuple):
    x: jax.Array
    f: jax.Array
    g: jax.Array
    s: jax.Array
    y: jax.Array
    rho: jax.Array
    head: jax.Array
    count: jax.Array
    direction: jax.Array
    step: jax.Array
    trial: jax.Array
    backtracks: jax.Array
    age: jax.Array
    radius: jax.Array


def _empty(params, memory_size, radius):
    n, d = params.shape
    zeros = jnp.zeros_like(params)
    ints = jnp.zeros(n, dtype=jnp.int32)
    history = jnp.zeros((n, memory_size, d), dtype=params.dtype)
    return _State(params, jnp.full(n, jnp.inf, dtype=params.dtype), zeros,
                  history, history, jnp.zeros((n, memory_size), dtype=params.dtype),
                  ints, ints, zeros, jnp.ones(n, dtype=params.dtype), params,
                  ints, ints, jnp.full(n, radius, dtype=params.dtype))


def _cap(direction, radius):
    """Euclidean cap without squaring large unscaled coordinates."""
    scale = jnp.max(jnp.abs(direction), axis=1)
    tiny = jnp.finfo(direction.dtype).tiny
    unit = direction / jnp.maximum(scale, tiny)[:, None]
    norm = jnp.sqrt(jnp.sum(unit * unit, axis=1))
    size = jnp.minimum(scale, radius / jnp.maximum(norm, tiny))
    return unit * size[:, None]


@lru_cache(maxsize=32)
def _kernels(memory_size, initial_radius, max_radius, armijo, shrink,
             min_step, max_backtracks, restart_after, gradient_tolerance):
    """Return the pure transition kernel; no objective callable is captured."""
    def direction(g, s, y, rho, head, count, radius):
        rows = jnp.arange(g.shape[0])
        alphas = jnp.zeros((g.shape[0], memory_size), dtype=g.dtype)

        def reverse(i, carry):
            q, aa = carry
            slot = (head - 1 - i) % memory_size
            ss, yy, rr = s[rows, slot], y[rows, slot], rho[rows, slot]
            a = jnp.where(i < count, rr * jnp.sum(ss * q, axis=1), 0.0)
            return q - a[:, None] * yy, aa.at[:, i].set(a)

        q, alphas = jax.lax.fori_loop(0, memory_size, reverse, (g, alphas))
        latest = (head - 1) % memory_size
        ss, yy = s[rows, latest], y[rows, latest]
        sy, yy2 = jnp.sum(ss * yy, axis=1), jnp.sum(yy * yy, axis=1)
        gamma = jnp.where(count > 0, sy / jnp.maximum(yy2, jnp.finfo(g.dtype).tiny), 1.0)
        gamma = jnp.clip(gamma, 1e-8, 1e8)

        def forward(k, r):
            i = memory_size - 1 - k
            slot = (head - 1 - i) % memory_size
            ss, yy, rr = s[rows, slot], y[rows, slot], rho[rows, slot]
            b = rr * jnp.sum(yy * r, axis=1)
            coefficient = jnp.where(i < count, alphas[:, i] - b, 0.0)
            return r + coefficient[:, None] * ss

        raw = -jax.lax.fori_loop(0, memory_size, forward, gamma[:, None] * q)
        finite = jnp.all(jnp.isfinite(raw), axis=1)
        bounded = _cap(jnp.where(finite[:, None], raw, -g), radius)
        slope = jnp.sum(g * bounded, axis=1)
        # Preserve the established finite path. Only when the reduction
        # overflows do we normalize the finite gradient before checking sign.
        g_scale = jnp.maximum(jnp.max(jnp.abs(g), axis=1), jnp.finfo(g.dtype).tiny)
        normalized_slope = jnp.sum((g / g_scale[:, None]) * bounded, axis=1)
        descent = jnp.where(
            jnp.isfinite(slope),
            slope < 0,
            jnp.isfinite(normalized_slope) & (normalized_slope < 0),
        )
        return jnp.where(descent[:, None], bounded, _cap(-g, radius))

    @jax.jit
    def advance(st, losses, grads, fresh):
        rows = jnp.arange(st.x.shape[0])
        valid = (jnp.isfinite(losses) & jnp.all(jnp.isfinite(grads), axis=1)
                 & jnp.all(jnp.isfinite(st.trial), axis=1))
        no_base = ~jnp.isfinite(st.f)
        slope = jnp.sum(st.g * st.direction, axis=1)
        threshold = st.f + armijo * st.step * slope

        # The ordinary path retains its exact prior arithmetic whenever both
        # the directional derivative and threshold are representable. If that
        # reduction overflows, compare the same inequality after dividing all
        # terms by one positive scale. This avoids both overflow and the
        # small-gradient underflow caused by multiplying g by Armijo first.
        scale = jnp.maximum(
            jnp.maximum(jnp.abs(st.f), jnp.abs(losses)),
            jnp.max(jnp.abs(st.g), axis=1),
        )
        scale = jnp.maximum(scale, jnp.finfo(st.g.dtype).tiny)
        scaled_slope = jnp.sum((st.g / scale[:, None]) * st.direction, axis=1)
        scaled_accept = (
            losses / scale
            <= st.f / scale + armijo * st.step * scaled_slope
        )
        ordinary = jnp.isfinite(slope) & jnp.isfinite(threshold)
        armijo_accept = jnp.where(ordinary, losses <= threshold, scaled_accept)
        accepted = valid & (no_base | armijo_accept)
        safe_g = jnp.where(valid[:, None], grads, 0.0)
        ds = st.trial - st.x
        dy = safe_g - st.g
        sy = jnp.sum(ds * dy, axis=1)
        ss = jnp.sum(ds * ds, axis=1)
        yy = jnp.sum(dy * dy, axis=1)
        # A rejected point, a fresh restart, or nonpositive/ill-scaled curvature
        # must not enter the inverse-Hessian history.
        threshold = 1e-8 * jnp.sqrt(ss) * jnp.sqrt(yy)
        reciprocal = 1.0 / jnp.where(sy > 0.0, sy, 1.0)
        pair = (accepted & ~no_base & (ss > 0) & (sy > threshold)
                & jnp.isfinite(sy) & jnp.isfinite(ss) & jnp.isfinite(yy)
                & jnp.isfinite(reciprocal))
        old_s, old_y, old_rho = st.s[rows, st.head], st.y[rows, st.head], st.rho[rows, st.head]
        s = st.s.at[rows, st.head].set(jnp.where(pair[:, None], ds, old_s))
        y = st.y.at[rows, st.head].set(jnp.where(pair[:, None], dy, old_y))
        rho = st.rho.at[rows, st.head].set(jnp.where(pair, reciprocal, old_rho))
        head = jnp.where(pair, (st.head + 1) % memory_size, st.head)
        count = jnp.minimum(st.count + pair.astype(jnp.int32), memory_size)
        x = jnp.where(accepted[:, None], st.trial, st.x)
        f = jnp.where(accepted, losses, st.f)
        g = jnp.where(accepted[:, None], safe_g, st.g)
        age = st.age + 1
        radius = jnp.where(accepted & (st.backtracks == 0),
                           jnp.minimum(max_radius, st.radius * 1.25), st.radius)
        new_direction = direction(g, s, y, rho, head, count, radius)
        d = jnp.where(accepted[:, None], new_direction, st.direction)
        step = jnp.where(accepted, 1.0, st.step * shrink)
        backtracks = jnp.where(accepted, 0, st.backtracks + 1)
        trial = x + step[:, None] * d
        stationary = jnp.max(jnp.abs(g), axis=1) <= gradient_tolerance
        restart = ((no_base & ~valid) | (backtracks >= max_backtracks)
                   | (step < min_step) | (age >= restart_after)
                   | (accepted & stationary)
                   | ~jnp.all(jnp.isfinite(trial), axis=1))
        # Every lane reset clears all curvature, search, and accepted-point state.
        # The Objective, not this state, owns the logged result history.
        blank = _empty(fresh, memory_size, initial_radius)
        updated = _State(x, f, g, s, y, rho, head, count, d, step, trial,
                         backtracks, age, radius)
        def select(a, b):
            mask = restart.reshape((restart.shape[0],) + (1,) * (a.ndim - 1))
            return jnp.where(mask, b, a)
        return jax.tree.map(select, updated, blank), accepted, restart

    return advance


class BatchedCurvaturePortfolio(OptimizationAlgorithm):
    """Safeguarded asynchronous L-BFGS in Objective's unbounded coordinates."""
    algorithm_str = "tjlabs_async_curvature_portfolio_cairn1"

    def __init__(self):
        # dfbench 0.3.3 declares the constructor abstract.
        pass

    def optimize(self, objective: Objective, init_params=None, random_seed=None,
                 max_iterations=None, population_size=8, memory_size=8,
                 initial_radius=0.5, max_radius=4.0, armijo=1e-4, shrink=0.5,
                 min_step=1e-8, max_backtracks=16, restart_after=256,
                 gradient_tolerance=1e-10, **kwargs) -> None:
        for name, value, lower, upper in (
            ("population_size", population_size, 2, 64),
            ("memory_size", memory_size, 1, 32),
            ("max_backtracks", max_backtracks, 1, 64),
            ("restart_after", restart_after, 2, 1000000),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name} must be an int in [{lower}, {upper}]")
        if max_iterations is not None and (type(max_iterations) is not int or max_iterations < 1):
            raise ValueError("max_iterations must be a positive integer or None")
        for name, value in (("initial_radius", initial_radius), ("max_radius", max_radius),
                            ("armijo", armijo), ("shrink", shrink), ("min_step", min_step),
                            ("gradient_tolerance", gradient_tolerance)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite real number")
        if not (0 < initial_radius <= max_radius <= 100):
            raise ValueError("require 0 < initial_radius <= max_radius <= 100")
        if not (0 < armijo < 0.5 and 0 < shrink < 1 and 0 < min_step < 1):
            raise ValueError("invalid line-search constants")
        if gradient_tolerance < 0:
            raise ValueError("gradient_tolerance must be nonnegative")

        obj = objective
        self.prepare(obj, unbounded=True, random_seed=random_seed)
        params = jnp.asarray(obj.random_params_unbounded(n_samples=population_size))
        if params.ndim != 2 or params.shape[0] != population_size or params.shape[1] < 1:
            raise ValueError("Objective returned an unexpected batched parameter shape")
        if not jnp.issubdtype(params.dtype, jnp.floating):
            raise ValueError("Objective parameters must use a floating dtype")
        if init_params is not None:
            init = jnp.asarray(init_params, dtype=params.dtype)
            if init.shape != params.shape[1:]:
                raise ValueError("init_params has the wrong dimension")
            params = params.at[0].set(init)
        if not bool(jnp.all(jnp.isfinite(params))):
            raise ValueError("initial parameters must be finite")

        def sample():
            result = jnp.asarray(obj.random_params_unbounded(n_samples=population_size), dtype=params.dtype)
            if result.shape != params.shape or not bool(jnp.all(jnp.isfinite(result))):
                raise ValueError("Objective returned invalid restart samples")
            return result

        fresh = sample()
        st = _empty(params, memory_size, initial_radius)
        advance = _kernels(memory_size, initial_radius, max_radius, armijo, shrink,
                           min_step, max_backtracks, restart_after, gradient_tolerance)
        # Compile and synchronize our own kernel before the clock. This is an
        # array-only dry run, never a result-producing Objective evaluation.
        warm = advance(st, jnp.ones(population_size, dtype=params.dtype),
                       jnp.ones_like(params), fresh)
        jax.tree.map(lambda a: a.block_until_ready(), warm)
        obj.warmup_vmap_value_and_grad(batch_size=population_size)
        obj.start_logging()
        batches = 0
        while not obj.budget_exceeded:
            if max_iterations is not None and batches >= max_iterations:
                break
            losses, grads = obj.vmap_value_and_grad(st.trial)
            losses, grads = jnp.asarray(losses), jnp.asarray(grads)
            if losses.shape != (population_size,) or grads.shape != params.shape:
                raise ValueError("Objective returned unexpected value/gradient shapes")
            batches += 1
            # The final admitted batch is logged by Objective. Never evaluate or
            # propose again after it has consumed the remaining budget.
            if obj.budget_exceeded or (max_iterations is not None and batches >= max_iterations):
                break
            st, _, restarted = advance(st, losses, grads, fresh)
            if bool(jnp.any(restarted)):
                fresh = sample()
