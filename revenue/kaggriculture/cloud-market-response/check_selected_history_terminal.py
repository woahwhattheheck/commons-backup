# SPDX-License-Identifier: Apache-2.0
"""Exercise the selected-action history -> joint family -> terminal boundary.

Uses existing source packages and small constructed native transitions only.
No actor, retained game, phase experiment, network request or new game seed.
The integration recipe below is exercised without changing a selected runtime.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
D = None
COUNTS = Counter()
RECORDS = []


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def family_for(bridge, *, limit=32, templates=True, completions=True):
    """Explicit test hypotheses: no observed rival order is an input."""
    universe = list(D.engine.PRODUCTS)
    patterns = [
        {'id': 'gap', 'origin': 'constructed fixed-slot hypothesis',
         'slots': [None, 'MILK', 'WOOL', 'CARROT', 'WHEAT', 'FERTILIZER',
                   'EGG', 'TOMATO', 'STRAWBERRY', 'MELON']},
        {'id': 'wool-first', 'origin': 'constructed alternative slot hypothesis',
         'slots': ['WOOL', 'MILK', 'CARROT', 'WHEAT', 'FERTILIZER',
                   'EGG', 'TOMATO', 'STRAWBERRY', 'MELON']},
    ]
    lots = [
        {'id': 'quiet-operating', 'origin': 'explicit quiet-stock hypothesis',
         'stock': {'WHEAT': 0, 'FERTILIZER': 0}},
        {'id': 'operating-lot', 'origin': 'explicit unobserved-stock hypothesis',
         'stock': {'WHEAT': 2, 'FERTILIZER': 1}},
    ]
    return D.joint.build_joint_terminal_scenarios(
        bridge.history, universe, 718,
        slot_templates=patterns if templates else None,
        unobserved_lots=lots if completions else None,
        max_scenarios=limit,
    )


def trained_bridge(seat, *, shared=False, samples=3, censored=False):
    """Only bridge-produced history enters the consumer; no manual intervals."""
    bridge = D.base.make_bridge()
    transitions = []
    for index, lag in enumerate(range(3, 3-samples, -1)):
        stock = {'MILK': 5, 'WOOL': 1}
        obs, cfg = D.base.fixture(step=718-24*lag, player=seat, stock=stock,
            market={'WOOL': 30000} if censored and index == 1 else None)
        selected = D.base.action([['SELL', 'MILK', 99], [],
                                  ['SELL', 'MILK', 1], ['SELL', 'WOOL', 1]])
        rival_stock = {'MILK': index+2, 'WOOL': 4-index, 'CARROT': 1+index//2}
        rival_queue = [['SELL', p, q] for p, q in rival_stock.items()]
        after, actual = D.base.market_after(obs, cfg, selected,
            rival=rival_queue, rival_stock=rival_stock)
        COUNTS['native_training_market_calls'] += 1
        untouched = deepcopy((obs, cfg, selected, after))
        if shared:
            binding = bridge.ledger.record(obs, cfg, selected,
                post_unit_shed=stock, post_unit_inventories=())
            fill_result = bridge.ledger.observe(after)
            with patch.object(bridge.ledger, 'record', side_effect=AssertionError('second record')), \
                 patch.object(bridge.ledger, 'observe', side_effect=AssertionError('second observe')):
                bridge.bind(obs, cfg, selected, binding)
                result = bridge.observe(after, fill_result=fill_result)
        else:
            with patch.object(D.engine, '_apply_unit_action', side_effect=AssertionError('unit projection')), \
                 patch.object(D.engine, '_process_market', side_effect=AssertionError('market replay')):
                bridge.record(obs, cfg, selected, post_unit_shed=stock, post_unit_inventories=())
                result = bridge.observe(after)
        assert untouched == (obs, cfg, selected, after)
        assert result['status'] == 'recorded'
        assert result['own_sale_units']['MILK'] == actual['own', 'MILK'] == 5
        assert all(item['step'] < after['step'] for item in result['intervals'])
        for product in ('MILK', 'CARROT'):
            interval = next(row for row in result['intervals'] if row['product'] == product)
            assert interval['exact'] and interval['lower'] == actual['rival', product]
        transitions.append(result)
    return bridge, transitions


def terminal_fixture(seat):
    obs, cfg = D.base.fixture(step=718, player=seat,
        stock={'MILK': 7, 'WOOL': 3, 'CARROT': 1})
    selected = D.base.action([['HIRE'], ['SELL', 'MILK', 5],
        ['BUY_SEED', 'CARROT', 1], [], ['SELL', 'WOOL', 99], ['SELL', 'MILK', 99]])
    selected['caller_note'] = {'identity': 'preserve-complete-action'}
    return obs, cfg, selected


def consume(family, obs, cfg, selected, post, *, max_cells=256):
    """Documentation recipe only; no controller or production integration."""
    if not family['ready']:
        return selected, None, None
    packet = D.terminal.build_terminal_inputs(D.engine, obs, cfg, selected,
        post_unit_observation=post, scenarios=family['scenarios'],
        max_plans=3, max_cells=max_cells)
    COUNTS['terminal_producer_calls'] += 1
    COUNTS['producer_native_market_calls'] += packet['native_market_calls']
    output, selector = D.cases.choose(D.deps, obs, cfg, selected, packet)
    COUNTS['score_selector_calls'] += 1
    return output, packet, selector


class JoinTests(unittest.TestCase):
    def test_01_ready_bridge_history_reaches_existing_terminal_consumer(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                bridge, transitions = trained_bridge(seat, shared=bool(seat))
                history_identity = id(bridge.history)
                family = family_for(bridge)
                self.assertEqual(id(bridge.history), history_identity)
                self.assertTrue(family['ready'])
                self.assertEqual(family['joint_support'], 3)
                self.assertEqual(len(family['scenarios']), 12)
                self.assertIsNone(family['scenario_probabilities'])
                for scenario in family['scenarios']:
                    for witness in scenario['origin']['witnesses']:
                        self.assertLess(witness['training_end'], 718)
                        self.assertEqual(witness['training_start'], witness['training_end'])
                    self.assertFalse(scenario['origin']['slot_order_identified'])
                obs, cfg, selected = terminal_fixture(seat)
                post = D.cases.own_unit_snapshot(D.engine, obs, cfg, selected)
                COUNTS['terminal_unit_boundary_captures'] += 1
                original = deepcopy((obs, cfg, selected, post, family))
                with patch.object(D.engine, '_apply_unit_action', side_effect=AssertionError('duplicate unit stage')):
                    out, packet, selector = consume(family, obs, cfg, selected, post)
                self.assertEqual((obs, cfg, selected, post, family), original)
                self.assertTrue(packet['complete'])
                plans = {p['id']: p['action'] for p in packet['plans']}
                scenarios = {s['id']: s for s in packet['scenarios']}
                self.assertEqual([s['origin'] for s in packet['scenarios']],
                                 [s['origin'] for s in family['scenarios']])
                self.assertIn(out, list(plans.values()))
                for plan in plans.values():
                    self.assertEqual(plan['farmer'], selected['farmer'])
                    self.assertEqual(plan['hands'], selected['hands'])
                    self.assertEqual(plan['caller_note'], selected['caller_note'])
                    self.assertEqual(plan['market'][0], ['HIRE'])
                    self.assertEqual(plan['market'][2], ['BUY_SEED', 'CARROT', 1])
                for receipt in packet['document']['receipts']:
                    state, env = D.cases.make_state(obs, cfg, plans[receipt['plan']], scenarios[receipt['scenario']])
                    D.engine.interpreter(state, env)
                    COUNTS['independent_terminal_interpreter_calls'] += 1
                    self.assertEqual(state[seat].status, 'DONE')
                    self.assertEqual([receipt['own_cash'], receipt['rival_cash']],
                        [state[seat].observation.farms[seat]['money'],
                         state[1-seat].observation.farms[1-seat]['money']])
                    COUNTS['cash_receipt_pairs_compared'] += 1
                # Complete history can still produce a budget-limited table.
                # The existing score consumer, not this join, owns that fallback.
                partial_out, partial, partial_selector = consume(family, obs, cfg, selected, post, max_cells=1)
                self.assertFalse(partial['complete'])
                self.assertEqual(partial_out, selected)
                self.assertEqual(partial_selector.draws, 0)
                RECORDS.append({'seat': seat, 'shared_ledger': bool(seat),
                    'transitions': transitions, 'family': family, 'packet': packet,
                    'selected_action': out, 'objective': selector.last_objective,
                    'partial_packet': partial, 'partial_action': partial_out})

    def test_02_not_ready_never_calls_a_terminal_producer(self):
        for seat in (0, 1):
            for kind in ('short_history', 'floor_censored', 'unknown_slots',
                         'unknown_operating_stock', 'scenario_budget'):
                with self.subTest(seat=seat, kind=kind):
                    bridge, transitions = trained_bridge(seat, shared=bool(seat),
                        samples=2 if kind == 'short_history' else 3,
                        censored=kind == 'floor_censored')
                    family = family_for(bridge,
                        templates=kind != 'unknown_slots',
                        completions=kind != 'unknown_operating_stock',
                        limit=1 if kind == 'scenario_budget' else 32)
                    self.assertFalse(family['ready'])
                    self.assertEqual(family['scenarios'], [])
                    obs, cfg, selected = terminal_fixture(seat)
                    original = deepcopy(selected)
                    # No unit snapshot is needed on this branch either.
                    with patch.object(D.terminal, 'build_terminal_inputs', side_effect=AssertionError('not-ready producer call')), \
                         patch.object(D.cases, 'choose', side_effect=AssertionError('not-ready selector call')):
                        out, packet, selector = consume(family, obs, cfg, selected, None)
                    self.assertIs(out, selected)
                    self.assertEqual(out, original)
                    self.assertIsNone(packet)
                    self.assertIsNone(selector)
                    COUNTS['not_ready_identity_preservations'] += 1
                    RECORDS.append({'seat': seat, 'case': kind, 'family': family,
                        'output_identical': True, 'terminal_calls': 0,
                        'latest_training_step': max(bridge.history.last.values(), default=None)})


def main():
    global D
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poly-package', type=Path, required=True)
    parser.add_argument('--joint', type=Path, default=HERE/'joint_terminal_history.py')
    parser.add_argument('--bridge-dir', type=Path, default=HERE)
    parser.add_argument('--fills', type=Path, default=HERE.parent/'cloud-observed-fills'/'observed_fills.py')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.poly_package
    sys.path.insert(0, str(root/'source'))
    try:
        terminal = load(root/'source/terminal_inputs.py', 'terminal_inputs')
        cases = load(root/'source/terminal_input_cases.py', '_cedar_joint_existing_cases')
    finally:
        sys.path.pop(0)
    deps = cases.dependencies(root/'dependencies/engine_loader.py', root/'engine',
                              root/'dependencies', root/'dependencies/full_support.py')
    base = load(args.bridge_dir/'check_selected_action_history.py', '_cedar_bridge_checks')
    base.D = NS(engine=deps.engine,
        flow=load(args.bridge_dir/'flow.py', '_cedar_joint_existing_flow'),
        fills=load(args.fills, '_cedar_joint_existing_fills'),
        sorrel=load(args.bridge_dir/'vendor/sorrel_adapter.py', '_cedar_joint_existing_sorrel'),
        subject=load(args.bridge_dir/'selected_action_history.py', '_cedar_joint_subject'))
    for name, expected in base.ENGINE_HASHES.items():
        assert hashlib.sha256((root/'engine'/name).read_bytes()).hexdigest() == expected, name
    D = NS(base=base, engine=deps.engine, deps=deps, terminal=terminal, cases=cases,
           joint=load(args.joint, '_cedar_joint_history'))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(JoinTests))
    paths = [Path(__file__), args.joint, args.fills,
             args.bridge_dir/'selected_action_history.py', args.bridge_dir/'check_selected_action_history.py',
             args.bridge_dir/'flow.py', args.bridge_dir/'vendor/sorrel_adapter.py']
    report = {'schema': 'titan.selected-history-terminal-check.v1',
        'tests': {'methods': result.testsRun, 'failures': len(result.failures),
                  'errors': len(result.errors), 'success': result.wasSuccessful()},
        'counts': dict(COUNTS), 'records': RECORDS,
        'source_hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'consumer_hashes': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in root.rglob('*.py')},
        'engine_hashes': deps.engine_hashes, 'actor_calls': 0, 'complete_games': 0,
        'new_game_seeds': 0, 'selected_runtime_changed': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('records', 'source_hashes', 'consumer_hashes')}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
