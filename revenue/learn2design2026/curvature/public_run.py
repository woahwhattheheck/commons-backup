"""Run a frozen candidate on real dfbench public ConstrainedVoyager.

This program reports observations; hashes provide content integrity, not trusted
execution attestation. It does not authorize promotion, submission, or a prize.
The CLI never imports the synthetic adapter used by the analytic test suite.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
ORGANIZER_REVISION = "84a4b0a4c7e0f3b702459ffc8ba6a1d84d34cefa"
ORGANIZER_PROJECT_BLOB = "50f509ac6cfd4e1f4843337410d1fb76d36720c4"
CANDIDATES = {
    "curvature_b8": ("submission.py", "BatchedCurvaturePortfolio", 8,
                     "fcc16ca4aaa348a1b1fbe42e021dc0dccdf3b2d0"),
    "v2_b8": ("baseline_v2.py", "StagedTrustPortfolio", 8,
              "ac814d1f543529a823f7c3afa2a9c4f54c0bfe12"),
    "v2_default_b16": ("baseline_v2.py", "StagedTrustPortfolio", 16,
                       "ac814d1f543529a823f7c3afa2a9c4f54c0bfe12"),
}


def identity(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()}


def organizer_identity(path):
    revision = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    if revision != ORGANIZER_REVISION:
        raise ValueError("organizer checkout is not the frozen revision")
    project = identity(path / "pyproject.toml")
    if project["git_blob"] != ORGANIZER_PROJECT_BLOB:
        raise ValueError("organizer pyproject differs from the frozen Git blob")
    return {"revision": revision, "pyproject": project}


def feasible_statistics(loss_history, sensitivity_history, feasible_history, width, eval_count):
    """Validate full batched histories before making any feasibility statement."""
    import numpy as np
    if not (len(loss_history) == len(sensitivity_history) == len(feasible_history)):
        raise ValueError("aux histories are absent or not aligned with losses")
    if len(loss_history) == 0:
        raise ValueError("no result-producing evaluation history")
    losses, sensitivities, feasible = [], [], []
    for raw, sensitivity, flag in zip(loss_history, sensitivity_history, feasible_history):
        a, b, c = np.asarray(raw), np.asarray(sensitivity), np.asarray(flag)
        if a.shape != (width,) or b.shape != (width,) or c.shape != (width,):
            raise ValueError("expected full batch histories; reduced best-only histories are insufficient")
        if c.dtype.kind != "b":
            raise ValueError("feasibility must contain booleans, not missing or coerced values")
        losses.append(a)
        sensitivities.append(b)
        feasible.append(c)
    raw, sensitivity, flag = map(np.concatenate, (losses, sensitivities, feasible))
    if raw.size != eval_count:
        raise ValueError("history size does not match Objective eval_count")
    finite = np.isfinite(raw) & np.isfinite(sensitivity)
    valid_feasible = flag & finite
    return {
        "evaluations_with_finite_loss_and_sensitivity": int(finite.sum()),
        "feasible_finite_evaluations": int(valid_feasible.sum()),
        "best_raw_objective_loss": float(raw[np.isfinite(raw)].min()) if np.isfinite(raw).any() else None,
        "best_feasible_objective_loss": float(raw[valid_feasible].min()) if valid_feasible.any() else None,
        "best_feasible_sensitivity_loss": float(sensitivity[valid_feasible].min()) if valid_feasible.any() else None,
        "has_feasible_point": bool(valid_feasible.any()),
        "official_score": None,
    }


def json_arrays(history):
    """Preserve every batch; represent nonfinite numbers as explicit JSON null."""
    import numpy as np
    result = []
    for batch in history:
        a = np.asarray(batch)
        if a.dtype.kind == "b":
            result.append(a.tolist())
        else:
            result.append([float(v) if math.isfinite(float(v)) else None for v in a.reshape(-1)])
    return result


def run(arm, seed, seconds, organizer):
    # Actual installed packages only. No test adapter or monkeypatch is used.
    import dfbench
    import jax
    import numpy as np
    from dfbench.problems import ConstrainedVoyagerProblem
    if importlib.metadata.version("dfbench") != "0.3.3":
        raise ValueError("this public run requires dfbench==0.3.3")
    if not (3, 11) <= sys.version_info[:2] < (3, 14):
        raise ValueError("organizer requires Python >=3.11,<3.14")
    organizer_before = organizer_identity(organizer)
    filename, class_name, width, blob = CANDIDATES[arm]
    source = ROOT / filename
    before = identity(source)
    if before["git_blob"] != blob:
        raise ValueError("candidate source does not match the frozen Git blob")
    spec = importlib.util.spec_from_file_location("_public_candidate", source)
    if spec is None or spec.loader is None:
        raise ValueError("cannot import the frozen source")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    cls = getattr(mod, class_name)
    if not issubclass(cls, dfbench.OptimizationAlgorithm):
        raise ValueError("candidate is not a real dfbench OptimizationAlgorithm")
    adapter = None
    if cls.__abstractmethods__:
        if arm == "curvature_b8" or cls.__abstractmethods__ != frozenset({"__init__"}):
            raise ValueError("unexpected abstract-method contract gap")
        original = cls
        cls = type("HistoricalNoOpConstructor", (cls,), {"__init__": lambda self: None})
        if cls.optimize is not original.optimize or cls.algorithm_str != original.algorithm_str:
            raise ValueError("historical constructor adapter changed optimizer semantics")
        adapter = "no-op __init__ only; frozen optimize and algorithm_str inherited unchanged"
    problem = ConstrainedVoyagerProblem()
    save = ["batched_loss", "batched_sensitivity_loss", "batched_is_feasible"]
    objective = dfbench.Objective(problem, max_time=seconds, save=save,
                                 save_params_history=False, verbose=0)
    start = time.perf_counter()
    cls().optimize(objective, random_seed=seed, population_size=width)
    elapsed = time.perf_counter() - start
    after = identity(source)
    organizer_after = organizer_identity(organizer)
    if before != after or organizer_before != organizer_after:
        raise ValueError("candidate or organizer identity changed during run")
    losses = objective.loss_history
    sensitivity = objective.sensitivity_loss_history
    feasibility = objective.is_feasible_history
    metrics = feasible_statistics(losses, sensitivity, feasibility, width, int(objective.eval_count))
    if not objective.budget_exceeded:
        raise ValueError("candidate returned before the configured Objective budget was exhausted")
    return {
        "schema": "learn2design-curvature-public-observation/v1",
        "evidence_class": "SELF_REPORTED_PUBLIC_CONSTRAINED_VOYAGER_EXECUTION",
        "authority": {"execution_attestation": False, "hidden_topology": False,
                      "H100_parity": False, "official_score": False,
                      "promotion": False, "prize": False, "payment": False},
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "cell": {"arm": arm, "problem": "ConstrainedVoyagerProblem", "seed": seed,
                 "max_time_seconds": seconds, "width": width, "save": save},
        "algorithm": cls.algorithm_str, "constructor_adapter": adapter,
        "candidate_before": before, "candidate_after": after,
        "organizer_before": organizer_before, "organizer_after": organizer_after,
        "runner_source": identity(Path(__file__)),
        "packages": {name: importlib.metadata.version(name) for name in ("dfbench", "differometor", "jax", "jaxlib", "numpy")},
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "cpu_count": os.cpu_count(), "jax_backend": jax.default_backend(),
                        "jax_x64_enabled": jax.config.x64_enabled,
                        "devices": [str(d) for d in jax.devices()]},
        "provider_context_self_reported": {name: os.environ.get(name) for name in
                    ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "RUNNER_OS", "RUNNER_ARCH")},
        "eval_count": int(objective.eval_count), "budget_exceeded": bool(objective.budget_exceeded),
        "objective_seconds": float(objective.time_elapsed), "wall_seconds_with_warmup": elapsed,
        "metrics": metrics,
        "raw": {"loss_history": json_arrays(losses), "sensitivity_loss_history": json_arrays(sensitivity),
                "is_feasible_history": json_arrays(feasibility)},
        "status": "COMPLETE_WITH_FEASIBLE_POINT" if metrics["has_feasible_point"] else "COMPLETE_NO_FEASIBLE_POINT",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arm", choices=tuple(CANDIDATES), required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--seconds", type=float, default=30.0)
    p.add_argument("--organizer", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if not math.isfinite(args.seconds) or not 1 <= args.seconds <= 120:
        p.error("public-development budget must be between 1 and 120 seconds")
    if args.out.exists():
        p.error("output already exists; use a fresh run path")
    report = run(args.arm, args.seed, args.seconds, args.organizer)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as f:
        json.dump(report, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({"status": report["status"], "eval_count": report["eval_count"],
                      "metrics": report["metrics"]}, sort_keys=True))


if __name__ == "__main__":
    main()
