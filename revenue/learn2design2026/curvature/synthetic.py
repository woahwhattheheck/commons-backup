"""Analytic objective adapter for local tests only; never dfbench provenance."""
from __future__ import annotations

from abc import ABC, abstractmethod
import importlib.util
from pathlib import Path
import sys
import types

import jax
import jax.numpy as jnp
import numpy as np


class SyntheticObjective:
    def __init__(self, loss, dimension=8, budget_batches=80, initial_scale=2.0,
                 dtype=np.float32, injected=None):
        self.loss = loss
        self.dimension = dimension
        self.budget_batches = budget_batches
        self.initial_scale = initial_scale
        self.dtype = dtype
        self.injected = injected
        self.logged = False
        self.history = []
        self.loss_history = []
        self.samples = 0
        self.events = []
        self.rng = np.random.default_rng(0)

    def prepare(self, random_seed):
        if self.logged:
            raise RuntimeError("use a fresh synthetic objective per run")
        self.rng = np.random.default_rng(0 if random_seed is None else random_seed)
        self.events.append("prepare")

    def random_params_unbounded(self, n_samples):
        self.samples += 1
        return jnp.asarray(self.rng.normal(0, self.initial_scale,
                                          (n_samples, self.dimension)), dtype=self.dtype)

    def warmup_vmap_value_and_grad(self, batch_size):
        if self.logged:
            raise RuntimeError("warmup after logging")
        self._evaluate = jax.jit(jax.vmap(jax.value_and_grad(self.loss)))
        arrays = self._evaluate(jnp.zeros((batch_size, self.dimension), dtype=self.dtype))
        jax.tree.map(lambda x: x.block_until_ready(), arrays)
        self.events.append("warmup")

    def start_logging(self):
        if self.logged:
            raise RuntimeError("logging already started")
        self.logged = True
        self.events.append("start_logging")

    @property
    def budget_exceeded(self):
        return len(self.history) >= self.budget_batches

    def vmap_value_and_grad(self, params):
        if not self.logged or self.budget_exceeded:
            raise RuntimeError("evaluation outside logged budget")
        loss, grad = self._evaluate(params)
        if self.injected is not None:
            loss, grad = self.injected(len(self.history), loss, grad)
        loss.block_until_ready()
        grad.block_until_ready()
        self.history.append(np.asarray(params).copy())
        self.loss_history.append(np.asarray(loss).copy())
        self.events.append("evaluate")
        return loss, grad

    @property
    def best_loss(self):
        values = np.concatenate(self.loss_history)
        finite = values[np.isfinite(values)]
        return float(np.min(finite)) if finite.size else None


class _Algorithm(ABC):
    @abstractmethod
    def __init__(self):
        pass

    def prepare(self, objective, unbounded, random_seed=None):
        if unbounded is not True:
            raise ValueError("this adapter only models unbounded coordinates")
        objective.prepare(random_seed)
        return None, jax.random.key(0 if random_seed is None else random_seed)


def load_candidate(path: Path, module_name="_curvature_candidate"):
    """Bind the source to a deliberately fake Objective contract for tests."""
    module = types.ModuleType("dfbench")
    module.Objective, module.OptimizationAlgorithm = SyntheticObjective, _Algorithm
    previous = sys.modules.get("dfbench")
    sys.modules["dfbench"] = module
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load candidate at {path}")
        candidate = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = candidate
        spec.loader.exec_module(candidate)
        return candidate
    finally:
        if previous is None:
            del sys.modules["dfbench"]
        else:
            sys.modules["dfbench"] = previous


def problem(name, dimension, seed=101):
    """Return a fixed analytic function; no organizer problem is represented."""
    rng = np.random.default_rng(seed)
    if name == "sphere":
        target = jnp.asarray(rng.normal(size=dimension))
        return lambda x: jnp.sum((x - target) ** 2)
    if name == "rotated_ellipsoid":
        q, _ = np.linalg.qr(rng.normal(size=(dimension, dimension)))
        q, weights = jnp.asarray(q), jnp.asarray(np.geomspace(1.0, 1e4, dimension))
        target = jnp.asarray(rng.normal(size=dimension))
        return lambda x: jnp.sum(weights * (q @ (x - target)) ** 2) / dimension
    if name == "rosenbrock":
        return lambda x: jnp.sum(100 * (x[1:] - x[:-1] ** 2) ** 2 + (1 - x[:-1]) ** 2)
    if name == "double_well":
        target = jnp.asarray(rng.normal(0, 0.3, size=dimension))
        return lambda x: jnp.sum(((x - target) ** 2 - 1) ** 2 + 0.1 * (x - target))
    raise ValueError(f"unknown analytic problem: {name}")
