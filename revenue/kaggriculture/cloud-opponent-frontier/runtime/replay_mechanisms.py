"""Replay reviewed Barnyard source against recorded observations, without new games.

This diagnoses branch activation on an observed trajectory, not a causal
counterfactual. It imports the explicitly supplied, already reviewed policy.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

HOOKS = ('_preempt_shift', '_repay_shift', '_weed_repair_action', '_rank_sell_slots')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def observe_hooks(module, hooks=HOOKS):
    originals = {}
    records = {name: {'calls': 0, 'changed': [], 'errors': []} for name in hooks}
    try:
        for name in hooks:
            original = getattr(module, name)
            originals[name] = original
            def observed(*args, _fn=original, _name=name):
                record = records[_name]
                record['calls'] += 1
                before = copy.deepcopy(args[1])
                step = args[0].get('step')
                try:
                    result = _fn(*args)
                except Exception as exc:
                    record['errors'].append({'step': step, 'type': type(exc).__name__})
                    raise
                if before != result:
                    record['changed'].append({'step': step, 'before': before,
                                               'after': copy.deepcopy(result)})
                return result
            setattr(module, name, observed)
        yield records
    finally:
        for name, original in originals.items():
            setattr(module, name, original)


def replay_rows(module, rows, seat: int) -> dict:
    if seat not in (0, 1):
        raise ValueError('seat must be 0 or 1')
    count = matched = 0
    mismatches = []
    units, orders = Counter(), Counter()
    max_hands = 0
    with observe_hooks(module) as hooks:
        for index, row in enumerate(rows):
            state = row['before'][seat]
            obs = state['observation']
            if not obs and index == 0:  # Interpreter initialization, no agent call.
                continue
            if 'private' not in obs or obs.get('player') != seat:
                raise ValueError(f'Missing or wrong-seat observation at row {index}')
            action = state['action']
            actual = module.agent(copy.deepcopy(obs))
            count += 1
            if actual == action:
                matched += 1
            else:
                mismatches.append({'step': obs.get('step'), 'observed': action, 'replayed': actual})
            max_hands = max(max_hands, len(obs['farms'][seat]['hands']))
            for unit in [action.get('farmer', []), *action.get('hands', [])]:
                if unit:
                    units[unit[0]] += 1
            for order in action.get('market', []):
                if order:
                    orders[order[0]] += 1
    if count == 0:
        raise ValueError('No observed agent calls; an empty replay cannot prove parity')
    return {'observations': count, 'exact_action_matches': matched,
            'all_actions_match': matched == count, 'mismatches': mismatches,
            'unit_action_requests': dict(units), 'market_order_requests': dict(orders),
            'max_observed_hands': max_hands, 'hooks': hooks,
            'limits': 'Observed-trajectory replay only. Request counts are not successful yield counts.'}


def replay_trace(policy: Path, trace: Path, seat: int) -> dict:
    spec = importlib.util.spec_from_file_location('t07_reviewed_replay_policy', policy)
    if spec is None or spec.loader is None:
        raise ValueError(f'Cannot load reviewed source: {policy}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with gzip.open(trace, 'rt', encoding='utf-8') as stream:
        report = replay_rows(module, (json.loads(line) for line in stream), seat)
    report.update(schema='titan.t07.mechanism-replay.v1', seat=seat,
                  policy_sha256=sha256(policy), trace_sha256=sha256(trace))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument(
        '--seat',
        type=int,
        choices=(0, 1),
        required=True,
        help='Player position whose recorded actions are replayed (0 or 1).',
    )
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = replay_trace(args.policy.resolve(strict=True), args.trace.resolve(strict=True), args.seat)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + '.tmp')
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(args.output)
    print(json.dumps({'observations': report['observations'], 'exact_action_matches': report['exact_action_matches'],
                      'changes': {name: len(value['changed']) for name, value in report['hooks'].items()}}))
    if not report['all_actions_match']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
