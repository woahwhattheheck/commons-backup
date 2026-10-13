# SPDX-License-Identifier: Apache-2.0
"""Bounded pairwise joint assignment of complete pickup->service->delivery bundles.

Callsite: SpatialTempo.install.act, after per-actor transform / Arlene assembly
and before _pending/_selected capture. One continuation owner per accepted
swap. Explicit no-op with a reason code when no swap is accepted. Never calls
a producer or executes a game.
"""
from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from itertools import combinations
from pathlib import Path

from spatial_tempo import MOVES, distance, move, path, set_unit, unit

PICKUP_OPS = {'PICKUP', 'HARVEST', 'COLLECT_FERTILIZER'}
SERVICE_OPS = {'WATER', 'CARE', 'FEED', 'FERTILIZE', 'PLANT'}
DELIVERY_OPS = {'DROP', 'PLACE'}
WORK_OPS = PICKUP_OPS | SERVICE_OPS | DELIVERY_OPS
ILLEGAL_OPS = {'DIG', 'BUILD_COOP', 'BUILD_PASTURE'}
SHEDS = ((4, 4), (5, 4), (4, 5), (5, 5))
HIGH_VALUE = {'HARVEST', 'FERTILIZE', 'FEED', 'PLANT', 'COLLECT_FERTILIZER'}
CHECKPOINTS = (226, 360, 433)
MAX_BUNDLE = 24
MAX_PAIRS = 12

REASON_NO_ACTORS = 'no_pair_of_actors'
REASON_NO_BUNDLES = 'no_complete_bundles'
REASON_SINGLE_BUNDLE = 'single_complete_bundle'
REASON_CARGO_MASK = 'cargo_masked_by_position'
REASON_UNRESUMABLE = 'next_commitment_unresumable'
REASON_STOCK = 'stock_contention'
REASON_NO_TRAVEL = 'no_travel_saved'
REASON_COLLISION = 'tile_collision'
REASON_HIRE = 'hire_or_checkpoint_window'
REASON_INCOMPAT = 'no_compatible_pair'
REASON_DISABLED = 'disabled'
REASON_ACCEPTED = 'accepted_pairwise_swap'


def _cargo_key(inv):
    return tuple(sorted((str(k), int(v)) for k, v in (inv or {}).items() if int(v) > 0))


def _noop(reason, **extra):
    report = {'changed': False, 'reason': reason, 'pair': None, 'saved_travel': 0,
              'collision_trace': None, 'activation': False, 'duplicate_targets': 0,
              'noop_actions': 0, 'high_value': 0, 'stock_contention': 0,
              'runtime_seconds': extra.pop('runtime_seconds', 0.0)}
    report.update(extra)
    return report


def _positions(farm):
    return [tuple(farm['farmer']), *[tuple(p) for p in farm['hands']]]


def _inventories(private, n):
    invs = list(private.get('inventories') or [])
    while len(invs) < n:
        invs.append({})
    return [dict(row) for row in invs[:n]]


