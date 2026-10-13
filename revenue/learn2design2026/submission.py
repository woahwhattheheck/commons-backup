"""Competition-facing Learn2Design optimizer.

Vectorized multi-trajectory Adam successor to the serial staged-trust baseline.
The Objective owns timing, evaluation accounting and problem-space mapping; this
algorithm uses the documented batched value+gradient path to keep accelerator
hardware busy while retaining independent lane state and deterministic reseeding.
"""
from __future__ import annotations

from dfbench import Objective, OptimizationAlgorithm
import jax
import jax.numpy as jnp


class StagedTrustPortfolio(OptimizationAlgorithm):
    """Batched trust-region Adam portfolio with elite-guided lane recycling."""

    algorithm_str = "tjlabs_vectorized_trust_portfolio_v2"

    def optimize(
        self,
        objective: Objective,
        init_params=None,
        random_seed: int | None = None,
        max_iterations: int | None = None,
        population_size: int = 16,
        learning_rate: float = 0.06,
        beta1: float = 0.90,
        beta2: float = 0.999,
        epsilon: float = 1e-8,
        grad_clip: float = 1.0,
        trust_radius: float = 0.22,
        min_trust_radius: float = 0.008,
        max_trust_radius: float = 0.70,
        noise_start: float = 0.055,
        noise_decay: float = 0.9985,
        reseed_interval: int = 72,
        elite_fraction: float = 0.25,
        **kwargs,
    ) -> None:
        obj = objective
        if type(population_size) is not int or not 4 <= population_size <= 64:
            raise ValueError("population_size must be int in [4,64]")
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
        if type(reseed_interval) is not int or reseed_interval < 8:
            raise ValueError("reseed_interval must be int >= 8")
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

        # Independent manual Adam state lets recycled lanes reset moments without
        # depending on private Optax state layouts.
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
            update = update * step_scale[:, None]
            return params + update, new_m, new_v, new_age

        @jax.jit
        def population_noise(noise_key):
            return jax.random.normal(noise_key, params.shape, dtype=params.dtype)

        # Compile algorithm-owned kernels and the Objective-owned vectorized path
        # before the benchmark clock starts. No result-producing Objective call is
        # made until after start_logging().
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
        reseed_count = max(1, population_size // 4)
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

            trust = jnp.where(improved, jnp.minimum(max_trust_radius, trust * 1.012), trust)
            shrink = (~improved) & (stalls > 0) & ((stalls % 24) == 0)
            trust = jnp.where(shrink, jnp.maximum(min_trust_radius, trust * 0.68), trust)

            # The just-completed batch is valid evidence even if it consumed the
            # remaining wall budget; never spend another update/evaluation after it.
            if obj.budget_exceeded:
                break

            proposal, m, v, age = adam_step(params, m, v, age, grads, trust, valid)
            key, noise_key = jax.random.split(key)
            noise_scale = noise_start * (noise_decay ** iteration)
            proposal = proposal + noise_scale * trust[:, None] * population_noise(noise_key)

            # Periodically recycle the historically weakest quarter around the
            # best historical lanes. Recycled lanes get fresh Adam moments while
            # strong lanes keep their exact best-known anchors for diversity.
            if (iteration + 1) % reseed_interval == 0:
                order = jnp.argsort(lane_best)
                elites = order[:elite_count]
                worst = order[-reseed_count:]
                anchor_indices = elites[jnp.arange(reseed_count) % elite_count]
                anchors = lane_best_params[anchor_indices]
                key, reseed_key = jax.random.split(key)
                perturb = population_noise(reseed_key)[:reseed_count]
                anchor_trust = trust[anchor_indices]
                recycled = anchors + 0.45 * anchor_trust[:, None] * perturb

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
