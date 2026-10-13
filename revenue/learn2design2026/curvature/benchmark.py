"""Fixed-evaluation analytic comparison; never organizer/competition evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import jax
import numpy as np
from synthetic import SyntheticObjective, load_candidate, problem

ROOT = Path(__file__).resolve().parent
PINS = {
    "submission.py": "fcc16ca4aaa348a1b1fbe42e021dc0dccdf3b2d0",
    "baseline_v2.py": "ac814d1f543529a823f7c3afa2a9c4f54c0bfe12",
}


def identity(path):
    data = path.read_bytes()
    return {"path": path.name, "bytes": len(data),
            "git_blob": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest()}


def verify_sources():
    ids = {name: identity(ROOT / name) for name in PINS}
    for name, blob in PINS.items():
        if ids[name]["git_blob"] != blob:
            raise ValueError(f"frozen source changed: {name}")
    return ids


def constructor_adapter(cls):
    """Only bridge the exact historical no-op constructor contract gap."""
    if not cls.__abstractmethods__:
        return cls
    if cls.__abstractmethods__ != frozenset({"__init__"}):
        raise ValueError("baseline needs more than the documented constructor adapter")
    adapted = type("ConstructorOnlyAdapter", (cls,), {"__init__": lambda self: None})
    if adapted.optimize is not cls.optimize or adapted.algorithm_str != cls.algorithm_str:
        raise ValueError("constructor adapter changed optimizer identity")
    return adapted


def trace_hash(arrays):
    h = hashlib.sha256()
    for a in arrays:
        arr = np.ascontiguousarray(a)
        h.update(str((arr.shape, arr.dtype.str)).encode() + b"\0")
        h.update(arr.tobytes())
    return h.hexdigest()


def run_matrix(seeds, dimensions, eval_budget, names):
    before = verify_sources()
    curvature = load_candidate(ROOT / "submission.py", "_matrix_curvature").BatchedCurvaturePortfolio
    baseline = constructor_adapter(load_candidate(ROOT / "baseline_v2.py", "_matrix_v2").StagedTrustPortfolio)
    arms = [("curvature_b8", curvature, 8), ("v2_b8", baseline, 8), ("v2_default_b16", baseline, 16)]
    entries = []
    dtype = np.float64 if jax.config.x64_enabled else np.float32
    for name in names:
        for dimension in dimensions:
            loss_fn = problem(name, dimension)
            for seed_index, seed in enumerate(seeds):
                # Rotate order; wall times include initialization/JIT and are
                # diagnostics, not a controlled throughput/physics comparison.
                ordered = arms[seed_index % 3:] + arms[:seed_index % 3]
                for arm, cls, width in ordered:
                    obj = SyntheticObjective(loss_fn, dimension, eval_budget // width, dtype=dtype)
                    start = time.perf_counter()
                    failure = None
                    try:
                        cls().optimize(obj, random_seed=seed, population_size=width)
                        if sum(x.shape[0] for x in obj.history) != eval_budget:
                            raise ValueError("wrong evaluation count")
                        if obj.best_loss is None or not np.isfinite(obj.best_loss):
                            raise ValueError("no finite best loss")
                    except Exception as exc:
                        failure = f"{type(exc).__name__}: {exc}"
                    entry = {
                        "problem": name, "dimension": dimension, "seed": seed,
                        "arm": arm, "width": width, "algorithm": cls.algorithm_str,
                        "evals": sum(x.shape[0] for x in obj.history),
                        "batches": len(obj.history), "best_loss": obj.best_loss if obj.history else None,
                        "wall_seconds_including_warmup": time.perf_counter() - start,
                        "parameter_trace_sha256": trace_hash(obj.history),
                        "loss_trace_sha256": trace_hash(obj.loss_history),
                        "best_loss_by_batch": [float(np.min(a[np.isfinite(a)])) if np.isfinite(a).any() else None
                                               for a in obj.loss_history],
                        "failure": failure,
                    }
                    entries.append(entry)
                    print(f"{name}/{dimension}/{seed}/{arm}: {entry['best_loss']} ({failure or 'OK'})",
                          file=sys.stderr, flush=True)
    after = verify_sources()
    if before != after:
        raise ValueError("candidate source changed during execution")
    return {
        "schema": "learn2design-curvature-analytic/v1",
        "evidence_class": "LOCAL_SYNTHETIC_FAKE_DFBENCH_REAL_JAX",
        "official_score_authority": False, "physics_execution_authority": False,
        "source_integrity_is_not_execution_attestation": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "config": {"seeds": seeds, "dimensions": dimensions, "eval_budget": eval_budget,
                   "problems": names, "problem_seed": 101, "initial_scale": 2.0},
        "environment": {"python": platform.python_version(), "jax": jax.__version__,
                        "numpy": np.__version__, "platform": platform.platform(),
                        "backend": jax.default_backend(), "x64_enabled": jax.config.x64_enabled,
                        "devices": [str(d) for d in jax.devices()]},
        "sources_before": before, "sources_after": after,
        "harness": {p: identity(ROOT / p) for p in ("benchmark.py", "synthetic.py")},
        "baseline_constructor_adapter": "no-op __init__ only; optimize/algorithm_str inherited unchanged",
        "status": "FAILED" if any(e["failure"] for e in entries) else "COMPLETE",
        "entries": entries,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--seeds", type=int, nargs="+", default=[7, 42, 73])
    p.add_argument("--dimensions", type=int, nargs="+", default=[8, 32])
    p.add_argument("--eval-budget", type=int, default=1024)
    p.add_argument("--problems", nargs="+", default=["sphere", "rotated_ellipsoid", "rosenbrock", "double_well"])
    args = p.parse_args()
    if args.out.exists():
        p.error("output already exists; use a new path")
    if args.eval_budget < 16 or args.eval_budget % 16:
        p.error("eval budget must be a positive multiple of 16")
    if any(d < 2 or d > 512 for d in args.dimensions):
        p.error("dimensions must be in [2,512]")
    if any(name not in {"sphere", "rotated_ellipsoid", "rosenbrock", "double_well"} for name in args.problems):
        p.error("unknown analytic problem")
    report = run_matrix(args.seeds, args.dimensions, args.eval_budget, args.problems)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as f:
        json.dump(report, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    return 0 if report["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
