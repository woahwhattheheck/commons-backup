#!/usr/bin/env python3
"""Run resumable wide-field shards through the existing official evaluator."""

from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

PANEL_RNG_SEED = 20260907
PANEL_LIMITS = {"action_rpc_seconds": 1.0, "startup_seconds": 10.0,
                "game_seconds_between_steps": 120.0, "remaining_overage_time": 0}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _entry_identity(spec: str) -> dict:
    """Direct entrypoint identity only; never import an agent to inspect a report."""
    if not isinstance(spec, str):
        raise TypeError("Agent spec must be text")
    if spec == "official_starter":
        return {"entry": spec}
    path, sep, name = spec.partition("::")
    source = Path(path).resolve(strict=True)
    return {"entry": source.name, "callable": name if sep else "agent",
            "sha256": sha256(source)}


def expected_binding(job: dict, evaluator: Path, engine: Path, opponents: list[str]) -> dict:
    """Match the explicit fields this existing panel command actually requests.

    This is not a transitive import manifest or proof of prior execution. The
    evaluator remains responsible for its official-source and action contracts.
    """
    seeds = job["seeds"]
    if not seeds or any(type(seed) is not int for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("Panel seeds must be distinct integers")
    rivals = {}
    for item in opponents:
        label, sep, spec = item.partition("=")
        if not sep or not label or label in rivals or not spec:
            raise ValueError("Panel opponents require unique nonempty label=spec entries")
        rivals[label] = _entry_identity(spec)
    if not rivals:
        raise ValueError("Panel config requires explicit opponents")
    loader = evaluator.resolve().parent.parent / "20260907-offline-agent" / "evaluate.py"
    engine_bytes = {name: (engine / name).read_bytes() for name in
                    ("kaggriculture.py", "kaggriculture.json", "utils.py")}
    configuration = json.loads(engine_bytes["kaggriculture.json"])["configuration"]
    episode_steps = configuration["episodeSteps"]
    if isinstance(episode_steps, dict):
        episode_steps = episode_steps["default"]
    if type(episode_steps) is not int or episode_steps < 2:
        raise ValueError("Engine episodeSteps default must be an integer >= 2")
    return {"scope": "requested_cells_and_direct_source_files",
            "agent_rng_seed": PANEL_RNG_SEED, "limits": dict(PANEL_LIMITS),
            "episode_steps": episode_steps, "loader_sha256": sha256(loader),
            "seeds": list(seeds), "candidate": _entry_identity(job["candidate"]),
            "opponents": rivals, "evaluator_sha256": sha256(evaluator),
            "engine_sha256": {name: hashlib.sha256(data).hexdigest()
                              for name, data in engine_bytes.items()}}


def inspect_report(path: Path, expected: int, binding: dict | None = None) -> dict:
    """Read and bind one report snapshot; leave incomplete/mismatched bytes intact."""
    if not path.is_file():
        return {"complete": False, "problems": ["report_missing"], "sha256": None}
    try:
        raw = path.read_bytes()
    except OSError as error:
        return {"complete": False, "problems": ["report_read:" + type(error).__name__], "sha256": None}
    digest = hashlib.sha256(raw).hexdigest()
    problems = []
    try:
        report = json.loads(raw)
    except (ValueError, UnicodeError):
        return {"complete": False, "problems": ["report_json"], "sha256": digest}
    if not isinstance(report, dict):
        return {"complete": False, "problems": ["report_object"], "sha256": digest}
    games = report.get("games")
    if not isinstance(games, list):
        return {"complete": False, "problems": ["games_list"], "sha256": digest}
    if len(games) != expected:
        problems.append("game_count")
    cells = []
    for game in games:
        if not isinstance(game, dict):
            problems.append("game_object")
            continue
        if game.get("status") != "complete" or game.get("failure") is not None:
            problems.append("game_incomplete")
        scores = game.get("scores")
        if (not isinstance(scores, list) or len(scores) != 2 or any(
                not (type(value) is int or type(value) is float and math.isfinite(value)) for value in scores)):
            problems.append("game_scores")
        if binding is not None:
            if type(game.get("episode_steps")) is not int or game.get("episode_steps") != binding["episode_steps"]:
                problems.append("episode_steps")
            seed, seat, opponent = game.get("seed"), game.get("candidate_seat"), game.get("opponent")
            if type(seed) is not int or type(seat) is not int or seat not in (0, 1) or not isinstance(opponent, str):
                problems.append("game_cell")
            else:
                cells.append((seed, seat, opponent))
    if binding is not None:
        seeds = report.get("seeds")
        if (not isinstance(seeds, list) or any(type(seed) is not int for seed in seeds)
                or seeds != binding["seeds"]):
            problems.append("seeds")
        for key in ("evaluator_sha256", "engine_sha256", "loader_sha256", "agent_rng_seed", "limits"):
            if report.get(key) != binding[key]:
                problems.append(key)
        limits = report.get("limits")
        if not isinstance(limits, dict) or any(type(v) not in (int, float) for v in limits.values()):
            problems.append("limits")
        candidate = report.get("candidate")
        if not isinstance(candidate, dict) or any(candidate.get(k) != v for k, v in binding["candidate"].items()):
            problems.append("candidate_source")
        rivals = report.get("opponents")
        if not isinstance(rivals, dict) or set(rivals) != set(binding["opponents"]):
            problems.append("opponent_labels")
        else:
            for label, ident in binding["opponents"].items():
                found = rivals[label]
                if not isinstance(found, dict) or any(found.get(k) != v for k, v in ident.items()):
                    problems.append("opponent_source:" + label)
        wanted = Counter((seed, seat, label) for seed in binding["seeds"]
                         for label in binding["opponents"] for seat in (0, 1))
        if Counter(cells) != wanted:
            problems.append("game_cells")
    progress = report.get("progress")
    if progress is not None and (not isinstance(progress, dict) or progress.get("state") != "complete"):
        problems.append("progress_incomplete")
    return {"complete": not problems, "problems": sorted(set(problems)), "sha256": digest}


def valid_report(path: Path, expected: int, binding: dict | None = None) -> bool:
    # The two-argument compatibility form checks structure only. run_job always
    # supplies the requested source/cell binding for an execution/reuse verdict.
    return inspect_report(path, expected, binding)["complete"]


def run_job(job: dict, evaluator: Path, engine: Path, opponents: list[str], out: Path) -> dict:
    try:
        binding = expected_binding(job, evaluator, engine, opponents)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {**job, "status": "failed", "reason": "binding_unavailable",
                "error": type(error).__name__ + ": " + str(error)}
    seeds = job["seeds"]
    target = out / "raw" / job["arm"] / (f"{seeds[0]}-{seeds[-1]}.json")
    log = out / "logs" / job["arm"] / (f"{seeds[0]}-{seeds[-1]}.log")
    target.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    expected = len(seeds) * len(opponents) * 2
    validation = inspect_report(target, expected, binding)
    if validation["complete"]:
        return {**job, "status": "reused-complete", "report": str(target),
                "sha256": validation["sha256"], "source_binding": binding}
    if target.exists() or log.exists():
        # Preserve prior attempts, including failures. Explicit failed-cell replay
        # remains with the existing replay_failed_cells tool, not this resume check.
        return {**job, "status": "failed", "reason": "existing_evidence_not_reusable",
                "report": str(target), "log": str(log), "sha256": validation["sha256"],
                "validation": validation, "source_binding": binding}
    cmd = [sys.executable, "-B", str(evaluator), "--engine-dir", str(engine),
           "--candidate", job["candidate"],
           "--loader", str(evaluator.resolve().parent.parent / "20260907-offline-agent" / "evaluate.py"),
           "--rng-seed", str(PANEL_RNG_SEED),
           "--action-timeout", str(PANEL_LIMITS["action_rpc_seconds"]),
           "--startup-timeout", str(PANEL_LIMITS["startup_seconds"]),
           "--game-timeout", str(PANEL_LIMITS["game_seconds_between_steps"])]
    for opponent in opponents:
        cmd += ["--opponent", opponent]
    cmd += ["--seeds", ",".join(map(str, seeds)), "--output", str(target)]
    started = time.time()
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except UnicodeDecodeError as error:
        # Preserve display diagnostics without converting the failed exchange
        # into a successful result or replacing its original decoding exception.
        try:
            log.write_text(error.object.decode(error.encoding, errors="backslashreplace"), encoding="utf-8")
        except Exception as output_error:
            raise error from output_error
        raise
    log.write_text(proc.stdout)
    validation = inspect_report(target, expected, binding)
    try:
        if expected_binding(job, evaluator, engine, opponents) != binding:
            validation["problems"].append("source_changed_during_job")
            validation["complete"] = False
    except (OSError, ValueError, KeyError, TypeError):
        validation["problems"].append("source_unavailable_after_job")
        validation["complete"] = False
    return {**job, "status": "complete" if validation["complete"] and proc.returncode == 0 else "failed",
            "returncode": proc.returncode, "elapsed_seconds": time.time() - started,
            "report": str(target), "log": str(log), "sha256": validation["sha256"],
            "validation": validation, "source_binding": binding}



def write_run_state(path: Path, records: list[dict]) -> None:
    """Replace one complete UTF-8 checkpoint; never truncate the prior file.

    Staging and replacement share a directory. This is a single-file guarantee,
    not a transaction with raw reports or a power-loss durability guarantee.
    """
    payload = (json.dumps(records, indent=2) + "\n").encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            if stream.write(payload) != len(payload):
                raise OSError("Short run-state checkpoint write")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                # Cleanup must not replace the original publication exception.
                # A hard exit or failed cleanup can leave an unreferenced stage.
                pass


def validate_panel_config(cfg: object, workers: int) -> None:
    """Require runnable panel dimensions before creating output or starting work.

    Additional configuration fields and all nonempty actor references pass through
    unchanged. This validates the requested job grid, not source or result identity.
    """
    if not isinstance(cfg, dict):
        raise ValueError("panel configuration must be a JSON object")
    seeds = cfg.get("seeds")
    if not isinstance(seeds, dict):
        raise ValueError("seeds must be an object with first, last and shard_size")
    first, last = seeds.get("first"), seeds.get("last")
    if type(first) is not int or type(last) is not int:
        raise ValueError("seeds.first and seeds.last must be integers")
    if first > last:
        raise ValueError("seeds.first must not exceed seeds.last")
    try:
        # Preserve the existing int-conversion behavior for nonempty shards.
        size = int(seeds["shard_size"])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("seeds.shard_size must convert to a positive integer") from None
    if size <= 0:
        raise ValueError("seeds.shard_size must convert to a positive integer")
    arms = cfg.get("arms")
    if not isinstance(arms, dict) or not arms:
        raise ValueError("arms must contain at least one candidate")
    if any(not isinstance(value, str) or not value.strip() for value in arms.values()):
        raise ValueError("each candidate reference must be a nonempty string")
    opponents = cfg.get("opponents")
    if not isinstance(opponents, list) or not opponents:
        raise ValueError("opponents must contain at least one opponent")
    if any(not isinstance(value, str) or not value.strip() for value in opponents):
        raise ValueError("each opponent reference must be a nonempty string")
    for field in ("evaluator", "engine"):
        if not isinstance(cfg.get(field), str) or not cfg[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    if type(workers) is not int or workers <= 0:
        raise ValueError("--jobs must be a positive integer")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    try:
        cfg = json.loads(args.config.read_text())
        validate_panel_config(cfg, args.jobs)
    except (OSError, UnicodeError, ValueError) as error:
        ap.error(f"invalid panel configuration: {error}")
    args.output.mkdir(parents=True, exist_ok=True)
    seeds = list(range(cfg["seeds"]["first"], cfg["seeds"]["last"] + 1))
    size = int(cfg["seeds"]["shard_size"])
    jobs = []
    for arm, candidate in cfg["arms"].items():
        for i in range(0, len(seeds), size):
            jobs.append({"arm": arm, "candidate": candidate, "seeds": seeds[i:i + size]})
    records = []
    first_failure = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_job, j, Path(cfg["evaluator"]), Path(cfg["engine"]),
                               cfg["opponents"], args.output): j for j in jobs}
        for future in concurrent.futures.as_completed(futures):
            try:
                rec = future.result()
            except Exception as exc:
                # All jobs were already submitted. Retain their results before
                # re-raising the first ordinary failure; do not retry any job.
                # BaseException cancellation is deliberately not converted.
                if first_failure is None:
                    first_failure = (exc, exc.__traceback__)
                rec = {**futures[future], "status": "failed",
                       "failure": {"kind": "runner_exception",
                                   "type": type(exc).__name__, "message": str(exc)}}
            records.append(rec)
            try:
                write_run_state(args.output / "run-state.json", records)
            except Exception as output_error:
                if first_failure is not None:
                    error, traceback = first_failure
                    raise error.with_traceback(traceback) from output_error
                raise
            print(json.dumps(rec, sort_keys=True), flush=True)
    if first_failure is not None:
        error, traceback = first_failure
        raise error.with_traceback(traceback)
    failed = [r for r in records if r["status"] == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())