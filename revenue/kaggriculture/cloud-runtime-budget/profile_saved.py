# SPDX-License-Identifier: Apache-2.0
"""Profile one actor over saved observations; never advance a game or retry an action.

The two passes run in separate Python processes. The ordinary pass supplies wall
costs; the instrumented pass supplies cumulative hot-function costs. Output/action
hash correspondence is checked rather than assumed. TANDEM's existing TimedFactory
is consumed as a file dependency, not copied or replaced.
"""
from __future__ import annotations

import argparse
import copy
import cProfile
import hashlib
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import platform
import pstats
import resource
import random
import subprocess
import sys
import time
import gzip


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def load_module(path: Path, name: str, *, loaded_sources=None):
    """Execute one source read, never a timestamp-valid cached bytecode file."""
    source = path.read_bytes()
    if loaded_sources is not None:
        loaded_sources[name] = {"path": str(path), "sha256": digest(source)}
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("not an importable Python source")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def bind_action(fn):
    """Select shape before the first invocation; a body TypeError is never retried."""
    signature = inspect.signature(fn)
    try:
        signature.bind({}, {})
    except TypeError:
        signature.bind({})
        return lambda obs, cfg: fn(obs)
    return lambda obs, cfg: fn(obs, cfg)


def load_execution_receipt(path: Path):
    raw = path.read_bytes()
    receipt = json.loads(raw)
    if receipt.get("schema") != "titan.recorded-actor-inputs.v1":
        raise ValueError("unsupported recorded-input receipt")
    for field in ("candidate_actor_rng_seed", "candidate_pythonhashseed"):
        if type(receipt.get(field)) is not int:
            raise ValueError("recorded actor seed is missing or invalid")
    return receipt, digest(raw)


def load_workload(path: Path, seat: int, limit: int, receipt_path: Path | None = None):
    raw = path.read_bytes()
    decoded = gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
    if receipt_path is not None:
        receipt, receipt_hash = load_execution_receipt(receipt_path)
        if digest(raw) != receipt.get("output_file_sha256") or digest(decoded) != receipt.get("input_jsonl_sha256"):
            raise ValueError("recorded JSONL bytes differ from their receipt")
        rows = [json.loads(line) for line in decoded.splitlines() if line.strip()]
        if len(rows) != receipt.get("observation_count") or not rows:
            raise ValueError("recorded observation count differs")
        if receipt.get("candidate_seat") != seat:
            raise ValueError("recorded candidate seat differs")
        for row in rows:
            if row.get("seat") != seat or row.get("step") != row.get("observation", {}).get("step"):
                raise ValueError("recorded row seat or clock differs")
            if not isinstance(row.get("configuration"), dict):
                raise ValueError("recorded row configuration is missing")
        value = {"schema": "titan.profile.observations.v1", "configuration": rows[0]["configuration"],
                 "records": rows, "provenance": {"kind": "recorded_actor_inputs",
                    "receipt_sha256": receipt_hash, "source_receipt": receipt}}
    else:
        value = json.loads(decoded)
    for _ in range(8):
        if isinstance(value, str):
            value = json.loads(value)
        elif isinstance(value, dict) and ("steps" in value or "records" in value):
            break
        elif isinstance(value, dict):
            keys = [k for k in ("replay", "result", "episode", "Replay") if k in value]
            if len(keys) != 1:
                raise ValueError("ambiguous or unrecognized workload envelope")
            value = value[keys[0]]
        else:
            raise ValueError("no observation workload")
    if not isinstance(value, dict):
        raise ValueError("no observation workload object")
    cfg = copy.deepcopy(value.get("configuration", {}))
    if not isinstance(cfg, dict):
        raise ValueError("configuration must be a mapping")
    cfg.pop("seed", None)  # labels and hidden seed never become agent input
    records = []
    if value.get("schema") == "titan.profile.observations.v1":
        for row in value["records"][:limit]:
            records.append(copy.deepcopy(row))
        provenance = value.get("provenance", {})
    elif isinstance(value.get("steps"), list):
        for step, frame in enumerate(value["steps"][:-1][:limit]):
            rows = frame.get("state") if isinstance(frame, dict) else frame
            if not isinstance(rows, list) or len(rows) != 2:
                raise ValueError("expected two player rows")
            own = copy.deepcopy(rows[seat].get("observation", {}))
            for key in ("farms", "market", "town", "step", "day", "hour"):
                if key not in own:
                    source = next((r.get("observation", {})[key] for r in rows
                                   if key in r.get("observation", {})), None)
                    if source is not None:
                        own[key] = copy.deepcopy(source)
            own["player"] = seat
            own.setdefault("step", step)
            records.append({"observation": own})
        provenance = {"kind": "retained_replay_off_policy", "info_id":
                      (value.get("info") or {}).get("EpisodeId")}
    else:
        raise ValueError("no complete observations; summary/action/timing rows cannot be replayed")
    if not records:
        raise ValueError("empty observation workload")
    last = -1
    for row in records:
        obs = row.get("observation")
        if not isinstance(obs, dict) or not all(k in obs for k in ("farms", "private", "market")):
            raise ValueError("full own observation is required")
        step = obs.get("step")
        if step is None:
            step = int(obs["day"]) * int(cfg.get("turnsPerDay", 24)) + int(obs["hour"])
            obs["step"] = step
        if type(step) is not int or step != last + 1:
            raise ValueError("stateful actor requires an uninterrupted prefix starting at zero")
        if obs.get("player", seat) != seat:
            raise ValueError("observation player does not match selected seat")
        last = step
    return cfg, records, {"transport_sha256": digest(raw), "decoded_sha256": digest(decoded),
                          "records": len(records), "provenance": provenance}


