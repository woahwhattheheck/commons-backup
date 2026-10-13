#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproduce the four discriminating early-capital execution cases."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DEFAULT_LAB = HERE.parents[1]
PREDECESSOR_SHA256 = (
    '13dc90de8cd3abbb54a8acba066b9e56f6b50aefb34993d3544bac6e4576f4f6'
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _farm(money=3000, unlocked=('NW',)):
    return {
        'money': money,
        'unlocked_quadrants': list(unlocked),
        'hires_today': 0,
        'tiles': [[None] * 10 for _ in range(10)],
        'farmer': [4, 4],
        'hands': [],
    }


def _observation(mechanics, *, money=900, shed=None):
    own = _farm(money)
    return {
        'step': 150,
        'day': 6,
        'hour': 6,
        'player': 0,
        'farms': [own, _farm()],
        'private': {
            'shed': dict(shed or {}),
            'inventories': [{}],
            'seeds': {},
        },
        'market': {
            'inventory': {
                item: 10000 for item in mechanics.PRODUCTS
            },
            'prices': {},
            'params': None,
        },
    }


def _route():
    return [
        {'farmer': ['PASS'], 'hands': [], 'market': []}
        for _ in range(720)
    ]


def _stable_ids(original, reordered):
    used = set()
    result = []
    for order in reordered:
        for index, source in enumerate(original):
            if index not in used and source == order:
                used.add(index)
                result.append((index, order))
                break
        else:
            raise AssertionError(f'order identity changed: {order!r}')
    return result


def _executed(payload):
    result = {}
    for receipt in payload['receipts']:
        op = receipt['op']
        if op in ('PASS', 'EMPTY'):
            continue
        result[f"{op}@{receipt['index']}"] = receipt['executed']
    return result


def reproduce(lab):
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))

    import mechanics
    import kestrel_early_capital as candidate

    predecessor_path = lab / 'early_capital.py'
    predecessor_bytes = predecessor_path.read_bytes()
    predecessor_sha = hashlib.sha256(predecessor_bytes).hexdigest()
    if predecessor_sha != PREDECESSOR_SHA256:
        raise RuntimeError(
            'predecessor source moved: '
            f'expected {PREDECESSOR_SHA256}, got {predecessor_sha}'
        )
    predecessor = _load('_kestrel_predecessor', predecessor_path)
    cfg = {
        'episodeSteps': 720,
        'turnsPerDay': 24,
        'farmHandCostMult': 1,
        'maxMarketOrdersPerTurn': 10,
        'shedCapacity': 100,
    }
    cases = {
        'inactive_tail_activation': (
            _observation(mechanics, shed={'WOOL': 1}),
            {
                'farmer': ['PASS'],
                'hands': [],
                'market': (
                    [['PASS'] for _ in range(10)]
                    + [['BUY_LAND'], ['SELL', 'WOOL', 1]]
                ),
            },
        ),
        'buy_then_sell_dependency': (
            _observation(mechanics, money=1000),
            {
                'farmer': ['PASS'],
                'hands': [],
                'market': [
                    ['BUY_PRODUCT', 'WHEAT', 1],
                    ['BUY_LAND'],
                    ['SELL', 'WHEAT', 1],
                ],
            },
        ),
        'capital_steals_product_cash': (
            _observation(mechanics, money=1000),
            {
                'farmer': ['PASS'],
                'hands': [],
                'market': [
                    ['BUY_PRODUCT', 'WHEAT', 1],
                    ['BUY_LAND'],
                ],
            },
        ),
        'sell_funded_free_gain': (
            _observation(
                mechanics,
                money=900,
                shed={'WOOL': 1},
            ),
            {
                'farmer': ['PASS'],
                'hands': [],
                'market': [
                    ['BUY_LAND'],
                    ['SELL', 'WOOL', 1],
                ],
            },
        ),
    }

    actual = {}
    for name, (observation, selected) in cases.items():
        old_action, old_report = predecessor.order_early_capital(
            mechanics,
            deepcopy(observation),
            cfg,
            deepcopy(selected),
            _route(),
        )
        new_action, new_report = candidate.order_early_capital(
            mechanics,
            deepcopy(observation),
            cfg,
            deepcopy(selected),
            _route(),
        )
        farm, private, market, _ = candidate._post_unit_state(
            mechanics,
            observation,
            cfg,
            selected,
            None,
        )
        base_state = (farm, private, market)
        original_entries = list(enumerate(selected['market'][:10]))
        old_entries = _stable_ids(
            selected['market'],
            old_action['market'],
        )[:10]
        new_entries = _stable_ids(
            selected['market'],
            new_action['market'],
        )[:10]
        original_payload, _ = candidate._simulate_market(
            mechanics, base_state, original_entries, cfg,
        )
        old_payload, _ = candidate._simulate_market(
            mechanics, base_state, old_entries, cfg,
        )
        new_payload, _ = candidate._simulate_market(
            mechanics, base_state, new_entries, cfg,
        )
        actual[name] = {
            'predecessor_changed': bool(old_report['changed']),
            'candidate_changed': bool(new_report['changed']),
            'candidate_reason': new_report['reason'],
            'original_active_original_indices': [
                index for index, _ in original_entries
            ],
            'predecessor_active_original_indices': [
                index for index, _ in old_entries
            ],
            'candidate_active_original_indices': [
                index for index, _ in new_entries
            ],
            'original_execution': _executed(original_payload),
            'predecessor_execution': _executed(old_payload),
            'candidate_execution': _executed(new_payload),
        }

    # Direct assertions keep the script useful even without the stored receipt.
    tail = actual['inactive_tail_activation']
    assert tail['original_active_original_indices'] == list(range(10))
    assert tail['predecessor_active_original_indices'][:2] == [11, 10]
    assert tail['candidate_active_original_indices'] == list(range(10))

    dependency = actual['buy_then_sell_dependency']
    assert dependency['original_execution'] == {
        'BUY_PRODUCT@0': 1,
        'BUY_LAND@1': 0,
        'SELL@2': 1,
    }
    assert dependency['predecessor_execution'] == {
        'BUY_PRODUCT@0': 0,
        'BUY_LAND@1': 1,
        'SELL@2': 0,
    }
    assert dependency['candidate_execution'] == dependency['original_execution']

    displaced = actual['capital_steals_product_cash']
    assert displaced['original_execution'] == {
        'BUY_PRODUCT@0': 1,
        'BUY_LAND@1': 0,
    }
    assert displaced['predecessor_execution'] == {
        'BUY_PRODUCT@0': 0,
        'BUY_LAND@1': 1,
    }
    assert displaced['candidate_execution'] == displaced['original_execution']

    gain = actual['sell_funded_free_gain']
    assert gain['candidate_execution'] == {
        'BUY_LAND@0': 1,
        'SELL@1': 1,
    }
    assert gain['candidate_reason'] == 'execution_gain_proved'
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-root', type=Path, default=DEFAULT_LAB)
    parser.add_argument('--check', type=Path)
    args = parser.parse_args()
    actual = reproduce(args.lab_root.resolve())
    if args.check:
        expected = json.loads(args.check.read_text())
        expected_cases = expected['reproduced_cases']
        if actual != expected_cases:
            raise SystemExit('stored predecessor receipt differs from replay')
    print(json.dumps(actual, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
