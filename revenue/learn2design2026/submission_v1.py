"""Competition-facing Learn2Design optimizer.

The implementation intentionally stays compact: a deterministic portfolio of noisy
Adam restarts in Objective's smooth unbounded space, with bounded trust-region
steps and restart scheduling. It never calls a result-producing Objective method
before start_logging().
"""
from __future__ import annotations

from dfbench import Objective, OptimizationAlgorithm
import jax
import jax.numpy as jnp
import optax


class StagedTrustPortfolio(OptimizationAlgorithm):
    algorithm_str = "tjlabs_staged_trust_portfolio_v1"

    def optimize(
        self,
        objective: Objective,
        init_params=None,
        random_seed: int | None = None,
        learning_rate: float = 0.08,
        restarts: int = 5,
        restart_patience: int = 220,
        trust_radius: float = 0.30,
        min_trust_radius: float = 0.01,
        max_trust_radius: float = 0.80,
        noise_start: float = 0.10,
        noise_decay: float = 0.997,
        **kwargs,
    ) -> None:
        obj = objective
        if type(restarts) is not int or not 1 <= restarts <= 16:
            raise ValueError("restarts must be int in [1,16]")
        if type(restart_patience) is not int or restart_patience < 20:
            raise ValueError("restart_patience must be int >=20")
        if not (0.0 < learning_rate <= 1.0):
            raise ValueError("learning_rate must be in (0,1]")
        if not (0 < min_trust_radius <= trust_radius <= max_trust_radius <= 2.0):
            raise ValueError("invalid trust radii")
        if not (0.0 <= noise_start <= 1.0 and 0.9 <= noise_decay <= 1.0):
            raise ValueError("invalid noise schedule")

        _, key = self.prepare(obj, unbounded=True, random_seed=random_seed)
        if random_seed is None:
            random_seed = 0

        starts = []
        if init_params is not None:
            starts.append(jnp.asarray(init_params))
        while len(starts) < restarts:
            starts.append(jnp.asarray(obj.random_params_unbounded()))

        obj.warmup_value_and_grad()
        obj.start_logging()

        best_params = starts[0]
        best_loss = jnp.asarray(jnp.inf)
        trust = float(trust_radius)
        global_iteration = 0

        for restart_index, start in enumerate(starts):
            if obj.budget_exceeded:
                break
            params = start
            optimizer = optax.chain(
                optax.clip_by_global_norm(1.0),
                optax.adam(learning_rate),
            )
            state = optimizer.init(params)
            local_best = jnp.asarray(jnp.inf)
            no_improve = 0
            local_trust = trust

            while not obj.budget_exceeded and no_improve < restart_patience:
                loss, grad = obj.value_and_grad(params)
                finite = bool(jnp.isfinite(loss)) and bool(jnp.all(jnp.isfinite(grad)))
                if not finite:
                    no_improve = restart_patience
                    continue

                loss_scalar = float(loss)
                if loss_scalar < float(local_best):
                    local_best = loss
                    no_improve = 0
                    local_trust = min(max_trust_radius, local_trust * 1.015)
                else:
                    no_improve += 1
                    if no_improve % 25 == 0:
                        local_trust = max(min_trust_radius, local_trust * 0.70)

                if loss_scalar < float(best_loss):
                    best_loss = loss
                    best_params = params

                updates, state = optimizer.update(grad, state, params)
                step = updates
                step_norm = jnp.linalg.norm(step)
                scale = jnp.minimum(1.0, local_trust / (step_norm + 1e-12))
                step = step * scale

                key, noise_key = jax.random.split(key)
                noise_scale = noise_start * (noise_decay ** global_iteration)
                noise = jax.random.normal(noise_key, params.shape, dtype=params.dtype)
                proposal = params + step + noise_scale * local_trust * noise

                if restart_index > 0 and no_improve > restart_patience // 2:
                    proposal = 0.75 * proposal + 0.25 * best_params

                params = proposal
                global_iteration += 1

            trust = max(min_trust_radius, min(max_trust_radius, local_trust))
