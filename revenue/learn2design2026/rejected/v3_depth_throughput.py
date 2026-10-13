"""Learn2Design depth/throughput hybrid optimizer candidate.

This v3 keeps the organizer-supported vectorized Objective path from v2, but
uses a smaller portfolio and much earlier historical-best snapback/recycling so
short public-development cells obtain materially more optimizer generations.
The Objective remains authoritative for timing and evaluation accounting.
"""
from __future__ import annotations

from dfbench import Objective, OptimizationAlgorithm
import jax
import jax.numpy as jnp


class StagedTrustPortfolio(OptimizationAlgorithm):
    """Depth-biased batched Adam portfolio with early elite rehabilitation."""

    algorithm_str = "tjlabs_depth_throughput_portfolio_v3"

    def optimize(
        self,
        objective: Objective,
        init_params=None,
        random_seed: int | None = None,
        max_iterations: int | None = None,
        population_size: int = 8,
        learning_rate: float = 0.07,
        beta1: float = 0.90,
        beta2: float = 0.999,
        epsilon: float = 1e-8,
        grad_clip: float = 1.0,
        trust_radius: float = 0.26,
        min_trust_radius: float = 0.01,
        max_trust_radius: float = 0.75,
        noise_start: float = 0.065,
        noise_decay: float = 0.998,
        snapback_patience: int = 7,
        recycle_interval: int = 12,
        elite_fraction: float = 0.25,
        **kwargs,
    ) -> None:
        obj = objective
        if type(population_size) is not int or not 4 <= population_size <= 32:
            raise ValueError("population_size must be int in [4,32]")
        if max_iterations is not None and (type(max_iterations) is not int or max_iterations <= 0):
            raise ValueError("max_iterations must be a positive int or None")
        if not (0.0 < learning_rate <= 1.0):
            raise ValueError("learning_rate must be in (0,1]")
        if not (0.0 < beta1 < 1.0 and 0.0 < beta2 < 1.0):
            raise ValueError("Adam betas must be in (0,1)")
        if not (epsilon > 0.0 and grad_clip > 0.0):
            raise ValueError("epsilon and grad_clip must be positive")
        if not (0.0 < min_trust_radius <= trust_radius <= max_trust_radius <= 2.0):
            raise ValueError("invalid trust radii")
        if not (0.0 <= noise_start <= 1.0 and 0.90 <= noise_decay <= 1.0):
            raise ValueError("invalid noise schedule")
        if type(snapback_patience) is not int or snapback_patience < 3:
            raise ValueError("snapback_patience must be int >= 3")
        if type(recycle_interval) is not int or recycle_interval < 6:
            raise ValueError("recycle_interval must be int >= 6")
        if not (0.0 < elite_fraction <= 0.5):
            raise ValueError("elite_fraction must be in (0,0.5]")

        _, key = self.prepare(obj, unbounded=True, random_seed=random_seed)

        params = jnp.asarray(obj.random_params_unbounded(n_samples=population_size))
        if params.ndim != 2 or params.shape[0] != population_size:
            raise ValueError("Objective returned an unexpected batched parameter shape")
        if init_params is not None:
            init = jnp.asarray(init_params, dtype=params.dtype)
            if init.shape != params.shape[1:]:
                raise ValueError("init_params shape does not match Objective dimension")
            params = params.at[0].set(init)

        m = jnp.zeros_like(params)
        v = jnp.zeros_like(params)
        age = jnp.zeros((population_size,), dtype=jnp.int32)
        trust = jnp.full((population_size,), trust_radius, dtype=params.dtype)

        @jax.jit
        def adam_step(params, m, v, age, grads, trust, valid_rows):
            safe_grads = jnp.where(valid_rows[:, None], grads, 0.0)
            grad_norm = jnp.linalg.norm(safe_grads, axis=1)
            grad_scale = jnp.minimum(1.0, grad_clip / (grad_norm + epsilon))
            safe_grads = safe_grads * grad_scale[:, None]

            new_age = age + 1
            new_m = beta1 * m + (1.0 - beta1) * safe_grads
            new_v = beta2 * v + (1.0 - beta2) * jnp.square(safe_grads)
            b1 = 1.0 - jnp.power(beta1, new_age.astype(params.dtype))
            b2 = 1.0 - jnp.power(beta2, new_age.astype(params.dtype))
            m_hat = new_m / b1[:, None]
            v_hat = new_v / b2[:, None]
            update = -learning_rate * m_hat / (jnp.sqrt(v_hat) + epsilon)

            step_norm = jnp.linalg.norm(update, axis=1)
            step_scale = jnp.minimum(1.0, trust / (step_norm + epsilon))
            return params + update * step_scale[:, None], new_m, new_v, new_age

        @jax.jit
        def population_noise(noise_key):
            return jax.random.normal(noise_key, params.shape, dtype=params.dtype)

        valid0 = jnp.ones((population_size,), dtype=bool)
        _ = adam_step(params, m, v, age, jnp.zeros_like(params), trust, valid0)
        key, warm_noise_key = jax.random.split(key)
        _ = population_noise(warm_noise_key)
        obj.warmup_vmap_value_and_grad(batch_size=population_size)
        obj.start_logging()

        lane_best = jnp.full((population_size,), jnp.inf, dtype=params.dtype)
        lane_best_params = params
        stalls = jnp.zeros((population_size,), dtype=jnp.int32)
        elite_count = max(1, int(population_size * elite_fraction))
        recycle_count = max(1, population_size // 4)
        iteration = 0

        while not obj.budget_exceeded:
            if max_iterations is not None and iteration >= max_iterations:
                break

            losses, grads = obj.vmap_value_and_grad(params)
            valid = jnp.isfinite(losses) & jnp.all(jnp.isfinite(grads), axis=1)
            safe_losses = jnp.where(valid, losses, jnp.inf)

            improved = safe_losses < lane_best
            lane_best = jnp.where(improved, safe_losses, lane_best)
            lane_best_params = jnp.where(improved[:, None], params, lane_best_params)
            stalls = jnp.where(improved, 0, stalls + 1)

            trust = jnp.where(improved, jnp.minimum(max_trust_radius, trust * 1.015), trust)
            shrink = (~improved) & (stalls > 0) & ((stalls % snapback_patience) == 0)
            trust = jnp.where(shrink, jnp.maximum(min_trust_radius, trust * 0.72), trust)

            if obj.budget_exceeded:
                break

            proposal, m, v, age = adam_step(params, m, v, age, grads, trust, valid)
            key, noise_key = jax.random.split(key)
            noise_scale = noise_start * (noise_decay ** iteration)
            proposal = proposal + noise_scale * trust[:, None] * population_noise(noise_key)

            # Recover stalled lanes around their own historical best early enough
            # to matter in short public-development cells. Preserve the historical
            # score, but reset Adam moments so a stale trajectory is not sticky.
            snapback = (stalls >= snapback_patience) & jnp.isfinite(lane_best)
            key, snap_key = jax.random.split(key)
            snap_noise = population_noise(snap_key)
            snap_target = lane_best_params + 0.20 * trust[:, None] * snap_noise
            proposal = jnp.where(snapback[:, None], snap_target, proposal)
            m = jnp.where(snapback[:, None], 0.0, m)
            v = jnp.where(snapback[:, None], 0.0, v)
            age = jnp.where(snapback, 0, age)
            stalls = jnp.where(snapback, 0, stalls)

            # Recycle the historically weakest quarter every few generations,
            # not after dozens of batches. Elite lanes keep their accumulated
            # history; recycled lanes start near an elite with fresh moments.
            if (iteration + 1) % recycle_interval == 0:
                order = jnp.argsort(lane_best)
                elites = order[:elite_count]
                worst = order[-recycle_count:]
                anchor_indices = elites[jnp.arange(recycle_count) % elite_count]
                anchors = lane_best_params[anchor_indices]
                key, recycle_key = jax.random.split(key)
                perturb = population_noise(recycle_key)[:recycle_count]
                recycled = anchors + 0.32 * trust[anchor_indices, None] * perturb

                proposal = proposal.at[worst].set(recycled)
                m = m.at[worst].set(0.0)
                v = v.at[worst].set(0.0)
                age = age.at[worst].set(0)
                stalls = stalls.at[worst].set(0)
                lane_best = lane_best.at[worst].set(jnp.inf)
                lane_best_params = lane_best_params.at[worst].set(recycled)
                trust = trust.at[worst].set(trust_radius)

            params = proposal
            iteration += 1
