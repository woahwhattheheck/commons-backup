# SPDX-License-Identifier: Apache-2.0
"""Offline source-pinned imports and full official-interpreter replay fixtures."""
from __future__ import annotations
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / 'SOURCES.json').read_text())


def identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {'bytes': len(data),
            'git_blob': hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(),
            'sha256': hashlib.sha256(data).hexdigest()}


def load_file(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f'Cannot import {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_runtime(root: Path) -> dict[str, Any]:
    root = root.resolve()
    source = root / 'scheduler.py'
    actual = identity(source)
    named = {node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
             for node in ast.parse(source.read_text()).body
             if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
    for name, expected in PINS['scheduler_ast_nodes'].items():
        if named.get(name) != expected:
            raise ValueError(f'Scheduler mechanism changed: {name}; revalidate explicitly')
    statements = {ast.dump(n, include_attributes=False) for n in ast.parse(source.read_text()).body}
    if not set(PINS['scheduler_required_module_bindings']).issubset(statements):
        raise ValueError('Scheduler module bindings changed; revalidate explicitly')
    for name, expected in PINS['dependencies'].items():
        if identity(root/name) != expected:
            raise ValueError(f'Scheduler dependency changed: {name}')
    return {'scheduler': actual, 'exact_predecessor_file': actual == PINS['scheduler_file'],
            'all_market_mechanism_ast_nodes_match': True,
            'dependencies': PINS['dependencies']}


def load_scheduler(root: Path) -> tuple[Any, dict[str, Any]]:
    root = root.resolve()
    receipt = validate_runtime(root)
    for name in ('mechanics', 'observed_clone'):
        prior = sys.modules.get(name)
        if prior is not None and Path(getattr(prior, '__file__', '')).resolve() != root/(name+'.py'):
            raise ValueError(f'Wrong-root cached module: {name}; run in a fresh process')
    sys.path.insert(0, str(root))
    try:
        module = load_file(root/'scheduler.py', '_titan_market_response_scheduler')
    finally:
        sys.path.pop(0)
    return module, receipt


def load_engine(root: Path) -> tuple[Any, Any, dict[str, Any]]:
    root = root.resolve()
    choices = [root/'checks/reference', root/'reference']
    ref = next((p for p in choices if (p/'engine/kaggriculture.py').is_file()), None)
    if ref is None:
        raise ValueError('Missing preserved official engine; no network fallback')
    for name, expected in PINS['official_engine'].items():
        if identity(ref/'engine'/name) != expected:
            raise ValueError(f'Official engine changed: {name}')
    for name, expected in PINS['evaluator'].items():
        if identity(ref/'evaluator'/name) != expected:
            raise ValueError(f'Evaluator changed: {name}')
    evaluator = load_file(ref/'evaluator/evaluate.py', '_titan_market_response_evaluator')
    engine, hashes = evaluator.get_engine(ref/'engine', ref/'evaluator/loader.py')
    return engine, evaluator.Struct, hashes


def replay_plan(engine: Any, Struct: Any, spec: dict[str, Any], plan: Any,
                stream: Any, seat: int, *, realize_carry: bool = True) -> dict[str, Any]:
    """Full interpreter, fixed own row1 behind a real BUY_SEED barrier.

    Both counterfactuals buy one WHEAT seed each callback from ample initial cash;
    identical costs/seeds cancel in delta. No no-op row-compaction assumption is
    needed. Rival row0/1/2 realizes before/paired/after against the same own row1.
    Input states are synthetic; the caller must not label them observed games.
    """
    if type(seat) is not int or seat not in (0, 1):
        raise ValueError('seat must be 0 or 1')
    now, end, item = spec['now'], spec['dates'][-1], spec['item']
    cfg = Struct({k: v.get('default') if isinstance(v, dict) else v
                  for k, v in engine.specification['configuration'].items()})
    cfg.update(spec.get('config', {}))
    cfg.weedSpawnChance = 0
    # Use an actual future episode end so terminal reward shaping does not
    # contaminate isolated cash/market measurements of a finite planning window.
    cfg.episodeSteps = max(int(cfg.get('episodeSteps', 720)), end + 4)
    farms = [engine._new_farm(10, 10000), engine._new_farm(10, 10000)]
    market = engine._new_market(spec.get('params'))
    market['inventory'][item] = spec['inventory']
    engine._refresh_prices(market)
    town = {'unlocked_shops': list(spec['shops'])}
    env = Struct(configuration=cfg, done=False, info={'seed': 1789179643})
    states = []
    for p in (0, 1):
        private = engine._new_private()
        private['shed'][item] = spec['quantity'] if p == seat else spec['rival_quantity']
        states.append(Struct(observation=Struct(player=p, step=now, day=now//24,
                     hour=now%24, farms=farms, market=market, town=town, private=private),
                     action={}, status='ACTIVE', reward=0))
    own_plan = dict(plan)
    rival_plan = {t: (n, a) for t, n, a in stream}
    rem = spec['quantity'] - sum(own_plan.values())
    terminal = end == spec.get('last', 718)
    stop = end + 1 if realize_carry and not terminal else end
    timeline = []
    for step in range(now, stop + 1):
        own = own_plan.get(step, 0) if step <= end else rem
        rival, alignment = rival_plan.get(step, (0, 'paired'))
        if alignment not in ('before', 'paired', 'after'):
            raise ValueError('invalid alignment')
        own_orders = [['BUY_SEED', 'WHEAT', 1], ['SELL', item, own]]
        rival_row = {'before': 0, 'paired': 1, 'after': 2}[alignment]
        rival_orders = [[] for _ in range(rival_row)] + [['SELL', item, rival]]
        for p in (0, 1):
            states[p].observation.step = step
            states[p].action = {'farmer': ['PASS'], 'hands': [],
                                'market': copy.deepcopy(own_orders if p == seat else rival_orders)}
        engine.interpreter(states, env)
        timeline.append({'step': step, 'own_cash': farms[seat]['money'],
                         'rival_cash': farms[1-seat]['money'],
                         'inventory': market['inventory'][item],
                         'own_orders': own_orders, 'rival_orders': rival_orders})
    return {'own_cash': farms[seat]['money'], 'rival_cash': farms[1-seat]['money'],
            'margin': farms[seat]['money'] - farms[1-seat]['money'],
            'market': copy.deepcopy(market),
            'privates': [copy.deepcopy(s.observation.private) for s in states],
            'timeline': timeline,
            'carry_realized_at': end + 1 if stop > end else None}


def load_selected_core(root: Path) -> tuple[Any, dict[str, Any]]:
    """Current frozen consumer's optimizer, not the standalone scheduler copy."""
    root = root.resolve()
    receipt = validate_runtime(root)
    if identity(root/'selected_sell_core.py') != PINS['selected_sell_core']:
        raise ValueError('Frozen optimizer changed: selected_sell_core.py; revalidate explicitly')
    prior = sys.modules.get('mechanics')
    if prior is not None and Path(getattr(prior, '__file__', '')).resolve() != root/'mechanics.py':
        raise ValueError('Wrong-root cached mechanics; run in a fresh process')
    sys.path.insert(0, str(root))
    try:
        module = load_file(root/'selected_sell_core.py', '_titan_market_response_selected_core')
    finally:
        sys.path.pop(0)
    receipt['selected_sell_core'] = identity(root/'selected_sell_core.py')
    receipt['consumer'] = 'frozen'
    receipt['frozen_caller_source_matches'] = identity(root/'frozen_selected.py') == PINS['frozen_caller']
    receipt['full_frozen_transform_executed'] = False
    return module, receipt