def _window(obs, selected, route, now):
    end = min((now // 24 + 1) * 24, 719)
    for t in CHECKPOINTS:
        if now < t < end:
            end = t
            break
    if any(a and a[0] == 'HIRE' for a in selected.get('market', []) or []):
        return None
    for t in range(now, end):
        row = selected if t == now else (route[t] if t < len(route) else None)
        if row is None:
            break
        if any(a and a[0] == 'HIRE' for a in row.get('market', []) or []):
            end = t
            break
    if end - now < 3:
        return None
    return end


def extract_bundle(obs, selected, route, worker, now, end, board):
    """Complete pickup -> service/delivery bundle for one actor, or None."""
    farm = obs['farms'][obs['player']]
    positions = _positions(farm)
    if worker >= len(positions):
        return None
    origin = positions[worker]
    invs = _inventories(obs['private'], len(positions))
    cargo = invs[worker]
    sequence = []
    tasks = []
    p = origin
    t = now
    while t < end and len(sequence) < MAX_BUNDLE:
        row = selected if t == now else (route[t] if t < len(route) else None)
        if row is None:
            break
        action = list(unit(row, worker) or ['PASS'])
        op = action[0] if action else 'PASS'
        if op in ILLEGAL_OPS:
            break
        if op not in MOVES and op != 'PASS' and op not in WORK_OPS:
            break
        if op in WORK_OPS:
            tasks.append((p, list(action)))
        sequence.append(list(action))
        p = move(p, action, board)
        t += 1
    if len(sequence) < 3 or not tasks:
        return None
    ops = [a[0] for _, a in tasks]
    if not any(op in PICKUP_OPS for op in ops):
        return None
    pickup_at = next(i for i, op in enumerate(ops) if op in PICKUP_OPS)
    if not any(op in SERVICE_OPS or op in DELIVERY_OPS for op in ops[pickup_at + 1:]):
        return None
    travel = sum(1 for a in sequence if a and a[0] in MOVES)
    return {
        'worker': worker,
        'origin': origin,
        'goal': p,
        'cargo': cargo,
        'cargo_key': _cargo_key(cargo),
        'sequence': sequence,
        'tasks': tasks,
        'end': t,
        'window': end - now,
        'travel': travel,
        'pickup_tiles': [pos for pos, a in tasks if a[0] in PICKUP_OPS],
        'service_tiles': [pos for pos, a in tasks if a[0] in SERVICE_OPS],
        'high_value': sum(1 for _, a in tasks if a[0] in HIGH_VALUE),
    }


def rebuild(origin, tasks, goal, board, window):
    """Path actor from origin through borrowed tasks, then rejoin goal."""
    trial = []
    cursor = origin
    for location, action in tasks:
        trial.extend(path(cursor, location))
        trial.append(list(action))
        cursor = location
    trial.extend(path(cursor, goal))
    if not trial or len(trial) > window:
        return None
    return trial


def collision_trace(origin_a, seq_a, origin_b, seq_b, board, now):
    pa, pb = origin_a, origin_b
    hits = []
    n = max(len(seq_a), len(seq_b))
    for k in range(n):
        aa = seq_a[k] if k < len(seq_a) else ['PASS']
        ab = seq_b[k] if k < len(seq_b) else ['PASS']
        pa = move(pa, aa, board)
        pb = move(pb, ab, board)
        if pa == pb and pa not in SHEDS:
            hits.append({'offset': k, 'step': now + k, 'tile': list(pa)})
            if len(hits) >= 4:
                break
    return hits


def _pair_reason(a, b):
    if a['origin'] == b['origin'] and a['cargo_key'] != b['cargo_key']:
        return REASON_CARGO_MASK
    if a['cargo_key'] != b['cargo_key']:
        return 'cargo_incompatible'
    shared = set(map(tuple, a['pickup_tiles'])) & set(map(tuple, b['pickup_tiles']))
    if shared:
        return REASON_STOCK
    return None


def _evaluate_swap(a, b, board, now):
    """Return (candidate_dict) or (None, reason)."""
    reason = _pair_reason(a, b)
    if reason:
        return None, reason
    window = min(a['window'], b['window'], MAX_BUNDLE)
    seq_a = rebuild(a['origin'], b['tasks'], a['goal'], board, window)
    if seq_a is None:
        return None, REASON_UNRESUMABLE
    seq_b = rebuild(b['origin'], a['tasks'], b['goal'], board, window)
    if seq_b is None:
        return None, REASON_UNRESUMABLE
    hits = collision_trace(a['origin'], seq_a, b['origin'], seq_b, board, now)
    if hits:
        return None, REASON_COLLISION
    new_travel = (sum(1 for x in seq_a if x and x[0] in MOVES)
                  + sum(1 for x in seq_b if x and x[0] in MOVES))
    old_travel = a['travel'] + b['travel']
    saved = old_travel - new_travel
    if saved <= 0:
        return None, REASON_NO_TRAVEL
    first_a = b['tasks'][0][0]
    first_b = a['tasks'][0][0]
    nearest = distance(a['origin'], first_a) + distance(b['origin'], first_b)
    original_near = distance(a['origin'], a['tasks'][0][0]) + distance(b['origin'], b['tasks'][0][0])
    if nearest >= original_near and saved <= 0:
        return None, REASON_NO_TRAVEL
    return {
        'i': a['worker'], 'j': b['worker'],
        'seq_i': seq_a, 'seq_j': seq_b,
        'bundle_i': a, 'bundle_j': b,
        'saved_travel': saved,
        'nearest': nearest,
        'collision_trace': [],
        'duplicate_targets': 0,
        'high_value': a['high_value'] + b['high_value'],
    }, None


def _ensure_stats(spatial):
    stats = getattr(spatial, 'joint_stats', None)
    if not isinstance(stats, dict):
        stats = {'activation_count': 0, 'travel_saved_total': 0,
                 'duplicate_targets_avoided': 0, 'noop_actions': 0,
                 'high_value_completed': 0, 'stock_contention': 0,
                 'runtime_seconds_total': 0.0, 'games': 0}
        spatial.joint_stats = stats
    return stats


def _log(record):
    path = os.environ.get('TITAN_JOINT_LOG') or '/tmp/v25/joint-stats.jsonl'
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, separators=(',', ':')) + '\n'
        with target.open('a', encoding='utf-8') as handle:
            handle.write(line)
    except OSError:
        return


def _apply(spatial, obs, selected, controller, now, board, choice):
    out = deepcopy(selected)
    route = controller.R[controller.cur]
    owner = min(choice['i'], choice['j'])
    applied = ((choice['i'], choice['seq_i'], choice['bundle_i'], choice['bundle_j']),
               (choice['j'], choice['seq_j'], choice['bundle_j'], choice['bundle_i']))
    noop_actions = 0
    for worker, seq, own, borrowed in applied:
        padded = [list(a) for a in seq]
        span = min(own['window'], MAX_BUNDLE)
        if len(padded) < span:
            padded.extend([['PASS']] * (span - len(padded)))
        for offset, action in enumerate(padded):
            t = now + offset
            if t >= len(route):
                break
            row = deepcopy(route[t])
            set_unit(row, worker, list(action))
            route[t] = row
        set_unit(out, worker, list(padded[0]))
        if padded[0] == ['PASS']:
            noop_actions += 1
        plan = {
            'kind': 'joint_swap',
            'step': now,
            'worker': worker,
            'end': now + len(padded),
            'route': controller.cur,
            'origin': own['origin'],
            'goal': own['goal'],
            'saved_travel': choice['saved_travel'],
            'owner': owner,
            'pair': (choice['i'], choice['j']),
            'original': [list(a) for a in own['sequence']],
            'replacement': padded,
            'extra': None,
            'collision_trace': list(choice['collision_trace']),
        }
        spatial.plans[worker] = plan
        spatial.active[worker] = plan['end']
        spatial.events.append({
            'kind': 'joint_swap', 'step': now, 'worker': worker, 'owner': owner,
            'pair': [choice['i'], choice['j']], 'saved_travel': choice['saved_travel'],
        })
    return out, noop_actions


def reconcile(spatial, observation, selected, controller):
    """Joint pairwise swap. Same selected object when no swap is accepted."""
    started = time.perf_counter()
    stats = _ensure_stats(spatial)
    now = int(observation['step'])
    if now == 0:
        stats['activation_count'] = 0
        stats['travel_saved_total'] = 0
        stats['duplicate_targets_avoided'] = 0
        stats['noop_actions'] = 0
        stats['high_value_completed'] = 0
        stats['stock_contention'] = 0
        stats['runtime_seconds_total'] = 0.0
    farm = observation['farms'][observation['player']]
    board = len(farm['tiles'])
    n = 1 + len(farm.get('hands') or [])
    runtime = lambda: round(time.perf_counter() - started, 6)

    def finish(report, result=None):
        report['runtime_seconds'] = runtime()
        stats['runtime_seconds_total'] = round(
            stats['runtime_seconds_total'] + report['runtime_seconds'], 6)
        report['activation_count'] = stats['activation_count']
        report['stats'] = {
            'activation_count': stats['activation_count'],
            'travel_saved_total': stats['travel_saved_total'],
            'duplicate_targets_avoided': stats['duplicate_targets_avoided'],
            'noop_actions': stats['noop_actions'],
            'high_value_completed': stats['high_value_completed'],
            'stock_contention': stats['stock_contention'],
            'runtime_seconds_total': stats['runtime_seconds_total'],
        }
        spatial.joint_report = report
        if report.get('changed') or now % 24 == 23:
            _log({'step': now, 'player': int(observation['player']), **report})
        return (selected if result is None else result), report

    if board != 10:
        return finish(_noop('board_unsupported'))
    if n < 2:
        return finish(_noop(REASON_NO_ACTORS))
    route = controller.R[controller.cur]
    end = _window(observation, selected, route, now)
    if end is None:
        return finish(_noop(REASON_HIRE))
    crop_worker = None
    intent = getattr(spatial, 'crop_intent', None)
    if isinstance(intent, dict):
        crop_worker = intent.get('worker')
    bundles = []
    for worker in range(n):
        if crop_worker is not None and worker == crop_worker:
            continue
        bundle = extract_bundle(observation, selected, route, worker, now, end, board)
        if bundle is not None:
            bundles.append(bundle)
    if len(bundles) == 0:
        return finish(_noop(REASON_NO_BUNDLES))
    if len(bundles) == 1:
        return finish(_noop(REASON_SINGLE_BUNDLE, complete_bundles=1))

    rejects = {}
    best = None
    stock_hits = 0
    for a, b in list(combinations(bundles, 2))[:MAX_PAIRS]:
        choice, reason = _evaluate_swap(a, b, board, now)
        if reason:
            rejects[reason] = rejects.get(reason, 0) + 1
            if reason == REASON_STOCK:
                stock_hits += 1
            continue
        key = (choice['saved_travel'], -choice['nearest'], -min(choice['i'], choice['j']))
        if best is None or key > best[0]:
            best = (key, choice)
    stats['stock_contention'] += stock_hits
    if best is None:
        order = (REASON_CARGO_MASK, REASON_UNRESUMABLE, REASON_STOCK, REASON_COLLISION,
                 REASON_NO_TRAVEL, REASON_INCOMPAT)
        reason = next((code for code in order if code in rejects), REASON_INCOMPAT)
        return finish(_noop(reason, rejects=rejects, complete_bundles=len(bundles),
                            stock_contention=stock_hits))

    choice = best[1]
    out, noop_actions = _apply(spatial, observation, selected, controller, now, board, choice)
    stats['activation_count'] += 1
    stats['travel_saved_total'] += choice['saved_travel']
    stats['noop_actions'] += noop_actions
    stats['high_value_completed'] += choice['high_value']
    trace = {
        'step': now,
        'owner': min(choice['i'], choice['j']),
        'pair': [choice['i'], choice['j']],
        'saved_travel': choice['saved_travel'],
        'cargo': [list(choice['bundle_i']['cargo_key']), list(choice['bundle_j']['cargo_key'])],
        'origins': [list(choice['bundle_i']['origin']), list(choice['bundle_j']['origin'])],
        'goals': [list(choice['bundle_i']['goal']), list(choice['bundle_j']['goal'])],
        'hits': choice['collision_trace'],
    }
    report = {
        'changed': True, 'reason': REASON_ACCEPTED, 'pair': [choice['i'], choice['j']],
        'saved_travel': choice['saved_travel'], 'collision_trace': trace,
        'activation': True, 'duplicate_targets': 0, 'noop_actions': noop_actions,
        'high_value': choice['high_value'], 'stock_contention': stock_hits,
        'owner': min(choice['i'], choice['j']),
        'rejects': rejects, 'complete_bundles': len(bundles),
    }
    return finish(report, out)
