#!/usr/bin/env python3
"""Recover actor inputs from an existing WIDEFIELD recorded-action trajectory.

No actor process or policy is run. The existing tracer and official interpreter
remain the execution contract. Recovered inputs are released only after the
recorded per-step banks, terminal scores and complete trace digest agree.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCHEMA = "titan.widefield.loss-trace.v1"


def load(path: Path, name: str) -> Any:
    """Execute and identify one captured source, without consulting bytecode.

    Imported dependencies are not snapshotted. Register before execution for
    normal module semantics, and restore the prior binding if execution fails.
    """
    source = path.read_bytes()
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    code = compile(source, str(path), "exec")
    module = importlib.util.module_from_spec(spec)
    missing = object()
    previous = sys.modules.get(name, missing)
    sys.modules[name] = module
    try:
        exec(code, module.__dict__)
    except BaseException:
        if previous is missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    module.__trace_input_source_sha256__ = hashlib.sha256(source).hexdigest()
    return module


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def validate_game(game: dict[str, Any]) -> list[dict[str, Any]]:
    if game.get("status") != "complete" or game.get("failure") is not None:
        raise ValueError("Only complete recorded trajectories are supported")
    if type(game.get("candidate_seat")) is not int or game["candidate_seat"] not in (0, 1):
        raise ValueError("candidate_seat must be 0 or 1")
    if type(game.get("seed")) is not int:
        raise ValueError("The original environment seed must be present")
    digest = game.get("trace_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Missing or invalid original trace digest")
    rows = game.get("actions_and_timing")
    if not isinstance(rows, list) or not rows or game.get("steps_completed") != len(rows):
        raise ValueError("Missing or inconsistent complete action sequence")
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or type(row.get("step")) is not int or row["step"] != index:
            raise ValueError(f"Noncontiguous recorded step at {index}")
        actions = row.get("actions")
        if not isinstance(actions, list) or len(actions) != 2 or not all(isinstance(a, dict) for a in actions):
            raise ValueError(f"Both original actions are required at step {index}")
        bank = row.get("bank")
        if not isinstance(bank, list) or len(bank) != 2 or any(type(v) not in (int, float) for v in bank):
            raise ValueError(f"Both original bank values are required at step {index}")
        canonical({"actions": actions, "bank": bank})
    return rows


def recover_inputs(game: dict[str, Any], evaluator: Any, tracer: Any, engine: Any,
                   engine_dir: Path, loader: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Replay recorded actions; return candidate-only inputs after correspondence.

    The evaluator module is never patched. Its isolated facade replaces only
    actor construction and fingerprint lookup; the existing tracer drives time,
    interpreter calls, observations, configuration and the original trace hash.
    This reconstructs input history, not the candidate's internal Python state.
    """
    original_rows = validate_game(game)
    seat = game["candidate_seat"]
    tags = ("__recorded_candidate__", "__recorded_opponent__")
    fingerprints = {tags[0]: copy.deepcopy(game.get("candidate")),
                    tags[1]: copy.deepcopy(game.get("opponent"))}
    inputs: list[dict[str, Any]] = []
    actors: list[Any] = []

    class RecordedActor:
        def __init__(self, spec: str, cache: Any, loader_path: Any, rng_seed: int):
            if spec not in tags:
                raise ValueError("Unexpected recorded actor identity")
            self.seat = seat if spec == tags[0] else 1 - seat
            self.index = 0
            self.ready = {"kind": "ready"}
            self.closed = False
            actors.append(self)

        def act(self, observation: Any, configuration: Any, timeout: float) -> dict[str, Any]:
            step = self.index
            if step >= len(original_rows) or observation.get("step") != step:
                raise ValueError(f"Recorded actor step mismatch at {step}")
            # Match Actor.exchange's JSON transport boundary and detach from the
            # mutable interpreter state before the next recorded transition.
            request = json.loads(evaluator.encoded({"observation": observation,
                                                    "configuration": configuration}))
            row = original_rows[step]
            action = copy.deepcopy(row["actions"][self.seat])
            if self.seat == seat:
                inputs.append({"step": step, "seat": seat, **request,
                               "expected_action": copy.deepcopy(action)})
            self.index += 1
            # These are placeholders required by tracer.play, never a timing
            # measurement. The reconstructed play result is not published.
            return {"kind": "action", "action": action,
                    "call_seconds": 0.0, "call_cpu_seconds": 0.0}

        def close(self) -> None:
            self.closed = True

        def report(self) -> dict[str, Any]:
            return {"recorded_action_playback": True, "calls": self.index}

    facade = SimpleNamespace(**vars(evaluator))
    facade.Actor = RecordedActor
    facade.fingerprint = lambda tag: copy.deepcopy(fingerprints[tag])
    replay = tracer.play(facade, engine, engine_dir, loader, tags[0], tags[1],
                         game["seed"], seat)
    if replay["status"] != "complete" or replay.get("failure") is not None:
        raise ValueError("Recorded replay did not reach the original terminal boundary")
    if len(inputs) != len(original_rows) or replay["steps_completed"] != len(original_rows):
        raise ValueError("Recorded replay length differs")
    for original, actual in zip(original_rows, replay["actions_and_timing"]):
        for key in ("actions", "bank"):
            if canonical(original[key]) != canonical(actual[key]):
                raise ValueError(f"Recorded {key} mismatch at step {original['step']}")
    if replay["scores"] != game.get("scores"):
        raise ValueError("Recorded terminal scores differ")
    if replay["trace_sha256"] != game["trace_sha256"]:
        raise ValueError("Recorded trace digest differs; no observation stream released")
    if len(actors) != 2 or not all(a.closed for a in actors):
        raise ValueError("Recorded actor lifecycle is incomplete")
    stream_hash = hashlib.sha256()
    for row in inputs:
        stream_hash.update(canonical(row) + b"\n")
    receipt = {
        "schema": "titan.recorded-actor-inputs.v1",
        "source_trace_sha256": game["trace_sha256"],
        "reconstructed_trace_sha256": replay["trace_sha256"],
        "input_jsonl_sha256": stream_hash.hexdigest(),
        "observation_count": len(inputs), "candidate_seat": seat,
        "environment_seed_provenance_only": game["seed"],
        "candidate": copy.deepcopy(game.get("candidate")),
        "opponent": copy.deepcopy(game.get("opponent")),
        "candidate_actor_rng_seed": 20260907,
        "candidate_pythonhashseed": 20260907,
        "policy_calls": 0, "new_game_evaluations": 0,
        "original_scores": copy.deepcopy(game.get("scores")),
        "candidate_internal_state_reconstructed": False,
        "consumer_instruction": "Replay the full ordered prefix through one persistent exact-source actor; compare expected actions before describing profiling as on-policy.",
        "timing_scope": "No policy or hosted timing was measured by this adapter.",
    }
    return inputs, receipt



