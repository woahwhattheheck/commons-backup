# SPDX-License-Identifier: Apache-2.0
"""Replay one complete saved observation stream through a file-agent.

Run this program in a fresh process for each mode. Worker mode uses one
persistent ThreadPoolExecutor thread so stateful actors are neither rebuilt nor
moved between workers. It records errors and mismatches; it does not call the
game interpreter or infer unexported fallback metadata.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_official(path: Path):
    spec = importlib.util.spec_from_file_location("titan_worker_consumer_official", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot import official loader adapter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_frames(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    if [row.get("step") for row in rows] != list(range(719)):
        raise ValueError("Require one complete chronological 719-action stream")
    return rows


def replay(*, mode: str, official_path: Path, entrypoint: Path, frames: Path,
           archive: Path, titan_agent: Path, deadline_adapter: Path,
           outer_timeout: float = 2.0) -> dict:
    official = load_official(official_path)
    actor = official.make_agent(entrypoint)
    source = read_frames(frames)
    executor = (ThreadPoolExecutor(max_workers=1, thread_name_prefix="titan-consumer")
                if mode == "worker" else None)
    rows: list[dict] = []
    errors: list[dict] = []
    mismatches: list[int] = []
    started = time.perf_counter()
    try:
        for frame in source:
            step = int(frame["step"])
            observation = frame["observations"][0]
            expected = frame["actions"][0]
            call_started = time.perf_counter()
            try:
                if executor is None:
                    action = actor(observation, {})
                else:
                    action = executor.submit(actor, observation, {}).result(
                        timeout=outer_timeout)
                error = None
            except FutureTimeout:
                action = None
                error = "outer_future_timeout"
            except BaseException as exc:
                action = None
                error = f"{type(exc).__name__}: {exc}"
            elapsed = time.perf_counter() - call_started
            if error is not None:
                errors.append({"step": step, "error": error})
            if action != expected:
                mismatches.append(step)
            rows.append({"step": step, "elapsed": elapsed, "error": error,
                         "matches_expected": action == expected})
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
    return {
        "schema": "titan.current-7b58.input-budget-worker-consumer.v1",
        "mode": mode,
        "archive_sha256": sha256(archive),
        "titan_agent_sha256": sha256(titan_agent),
        "deadline_adapter_sha256": sha256(deadline_adapter),
        "entrypoint_sha256": sha256(entrypoint),
        "source_frames_sha256": sha256(frames),
        "actions": len(rows),
        "errors": errors,
        "mismatched_steps": mismatches,
        "fallback_count": None,
        "max_call_seconds": max(row["elapsed"] for row in rows),
        "mean_call_seconds": sum(row["elapsed"] for row in rows) / len(rows),
        "wall_seconds": time.perf_counter() - started,
        "rows": rows,
        "scope": "saved action-stream compatibility; no game or interpreter calls",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("main", "worker"), required=True)
    parser.add_argument("--official", type=Path, required=True)
    parser.add_argument("--entrypoint", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--titan-agent", type=Path, required=True)
    parser.add_argument("--deadline-adapter", type=Path, required=True)
    parser.add_argument("--outer-timeout", type=float, default=2.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(mode=args.mode, official_path=args.official,
                    entrypoint=args.entrypoint, frames=args.frames,
                    archive=args.archive, titan_agent=args.titan_agent,
                    deadline_adapter=args.deadline_adapter,
                    outer_timeout=args.outer_timeout)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    return 0 if (result["actions"] == 719 and not result["errors"] and
                 not result["mismatched_steps"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
