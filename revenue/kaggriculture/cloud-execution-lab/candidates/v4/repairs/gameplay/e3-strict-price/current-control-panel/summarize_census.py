# SPDX-License-Identifier: Apache-2.0
"""Audit a declared current-TITAN trace panel; never infer fills or economic EV."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

STAGES = ('A', 'B', 'C', 'D', 'R')
PRODUCTS = ('WHEAT', 'FERTILIZER')


def sales(snapshot):
    """Count positive requested SELL units at original executable raw indices."""
    action = snapshot['action']
    raw = action.get('market', []) if isinstance(action, dict) else []
    prefix = raw[:snapshot['market_limit']] if isinstance(raw, list) else []
    if prefix != snapshot['executable_prefix']:
        raise ValueError('Snapshot prefix does not match raw slots')
    found = []
    for index, order in enumerate(prefix):
        if not isinstance(order, list) or len(order) < 3 or order[0] != 'SELL':
            continue
        if order[1] not in PRODUCTS:
            continue
        try:
            quantity = int(order[2])
        except (TypeError, ValueError):
            continue  # Exact official _parse_order rejection.
        if quantity > 0:
            found.append((index, order[1], quantity))
    return found


def read_json(path):
    return json.loads(path.read_text())


def audit(directory, controls=None):
    plan = read_json(directory / 'PLAN.json')
    execution = read_json(directory / 'GAMES.json')
    expected = {(seed, seat) for seed in plan['seeds'] for seat in plan['seats']}
    if len(expected) != len(plan['seeds']) * len(plan['seats']):
        raise ValueError('Duplicate plan cell')
    if execution['plan_sha256'] != hashlib.sha256((directory / 'PLAN.json').read_bytes()).hexdigest():
        raise ValueError('Plan hash mismatch')
    if execution['source_sha256'] != hashlib.sha256((directory / 'SOURCE.json').read_bytes()).hexdigest():
        raise ValueError('Source manifest hash mismatch')
    games = {}
    for game in execution['games']:
        key = (game['seed'], game['candidate_seat'])
        if key in games:
            raise ValueError('Duplicate game cell')
        games[key] = game
    if set(games) != expected:
        raise ValueError('Incomplete or unexpected game grid')
    if any(g['status'] != 'complete' or g['steps'] != plan['episode_steps'] - 1 for g in games.values()):
        raise ValueError('Incomplete full-game execution')

    counts = {stage: {p: {'rows': 0, 'requested_units': 0} for p in PRODUCTS} for stage in STAGES}
    transitions = {left + '->' + right:
        {p: {'matched_callbacks': 0, 'net_requested_units_removed': 0,
             'positive_removals': 0, 'positive_additions': 0} for p in PRODUCTS}
        for left, right in zip(STAGES, STAGES[1:])}
    coverage = Counter()
    statuses = Counter()
    fallbacks = Counter()
    final_steps = set()
    rows = []
    capture_errors = []
    raw_hashes = {}
    for (seed, seat), game in sorted(games.items()):
        path = directory / (str(seed) + '-' + str(seat) + '.jsonl')
        data = path.read_bytes()
        raw_hashes[path.name] = hashlib.sha256(data).hexdigest()
        callbacks = [json.loads(line) for line in data.splitlines()]
        if len(callbacks) != game['steps']:
            raise ValueError('Trace callback count mismatch')
        for step, row in enumerate(callbacks):
            if row['step'] != step or row['seat'] != seat:
                raise ValueError('Trace callback position mismatch')
            coverage['callbacks'] += 1
            capture_errors.extend(row['capture_errors'])
            snapshots = dict(row['stages'], R=row['returned'])
            unknown = set(snapshots) - set(STAGES)
            if unknown:
                raise ValueError('Unknown stages: ' + repr(unknown))
            if 'D' in snapshots and snapshots['D']['action'] != snapshots['R']['action']:
                capture_errors.append('D/returned action mismatch')
            final_diagnostics = snapshots['R']['diagnostics']
            statuses[final_diagnostics.get('status', 'unreported')] += 1
            if final_diagnostics.get('status') == 'deadline_fallback':
                fallbacks[final_diagnostics.get('fallback_stage', 'unreported')] += 1
            units = {}
            for stage, snapshot in snapshots.items():
                coverage[stage] += 1
                values = sales(snapshot)
                units[stage] = Counter()
                for index, product, quantity in values:
                    counts[stage][product]['rows'] += 1
                    counts[stage][product]['requested_units'] += quantity
                    units[stage][product] += quantity
                    if stage == 'R':
                        final_steps.add((seed, seat, step))
                    rows.append({'seed': seed, 'seat': seat, 'step': step,
                                 'day': row['day'], 'hour': row['hour'], 'stage': stage,
                                 'product': product, 'quantity_requested': quantity,
                                 'market_index': index,
                                 'executable_prefix': snapshot['executable_prefix'],
                                 'diagnostics': snapshot['diagnostics']})
            for left, right in zip(STAGES, STAGES[1:]):
                if left not in units or right not in units:
                    continue  # A bypass is missing-stage coverage, never a zero.
                for product in PRODUCTS:
                    delta = units[left][product] - units[right][product]
                    record = transitions[left + '->' + right][product]
                    record['matched_callbacks'] += 1
                    record['net_requested_units_removed'] += delta
                    record['positive_removals'] += max(0, delta)
                    record['positive_additions'] += max(0, -delta)
    comparison = {'run': False, 'all_identical': False}
    if controls is not None:
        control = read_json(controls / 'GAMES.json')
        if control['plan_sha256'] != execution['plan_sha256'] or control['source_sha256'] != execution['source_sha256']:
            raise ValueError('Control plan/source differs')
        cg = {(g['seed'], g['candidate_seat']): g for g in control['games']}
        if len(cg) != len(control['games']) or set(cg) != expected:
            raise ValueError('Control grid mismatch')
        comparisons = []
        for key in sorted(expected):
            a, b = games[key], cg[key]
            same = (b['status'] == 'complete' and a['steps'] == b['steps']
                    and a['scores'] == b['scores'] and a['trace_sha256'] == b['trace_sha256'])
            comparisons.append({'seed': key[0], 'seat': key[1], 'identical': same,
                                'observed_trace': a['trace_sha256'],
                                'control_trace': b['trace_sha256']})
        comparison = {'run': True, 'all_identical': all(r['identical'] for r in comparisons),
                      'identical_cells': sum(r['identical'] for r in comparisons), 'cells': comparisons}
    final_count = sum(counts['R'][p]['rows'] for p in PRODUCTS)
    valid = not capture_errors and coverage['R'] == len(expected) * (plan['episode_steps'] - 1)
    identity = comparison['all_identical']
    verdict = ('RESIDUAL_PRESENT' if final_count else 'NO_PORT_ON_THIS_PANEL') if valid and identity else 'INCONCLUSIVE'
    summary = {'schema': 'titan.e3.operating-sell-census.v1', 'verdict': verdict,
               'planned_cells': len(expected), 'completed_cells': len(games),
               'coverage': dict(coverage), 'status_counts': dict(statuses),
               'fallback_stage_counts': dict(fallbacks), 'stage_counts': counts,
               'matched_stage_transitions': transitions,
               'final_residual_rows': final_count, 'final_residual_unique_steps': len(final_steps),
               'capture_errors': capture_errors, 'control_comparison': comparison,
               'trace_files_sha256': raw_hashes,
               'units_meaning': 'Positive requested units in the executable raw prefix, NOT successful fills.',
               'inference_limit': 'Residual presence is reachability only, not harm, economics, E3-port authority or promotion. NO_PORT is scoped to this exact source/panel.'}
    return summary, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--controls', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary, rows = audit(args.directory, args.controls)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'SUMMARY.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    with (args.output / 'SELL-ROWS.jsonl').open('w') as f:
        for row in rows:
            f.write(json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n')
    print(json.dumps({k: summary[k] for k in ('verdict', 'coverage', 'stage_counts', 'final_residual_rows', 'final_residual_unique_steps')}))
    return int(summary['verdict'] == 'INCONCLUSIVE')


if __name__ == '__main__':
    raise SystemExit(main())