def recover_record(document: dict[str, Any], evaluator: Any, tracer: Any,
                   engine: Any, engine_dir: Path, loader: Path,
                   engine_hashes: dict[str, str], *, game_index: int = 0,
                   expected_trace: str | None = None,
                   seat: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate the original document before the same recorded-action recovery.

    An optional seat selects a single-player observation view for analysis. It
    does not change any action or expose the environment seed to that player.
    Original candidate identity is retained separately in the returned receipt.
    """
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError(f"Expected original {SCHEMA} record")
    if (document.get("engine_ref") != evaluator.ENGINE_REF or
            document.get("engine_sha256") != engine_hashes):
        raise ValueError("Recorded interpreter source differs from the supplied original engine")
    # The original tracer uses specification defaults. A declared custom
    # configuration must not be silently presented as its recorded contract.
    if any(document.get(key) not in (None, {})
           for key in ("configuration_overrides", "configuration")):
        raise ValueError("Custom recorded configurations are not supported by the original tracer")
    games = document.get("games")
    if (not isinstance(games, list) or type(game_index) is not int or
            not 0 <= game_index < len(games)):
        raise ValueError("game-index is out of range")
    original = games[game_index]
    if not isinstance(original, dict):
        raise ValueError("Recorded game must be an object")
    validate_game(original)
    if expected_trace is not None and original["trace_sha256"] != expected_trace:
        raise ValueError("Record is not the requested original source trace")
    if seat is not None and (type(seat) is not int or seat not in (0, 1)):
        raise ValueError("Observation view seat must be 0 or 1")
    original_seat = original["candidate_seat"]
    view_seat = original_seat if seat is None else seat
    selected = copy.deepcopy(original)
    if view_seat != original_seat:
        selected["candidate_seat"] = view_seat
        selected["candidate"], selected["opponent"] = selected.get("opponent"), selected.get("candidate")
    inputs, receipt = recover_inputs(selected, evaluator, tracer, engine, engine_dir, loader)
    actor_seed = 20260907 + int(view_seat != original_seat)
    receipt.update({"original_candidate_seat": original_seat,
                    "view_is_original_candidate": view_seat == original_seat,
                    "candidate_actor_rng_seed": actor_seed,
                    "candidate_pythonhashseed": actor_seed})
    return inputs, receipt


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--game-index", type=int, default=0)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, default=ROOT / "cloud-eval/evaluate.py")
    parser.add_argument("--tracer", type=Path, default=ROOT / "cloud-widefield-lab/trace_apex_loss.py")
    parser.add_argument("--loader", type=Path, default=ROOT / "20260907-offline-agent/evaluate.py")
    parser.add_argument("--expected-trace")
    parser.add_argument("--output", type=Path, required=True, help="JSONL or deterministic JSONL.gz")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = args.record.read_bytes()
    document = json.loads(raw)
    if len({args.record.resolve(), args.output.resolve(), args.receipt.resolve()}) != 3:
        raise ValueError("Source record, output and receipt must be different paths")
    evaluator = load(args.evaluator.resolve(), "trace_inputs_evaluator")
    tracer = load(args.tracer.resolve(), "trace_inputs_tracer")
    engine, engine_hashes = evaluator.get_engine(args.engine_dir, args.loader)
    inputs, receipt = recover_record(document, evaluator, tracer, engine,
                                     args.engine_dir, args.loader, engine_hashes,
                                     game_index=args.game_index,
                                     expected_trace=args.expected_trace)
    receipt.update({"source_record_sha256": hashlib.sha256(raw).hexdigest(),
                    "engine_ref": evaluator.ENGINE_REF, "engine_sha256": engine_hashes,
                    "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "evaluator_sha256": evaluator.__trace_input_source_sha256__,
                    "tracer_sha256": tracer.__trace_input_source_sha256__})
    output = b"".join(canonical(row) + b"\n" for row in inputs)
    if args.output.suffix == ".gz":
        output = gzip.compress(output, mtime=0)
    receipt["output_file_sha256"] = hashlib.sha256(output).hexdigest()
    atomic_write(args.output, output)
    atomic_write(args.receipt, json.dumps(receipt, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
