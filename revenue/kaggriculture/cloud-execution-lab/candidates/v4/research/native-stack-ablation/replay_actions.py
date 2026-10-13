# SPDX-License-Identifier: Apache-2.0
"""Reconstruct a recorded native game without rerunning either agent.

Raw actions, including extra actor commands and capped market suffixes, are
preserved. Acceptance requires the original full trace hash AND final scores.
Optional JSONL snapshots contain two separately indexed owned observations;
never give the rival's private observation to a policy or shadow guard.
"""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from run_native_ablation import SOURCE_SHA256, digest, encoded, verify_package


MAX_TAPE_BYTES = 16 * 1024 * 1024


def read_tape(path: Path, game: dict[str, Any]) -> list[Any]:
    raw = path.read_bytes()
    if digest(raw) != game.get('tape_sha256'):
        raise ValueError('Compressed action tape does not match the recorded game')
    with gzip.open(path, 'rb') as handle:
        unpacked = handle.read(MAX_TAPE_BYTES + 1)
    if len(unpacked) > MAX_TAPE_BYTES:
        raise ValueError('Uncompressed tape exceeds the diagnostic size limit')
    actions = json.loads(unpacked)
    if not isinstance(actions, list) or len(actions) != 719:
        raise ValueError('A complete standard game needs exactly 719 action pairs')
    if any(not isinstance(pair, list) or len(pair) != 2
           or any(not isinstance(action, dict) for action in pair) for pair in actions):
        raise ValueError('Malformed raw two-player action tape')
    if digest(encoded(actions)) != game.get('action_sha256'):
        raise ValueError('Decoded action tape hash mismatch')
    return actions


def replay(root: Path, game: dict[str, Any], tape: Path,
           snapshots: Path | None = None) -> dict[str, Any]:
    verify_package(root)
    if game.get('status') != 'complete' or game.get('steps') != 719:
        raise ValueError('Failed or incomplete games cannot be replay-certified')
    if game.get('source_manifest_sha256') != SOURCE_SHA256:
        raise ValueError('Game names a different source manifest')
    if type(game.get('seed')) is not int or type(game.get('candidate_seat')) is not int or game['candidate_seat'] not in (0,1):
        raise ValueError('Explicit integer seed and physical candidate seat required')
    if snapshots is not None and (snapshots.exists() or snapshots.resolve().is_relative_to(root.resolve())):
        raise ValueError('Snapshots require a new path outside the read-only package')
    actions = read_tape(tape, game)
    evaluator = root / 'checks/reference/evaluator/evaluate.py'
    if digest(evaluator.read_bytes()) != game.get('evaluator_sha256'):
        raise ValueError('Evaluator pin mismatch')
    spec = importlib.util.spec_from_file_location('_native_replay_evaluator', evaluator)
    if spec is None or spec.loader is None:
        raise ValueError('Evaluator cannot be imported')
    ev = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ev
    spec.loader.exec_module(ev)
    engine, hashes = ev.get_engine(root/'checks/reference/engine', root/'checks/reference/evaluator/loader.py')
    if hashes != game.get('engine_sha256'):
        raise ValueError('Engine pin mismatch')
    cfg = ev.Struct({k: v.get('default') if isinstance(v,dict) else v
                     for k,v in engine.specification['configuration'].items()})
    cfg.seed = game['seed']
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    if cfg.get('seed') is not None:
        raise ValueError('Environment seed leaked into policy configuration')
    import hashlib
    trace = hashlib.sha256()
    temporary = None
    output = None
    try:
        if snapshots is not None:
            snapshots.parent.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.NamedTemporaryFile(dir=snapshots.parent, delete=False)
            output = gzip.GzipFile(filename='', mode='wb', fileobj=temporary, mtime=0)
        for step, pair in enumerate(actions):
            for seat in (0,1):
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
                state[seat].action = pair[seat]
            if output is not None:
                output.write(encoded({'game_id':game['id'], 'seed':game['seed'], 'step':step,
                    'configuration':cfg, 'observations':[s.observation for s in state], 'actions':pair}) + b'\n')
            engine.interpreter(state, env)
            bank = [float(state[0].observation.farms[i]['money']) for i in (0,1)]
            trace.update(encoded({'step':step, 'actions':pair, 'bank':bank}))
            if all(s.status == 'DONE' for s in state) and step != 718:
                raise ValueError('Unexpected early terminal transition')
        if not all(s.status == 'DONE' for s in state):
            raise ValueError('Replay did not terminate')
        trace.update(encoded([s.observation for s in state]))
        scores = [s.reward for s in state]
        if trace.hexdigest() != game.get('trace_sha256') or scores != game.get('scores'):
            raise ValueError('Full engine trace or terminal score mismatch')
        receipt = {'id':game['id'], 'seed':game['seed'], 'candidate_seat':game['candidate_seat'],
                   'replay_verified':True, 'callbacks':719, 'scores':scores,
                   'trace_sha256':trace.hexdigest(), 'action_sha256':game['action_sha256']}
        if output is not None:
            output.close(); output = None
            temporary.close()
            Path(temporary.name).replace(snapshots)
            receipt['snapshots_sha256'] = digest(snapshots.read_bytes())
        return receipt
    finally:
        if output is not None:
            output.close()
        if temporary is not None:
            temporary.close()
            Path(temporary.name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--game', required=True, type=Path)
    parser.add_argument('--tape', required=True, type=Path)
    parser.add_argument('--snapshots', type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.root.resolve(), json.loads(args.game.read_bytes()),
                            args.tape, args.snapshots), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
