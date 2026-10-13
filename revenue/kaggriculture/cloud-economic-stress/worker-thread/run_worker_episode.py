#!/usr/bin/env python3
"""Run an extracted TITAN raw entrypoint entirely in one non-main worker."""
import argparse
import ast
import copy
import hashlib
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Callable, Dict, Tuple
from urllib.parse import urlparse


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact_file_agent(root):
    """Execute only the packaged official local-file loader definitions."""
    namespace = dict(
        os=os, sys=sys, StringIO=StringIO, Any=Any, Callable=Callable,
        Dict=Dict, Tuple=Tuple, urlparse=urlparse, InvalidArgument=ValueError,
        NotFound=FileNotFoundError,
    )
    sources = [
        (root / 'checks/reference/engine/utils.py', {'read_file'}),
        (root / 'checks/reference/evaluator/official_agent.py',
         {'is_url', 'get_last_callable', 'build_agent'}),
    ]
    for source, names in sources:
        tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
        nodes = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
        if {node.name for node in nodes} != names:
            raise ValueError(f'missing official definitions in {source}')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'),
             namespace)
    agent, _ = namespace['build_agent'](str(root / 'main.py'), {}, 'kaggriculture')
    return agent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive-root', required=True, type=Path)
    parser.add_argument('--engine-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seed', default=9922999, type=int)
    parser.add_argument('--outer-timeout', default=1.0, type=float)
    args = parser.parse_args()
    root = args.archive_root.resolve()
    evaluator = load(root / 'checks/reference/evaluator/evaluate.py',
                     'econ_worker_evaluator')
    engine, engine_hashes = evaluator.get_engine(
        args.engine_dir.resolve(), root / 'checks/reference/evaluator/loader.py')
    cfg = evaluator.Struct({
        key: value.get('default') if isinstance(value, dict) else value
        for key, value in engine.specification['configuration'].items()
    })
    cfg.seed = args.seed
    env = evaluator.Struct(configuration=cfg, done=False, info={})
    state = [evaluator.Struct(observation=evaluator.Struct(), action={},
                              status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    if cfg.get('seed') is not None:
        raise ValueError('engine seed leaked to agent configuration')

    candidate = exact_file_agent(root)
    main_id = threading.main_thread().ident
    calls, turns, daily = [], [], []
    trace = hashlib.sha256()
    action_trace = hashlib.sha256()
    failure = None

    def invoke(observation, configuration):
        started = time.perf_counter()
        action = candidate(observation, configuration)
        return action, time.perf_counter() - started, threading.get_ident()

    episode_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=1,
                            thread_name_prefix='official-agent-worker') as pool:
        for step in range(int(cfg.episodeSteps)):
            for seat in (0, 1):
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
            outer_started = time.perf_counter()
            future = pool.submit(invoke, copy.deepcopy(state[0].observation),
                                 copy.deepcopy(cfg))
            try:
                own_action, inner_seconds, worker_id = future.result(
                    timeout=args.outer_timeout)
            except TimeoutError:
                failure = {'step': step, 'type': 'OuterTimeout'}
                break
            except BaseException as error:
                failure = {'step': step, 'type': type(error).__name__,
                           'message': str(error)}
                break
            outer_seconds = time.perf_counter() - outer_started
            if worker_id == main_id:
                failure = {'step': step, 'type': 'ProtocolError',
                           'message': 'candidate ran on the main thread'}
                break
            rival_action = engine.starter_agent(copy.deepcopy(state[1].observation))
            actions = [own_action, rival_action]
            state[0].action, state[1].action = actions
            engine.interpreter(state, env)
            bank = [float(state[0].observation.farms[index]['money'])
                    for index in range(2)]
            calls.append({'step': step, 'call_seconds': inner_seconds,
                          'outer_seconds': outer_seconds,
                          'worker_thread_id': worker_id})
            turns.append({'step': step, 'actions': actions, 'bank': bank})
            encoded = evaluator.encoded({'step': step, 'actions': actions,
                                         'bank': bank})
            trace.update(encoded)
            action_trace.update(json.dumps(
                own_action, sort_keys=True, separators=(',', ':')).encode() + b'\n')
            done = all(cell.status == 'DONE' for cell in state)
            if (step + 1) % int(cfg.turnsPerDay) == 0 or done:
                daily.append({'step': step, 'bank': bank})
            if done:
                env.done = True
                break

    trace.update(evaluator.encoded([cell.observation for cell in state]))
    complete = failure is None and all(cell.status == 'DONE' for cell in state)
    result = {
        'scope': 'all candidate calls in one persistent non-main worker thread',
        'python': sys.version,
        'raw_entrypoint': str(root / 'main.py'),
        'raw_loader_sha256': hashlib.sha256((
            root / 'checks/reference/evaluator/official_agent.py').read_bytes()).hexdigest(),
        'source_manifest_sha256': hashlib.sha256((
            root / 'SOURCE.json').read_bytes()).hexdigest(),
        'engine_ref': evaluator.ENGINE_REF,
        'engine_sha256': engine_hashes,
        'seed': args.seed,
        'candidate_seat': 0,
        'opponent': 'official_starter',
        'status': 'complete' if complete else 'failed',
        'failure': failure,
        'steps': len(calls),
        'scores': [cell.reward for cell in state] if complete else None,
        'worker_thread_ids': sorted({row['worker_thread_id'] for row in calls}),
        'main_thread_id': main_id,
        'max_call_seconds': max((row['call_seconds'] for row in calls), default=None),
        'mean_call_seconds': statistics.mean(row['call_seconds'] for row in calls)
        if calls else None,
        'max_outer_seconds': max((row['outer_seconds'] for row in calls), default=None),
        'mean_outer_seconds': statistics.mean(row['outer_seconds'] for row in calls)
        if calls else None,
        'episode_wall_seconds': time.perf_counter() - episode_started,
        'candidate_action_sha256': action_trace.hexdigest(),
        'daily_bank': daily,
        'calls': calls,
        'turns': turns,
        'trace_sha256': trace.hexdigest(),
    }
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('calls', 'turns')}, indent=2))
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
