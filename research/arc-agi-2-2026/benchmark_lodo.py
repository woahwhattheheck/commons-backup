#!/usr/bin/env python3
"""Benchmark the existing ARC-AGI-2 solver by leave-one-demonstration-out.

This runner does not modify the solver. For each public training task, it holds
out each demonstration once, gives the remaining demonstrations to the solver,
and scores whether either emitted attempt exactly matches the held-out output.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import resource
import sys
import time
from pathlib import Path


def load_solver(path: Path):
    spec = importlib.util.spec_from_file_location("arc2_benchmark_solver", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load solver from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dataset_digest(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("training_dir", type=Path)
    parser.add_argument("--solver", type=Path, default=Path(__file__).with_name("arc2_baseline.py"))
    parser.add_argument("--expected-tasks", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--solver-source-commit")
    parser.add_argument("--dataset-source-commit")
    args = parser.parse_args()

    task_paths = sorted(args.training_dir.glob("*.json"))
    if len(task_paths) != args.expected_tasks:
        raise SystemExit(f"expected {args.expected_tasks} task files, found {len(task_paths)}")

    solver_path = args.solver.resolve()
    solver = load_solver(solver_path)
    corpus_sha256 = dataset_digest(task_paths, args.training_dir)

    started = time.perf_counter()
    fold_total = 0
    fold_passed = 0
    task_total = 0
    task_all_folds_passed = 0
    skipped_tasks: list[str] = []
    task_results: list[dict[str, object]] = []

    for task_path in task_paths:
        task = json.loads(task_path.read_text(encoding="utf-8"))
        demonstrations = task.get("train", [])
        if len(demonstrations) < 2:
            skipped_tasks.append(task_path.stem)
            continue

        task_total += 1
        passed = 0
        for index, held_out in enumerate(demonstrations):
            candidate = {
                "train": [pair for offset, pair in enumerate(demonstrations) if offset != index],
                "test": [{"input": held_out["input"]}],
            }
            prediction = solver.solve_task(candidate)[0]
            attempts = (prediction["attempt_1"], prediction["attempt_2"])
            success = held_out["output"] in attempts
            fold_total += 1
            fold_passed += int(success)
            passed += int(success)

        if passed == len(demonstrations):
            task_all_folds_passed += 1
        task_results.append(
            {
                "task_id": task_path.stem,
                "folds": len(demonstrations),
                "passed": passed,
            }
        )

    elapsed = time.perf_counter() - started
    peak_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = {
        "benchmark": "complete-public-training-leave-one-demonstration-out-pass-at-2",
        "benchmark_version": 1,
        "solver_path": solver_path.name,
        "solver_sha256": sha256_file(solver_path),
        "solver_source_commit": args.solver_source_commit,
        "training_corpus_sha256": corpus_sha256,
        "dataset_source_commit": args.dataset_source_commit,
        "task_files": len(task_paths),
        "eligible_tasks": task_total,
        "skipped_tasks": skipped_tasks,
        "folds": fold_total,
        "folds_passed": fold_passed,
        "fold_pass_rate": fold_passed / fold_total if fold_total else 0.0,
        "tasks_all_folds_passed": task_all_folds_passed,
        "task_all_folds_pass_rate": task_all_folds_passed / task_total if task_total else 0.0,
        "wall_seconds": elapsed,
        "peak_rss_kib": peak_rss_kib,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "task_results": task_results,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
