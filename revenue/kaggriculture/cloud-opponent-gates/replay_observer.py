"""Feed reconstructed original observations into the shared COK observer.

Both engine actions always come from the immutable saved traces. The observer's
returned action is compared but never controls the replay. No new game, seed
selection, outcome label, opponent policy call or held evaluation is created.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import read_evidence


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def replay_case(data, case, evaluator, engine, observer_type, source, pack):
    seat = case["candidate_seat"]
    original = next(g for g in data["original_games"]["games"] if g["candidate_seat"] == seat and g["seed"] == case["seed"])
    actions = [read_evidence.actions(data, case, position) for position in (0, 1)]
    cfg = evaluator.Struct({key: value.get("default") if isinstance(value, dict) else value
                            for key, value in engine.specification["configuration"].items()})
    cfg.seed = case["seed"]
    env = evaluator.Struct(configuration=cfg, done=False, info={})
    state = [evaluator.Struct(observation=evaluator.Struct(), action={}, status="ACTIVE", reward=0) for _ in (0, 1)]
    engine.interpreter(state, env)
    if cfg.get("seed") is not None:
        raise ValueError("Replay seed must not enter the policy observation/configuration")
    observer = observer_type(source, pack)
    frames = {frame["step"]: frame for frame in case["frames"]}
    trace = hashlib.sha256()
    records = []
    mismatches, frame_checks = [], 0
    for step in range(len(actions[seat])):
        for position in (0, 1):
            state[position].observation.step = step
            state[position].observation.remainingOverageTime = 0
        obs = state[seat].observation
        if step in frames:
            if read_evidence.encoded(obs) != read_evidence.encoded(frames[step]["observation"]):
                raise ValueError(f"Original observation checkpoint differs at {step}")
            if read_evidence.encoded(cfg) != read_evidence.encoded(frames[step]["configuration"]):
                raise ValueError(f"Original configuration checkpoint differs at {step}")
            frame_checks += 1
        returned = observer.act(copy.deepcopy(obs), copy.deepcopy(cfg))
        expected = actions[seat][step]["action"]
        match = returned == expected
        if not match:
            mismatches.append(step)
        record = copy.deepcopy(observer.last_record)
        record.update(match_id=f"saved-{case['seed']}-cok-{seat}", expected_action_matches=match)
        records.append(record)
        pair = [actions[position][step]["action"] for position in (0, 1)]
        for position in (0, 1):
            state[position].action = copy.deepcopy(pair[position])
        engine.interpreter(state, env)
        bank = [float(state[0].observation.farms[i]["money"]) for i in (0, 1)]
        trace.update(read_evidence.encoded({"step": step, "actions": pair, "bank": bank}))
        if all(actor.status == "DONE" for actor in state):
            env.done = True
            if step != len(actions[seat]) - 1:
                raise ValueError("Saved trace extends beyond the actual DONE boundary")
            break
    if not env.done:
        raise ValueError("Saved trace does not reach DONE")
    trace.update(read_evidence.encoded([actor.observation for actor in state]))
    if trace.hexdigest() != original["trace_sha256"]:
        raise ValueError("Reconstructed complete engine trace differs from original")
    scores = [actor.reward for actor in state]
    if scores != original["scores"]:
        raise ValueError("Reconstructed terminal result differs from original")
    return {"seed": case["seed"], "candidate_seat": seat, "replayed_decisions": len(records),
            "original_checkpoints_matched": frame_checks, "action_mismatch_steps": mismatches,
            "original_scores": scores, "original_trace_sha256": trace.hexdigest(),
            "records": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "pack", "engine", "evaluator", "observer", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    data = read_evidence.read()
    evaluator = load(args.evaluator.resolve(strict=True), "iris_replay_evaluator")
    engine, hashes = evaluator.get_engine(args.engine.resolve(strict=True))
    observe = load(args.observer.resolve(strict=True), "iris_shared_observer")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for case in data["cases"]:
        result = replay_case(data, case, evaluator, engine, observe.CokObserver, args.source, args.pack)
        records = result.pop("records")
        filename = f"telemetry-cok-{case['candidate_seat']}.jsonl"
        payload = b"".join(read_evidence.encoded(row) + b"\n" for row in records)
        (output / filename).write_bytes(payload)
        result["telemetry_file"] = filename
        result["telemetry_sha256"] = hashlib.sha256(payload).hexdigest()
        result["activation"] = observe.summarize(records)
        results.append(result)
    report = {"schema": "titan.cok-observer-consumer.v1", "new_scored_games": 0,
              "engine_ref": evaluator.ENGINE_REF, "engine_sha256": hashes,
              "observer_sha256": hashlib.sha256(args.observer.read_bytes()).hexdigest(),
              "consumer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "results": results}
    (output / "CONSUMER.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(any(result["action_mismatch_steps"] or any(actor["telemetry_errors"] for actor in result["activation"]["actors"]) for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