def describe_environment():
    result = {"python": sys.version, "platform": platform.platform(), "logical_cpus": os.cpu_count(),
              "cpu_affinity_count": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None}
    for name in ("cpu.max", "memory.max"):
        p = Path("/sys/fs/cgroup") / name
        result["cgroup_" + name] = p.read_text().strip() if p.exists() else None
    return result


def source_rows(root: Path):
    return {str(p.relative_to(root)): digest(p.read_bytes())
            for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts}


def worker(args):
    report = {"schema": "titan.saved-runtime-pass.v1", "mode": args.worker_mode,
              "status": "error", "classification": args.classification,
              "calls": [], "environment": describe_environment(),
              "process_id": os.getpid(),
              "entrypoint": str(args.entrypoint), "profiler_sha256": digest(Path(__file__).read_bytes())}
    observer = None
    loaded_sources = {}
    source_root = getattr(args, "source_root", None) or args.entrypoint.parent
    report["runtime_source_root"] = str(source_root)
    report["factory_kwargs"] = getattr(args, "factory_kwargs", None) or {}
    source_before = None
    prof = cProfile.Profile() if args.worker_mode == "profile" else None
    profile_steps = {int(step) for step in (getattr(args, "profile_steps", "") or "").split(",") if step}
    report["profiled_steps"] = sorted(profile_steps) if prof else []
    try:
        t0 = time.perf_counter()
        cfg, records, report["input"] = load_workload(args.replay, args.seat, args.max_decisions, getattr(args, "input_receipt", None))
        report["input_load_s"] = time.perf_counter() - t0
        timing = load_module(args.timing_source, "finch_existing_timing", loaded_sources=loaded_sources)
        report["timing_source_sha256"] = loaded_sources["finch_existing_timing"]["sha256"]
        execution = (report["input"]["provenance"].get("source_receipt", {})
                     if getattr(args, "input_receipt", None) is not None else {})
        actor_seed = execution.get("candidate_actor_rng_seed")
        report["actor_rng_seed"] = actor_seed
        report["pythonhashseed"] = os.environ.get("PYTHONHASHSEED")
        if actor_seed is not None:
            random.seed(actor_seed)
        source_before = source_rows(source_root)
        sys.path.insert(0, str(args.entrypoint.parent))
        t0 = time.perf_counter()
        target_load_started = t0
        module = load_module(args.entrypoint, "finch_profile_target", loaded_sources=loaded_sources)
        report["entry_import_s"] = time.perf_counter() - t0
        holder = {}

        def factory():
            actor = getattr(module, args.factory)(**report["factory_kwargs"])
            holder["actor"] = actor
            method = actor if args.method == "__call__" else getattr(actor, args.method)
            return bind_action(method)

        observer = timing.TimedFactory(factory)
        actor = observer()
        output_hash = hashlib.sha256()
        report["expected_actions"] = {"present": 0, "mismatches": 0, "first_mismatch": None}
        for row in records:
            obs = copy.deepcopy(row["observation"])
            configuration = copy.deepcopy(row.get("configuration", cfg))
            configuration.pop("seed", None)
            step = obs["step"]
            started = time.perf_counter()
            cpu_started = time.process_time()
            try:
                if prof and step in profile_steps:
                    prof.enable()
                action = actor(obs, configuration)
            finally:
                if prof:
                    prof.disable()
                elapsed = time.perf_counter() - started
                cpu_elapsed = time.process_time() - cpu_started
                report["calls"].append({"step": step, "wall_s": elapsed, "cpu_s": cpu_elapsed})
                if len(report["calls"]) == 1:
                    report["target_load_through_first_attempt_wall_s"] = time.perf_counter() - target_load_started
            if not isinstance(action, dict):
                raise TypeError("policy returned a non-dict action")
            encoded = canonical(action)
            output_hash.update(len(encoded).to_bytes(8, "big") + encoded)
            report["calls"][-1]["action_sha256"] = digest(encoded)
            diagnostics = getattr(holder["actor"], "diagnostics", {})
            if not isinstance(diagnostics, dict):
                diagnostics = {}
            report["calls"][-1]["diagnostics"] = {k: diagnostics.get(k) for k in
                ("status", "reason", "seed_reason") if k in diagnostics}
            if "expected_action" in row:
                expected = report["expected_actions"]
                expected["present"] += 1
                if canonical(row["expected_action"]) != encoded:
                    expected["mismatches"] += 1
                    if expected["first_mismatch"] is None:
                        expected["first_mismatch"] = step
        report["action_sequence_sha256"] = output_hash.hexdigest()
        report["status"] = "complete"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)[:300]}
    finally:
        report["timings"] = observer.timings() if observer else None
        report["runtime_sources"] = source_before
        report["loaded_sources"] = loaded_sources
        try:
            report["loaded_sources_unchanged"] = bool(loaded_sources) and all(
                digest(Path(row["path"]).read_bytes()) == row["sha256"]
                for row in loaded_sources.values())
        except OSError:
            report["loaded_sources_unchanged"] = False
        report["sources_unchanged"] = source_before == source_rows(source_root) if source_before else None
        report["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        values = [r["wall_s"] for r in report["calls"]]
        report["ordinary_threshold_s"] = 1.0
        report["calls_over_threshold"] = sum(t > 1.0 for t in values)
        report["total_observed_excess_s"] = sum(max(0.0, t - 1.0) for t in values)
        report["p99_call_s"] = sorted(values)[math.ceil(.99 * len(values))-1] if values else None
        if report["timings"] and report["timings"]["initialization_plus_first_action_s"] is not None:
            report["entry_import_through_first_action_s"] = report["entry_import_s"] + report["timings"]["initialization_plus_first_action_s"]
        if prof and prof.getstats():
            stats = pstats.Stats(prof)
            report["hot_functions"] = sorted([
                {"file": str(Path(filename).relative_to(source_root)), "line": lineno,
                 "function": name, "primitive_calls": cc, "calls": nc,
                 "self_s": tt, "cumulative_s": ct}
                for (filename, lineno, name), (cc, nc, tt, ct, _callers) in stats.stats.items()
                if str(filename).startswith(str(source_root) + os.sep)
            ], key=lambda r: r["cumulative_s"], reverse=True)[:50]
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return 0 if report["status"] == "complete" else 2


def read_child_report(path: Path, mode: str):
    """Keep interrupted/malformed child bytes and let the supervisor finish."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {"status": "process_error", "mode": mode,
                "error": {"type": "MissingChildReport"}}
    except OSError as exc:
        return {"status": "process_error", "mode": mode,
                "error": {"type": "UnreadableChildReport", "message": str(exc)[:300]}}
    try:
        report = json.loads(raw)
        if not isinstance(report, dict):
            raise ValueError("child report must be an object")
        if not isinstance(report.get("status"), str) or not report["status"]:
            raise ValueError("child report status is missing or invalid")
        calls = report.get("calls", [])
        if not isinstance(calls, list) or (report["status"] == "complete" and not calls):
            raise ValueError("child report calls are missing or invalid")
        for row in calls:
            if not isinstance(row, dict) or type(row.get("step")) is not int:
                raise ValueError("child report step is missing or invalid")
            wall = row.get("wall_s")
            if type(wall) not in (int, float) or wall < 0 or (type(wall) is float and not math.isfinite(wall)):
                raise ValueError("child report wall time is missing or invalid")
        if report["status"] == "complete":
            # Missing identities must not compare equal as None in the supervisor.
            def require_digest(value, field):
                if (not isinstance(value, str) or len(value) != 64
                        or any(char not in "0123456789abcdef" for char in value)):
                    raise ValueError("child report %s is not a SHA-256 digest" % field)

            if report.get("schema") != "titan.saved-runtime-pass.v1":
                raise ValueError("complete child report schema is missing or invalid")
            if report.get("mode") != mode:
                raise ValueError("complete child report mode differs from requested pass")
            if report.get("error"):
                raise ValueError("complete child report also contains an error")
            for field in ("action_sequence_sha256", "profiler_sha256", "timing_source_sha256"):
                require_digest(report.get(field), field)
            inputs = report.get("input")
            if not isinstance(inputs, dict):
                raise ValueError("complete child report input identity is missing")
            if type(inputs.get("records")) is not int or inputs["records"] != len(calls):
                raise ValueError("complete child report input count differs from calls")
            for field in ("transport_sha256", "decoded_sha256"):
                require_digest(inputs.get(field), "input." + field)
            runtime_sources = report.get("runtime_sources")
            if not isinstance(runtime_sources, dict):
                raise ValueError("complete child report runtime source identities are missing")
            for name, value in runtime_sources.items():
                if not isinstance(name, str) or not name:
                    raise ValueError("complete child report runtime source name is invalid")
                require_digest(value, "runtime_sources." + name)
            loaded_sources = report.get("loaded_sources")
            if not isinstance(loaded_sources, dict):
                raise ValueError("complete child report loaded source identities are missing")
            for name in ("finch_existing_timing", "finch_profile_target"):
                value = loaded_sources.get(name)
                if not isinstance(value, dict) or not isinstance(value.get("path"), str) or not value["path"]:
                    raise ValueError("complete child report loaded source is missing: " + name)
                require_digest(value.get("sha256"), "loaded_sources." + name)
            if report["timing_source_sha256"] != loaded_sources["finch_existing_timing"]["sha256"]:
                raise ValueError("complete child report timing source identities disagree")
            for index, row in enumerate(calls):
                if row["step"] != index:
                    raise ValueError("complete child report calls are not a zero-based uninterrupted prefix")
                require_digest(row.get("action_sha256"), "calls[%d].action_sha256" % index)
        json.dumps(report, allow_nan=False)  # validate the eventual receipt encoding too
    except (ValueError, UnicodeError, RecursionError) as exc:
        retained = path.with_name(path.stem + ".invalid.bin")
        with retained.open("xb") as handle:
            handle.write(raw)
        return {"status": "process_error", "mode": mode,
                "error": {"type": "InvalidChildReport", "message": str(exc)[:300]},
                "invalid_report": {"path": str(retained), "bytes": len(raw), "sha256": digest(raw)}}
    return report


def supervise(args):
    args.output.parent.mkdir(parents=True, exist_ok=True)
    outputs = [args.output] + [args.output.with_name(args.output.stem + "." + mode + suffix)
        for mode in ("ordinary", "profile") for suffix in (".json", ".log", ".invalid.bin", ".timeout.bin")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("use a new result basename; previous receipts are preserved")
    reports = []
    for mode in ("ordinary", "profile"):
        child_output = args.output.with_name(args.output.stem + "." + mode + ".json")
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker-mode", mode,
                   "--entrypoint", str(args.entrypoint), "--factory", args.factory,
                   "--method", args.method, "--timing-source", str(args.timing_source),
                   "--replay", str(args.replay), "--seat", str(args.seat),
                   "--max-decisions", str(args.max_decisions), "--classification", args.classification,
                   "--output", str(child_output)]
        if mode == "profile" and reports and reports[0].get("calls"):
            calls = reports[0]["calls"]
            steps = {calls[0]["step"], calls[-1]["step"]}
            steps.update(row["step"] for row in sorted(calls, key=lambda row: row["wall_s"], reverse=True)[:getattr(args,"profile_slowest",5)])
            command.extend(["--profile-steps", ",".join(map(str, sorted(steps)))])
        if getattr(args, "factory_kwargs", None):
            command.extend(["--factory-kwargs", json.dumps(args.factory_kwargs)])
        if getattr(args, "source_root", None):
            command.extend(["--source-root", str(args.source_root)])
        environment = None
        input_receipt = getattr(args, "input_receipt", None)
        if input_receipt is not None:
            execution, _ = load_execution_receipt(input_receipt)
            command.extend(["--input-receipt", str(input_receipt)])
            environment = dict(os.environ, PYTHONHASHSEED=str(execution["candidate_pythonhashseed"] % (2**32)))
        started = time.perf_counter()
        try:
            run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                 errors="backslashreplace", timeout=args.process_timeout, env=environment)
            code, log = run.returncode, run.stdout + run.stderr
            report = read_child_report(child_output, mode)
        except subprocess.TimeoutExpired as exc:
            code = None
            def decoded(value):
                return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")
            log = decoded(exc.stdout) + decoded(exc.stderr)
            report = {"status": "process_timeout", "mode": mode,
                      "error": {"type": "ProcessTimeout", "limit_s": args.process_timeout}}
            # A worker can finish its report and then hang during shutdown.
            # Preserve any bytes before replacing the path with timeout truth.
            try:
                raw = child_output.read_bytes()
            except FileNotFoundError:
                pass
            else:
                retained = child_output.with_name(child_output.stem + ".timeout.bin")
                with retained.open("xb") as handle:
                    handle.write(raw)
                report["timed_out_child_report"] = {
                    "path": str(retained), "bytes": len(raw), "sha256": digest(raw)}
        elapsed = time.perf_counter() - started
        report["process_start_to_exit_wall_s"] = elapsed
        report["process_exit_code"] = code
        child_output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        args.output.with_name(args.output.stem + "." + mode + ".log").write_text(log)
        reports.append(report)
    normal, profiled = reports
    matching = (normal.get("status") == profiled.get("status") == "complete" and
                normal.get("action_sequence_sha256") == profiled.get("action_sequence_sha256") and
                len(normal["calls"]) == len(profiled["calls"]) and
                [(row["step"], row["action_sha256"]) for row in normal["calls"]] ==
                [(row["step"], row["action_sha256"]) for row in profiled["calls"]] and
                normal.get("runtime_sources") == profiled.get("runtime_sources") and
                normal.get("input") == profiled.get("input") and
                normal.get("loaded_sources") == profiled.get("loaded_sources") and
                normal.get("loaded_sources_unchanged") is True and profiled.get("loaded_sources_unchanged") is True and
                normal.get("sources_unchanged") is True and profiled.get("sources_unchanged") is True and
                normal.get("process_exit_code") == profiled.get("process_exit_code") == 0)
    result = {"schema": "titan.saved-runtime-budget.v1", "ordinary": normal,
              "instrumented": profiled, "instrumentation_action_parity": matching,
              "limits": ["No engine transitions or game outcomes are computed.",
                         "Only directly loaded entrypoint and timing source bytes are execution-bound; transitive imports are not frozen.",
                         "Saved replay workloads are off-policy unless separately established by their owner.",
                         "Instrumented wall timings include profiler overhead; ordinary timings are the cost result.",
                         "Hot-function data covers the first, last and selected slowest ordinary-pass steps only.",
                         "Cumulative functions overlap; do not sum their maxima or durations.",
                         "Process duration includes workload parsing, profiling, serialization and interpreter shutdown.",
                         "The one-second threshold is not a hosted timeout verdict; official overage rules are separate."]}
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "parity": matching,
                      "calls": len(normal.get("calls", [])), "status": normal["status"]}))
    return 0 if matching else 2


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("entrypoint", "timing-source", "replay", "output"):
        ap.add_argument("--" + name, type=Path,
                        required=True)
    ap.add_argument("--input-receipt", type=Path, help="TRACE native JSONL receipt; supplies actor RNG and process hash seed")
    ap.add_argument("--factory", default="make_agent")
    ap.add_argument("--factory-kwargs", type=json.loads, default={}, help="JSON object forwarded once to the selected factory")
    ap.add_argument("--source-root", type=Path, help="Explicit runtime dependency root for source binding and hot-function attribution")
    ap.add_argument("--method", default="act")
    ap.add_argument("--seat", type=int, choices=(0, 1), default=0)
    ap.add_argument("--max-decisions", type=int, default=719)
    ap.add_argument("--classification", default="retained-public-off-policy")
    ap.add_argument("--process-timeout", type=float, default=180)
    ap.add_argument("--worker-mode", choices=("ordinary", "profile"))
    ap.add_argument("--profile-slowest", type=int, default=5)
    ap.add_argument("--profile-steps", default="")
    args = ap.parse_args()
    for name in ("entrypoint", "timing_source", "replay", "output"):
        setattr(args, name, getattr(args, name).resolve())
    if args.input_receipt is not None:
        args.input_receipt = args.input_receipt.resolve()
    if args.source_root is not None:
        args.source_root = args.source_root.resolve()
    if not isinstance(args.factory_kwargs, dict):
        ap.error("--factory-kwargs must be a JSON object")
    if args.process_timeout <= 0:
        ap.error("--process-timeout must be positive")
    if args.profile_slowest < 1:
        ap.error("--profile-slowest must be positive")
    if args.max_decisions < 1:
        ap.error("--max-decisions must be positive")
    return worker(args) if args.worker_mode else supervise(args)


if __name__ == "__main__":
    raise SystemExit(main())