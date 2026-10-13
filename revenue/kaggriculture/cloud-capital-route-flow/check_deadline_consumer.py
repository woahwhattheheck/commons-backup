# SPDX-License-Identifier: Apache-2.0
"""Exercise completion checks through existing saved-input and cash consumers.

Use two explicit source closures: the original PR10102 closure and the same
closure with the deadline repair and its declared reader source pin. The input
and scenarios are reused unchanged. No game or controller action is executed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


def load_consumer(root: Path, name: str):
    path = root / 'cloud-capital-bundles/reached_quote_case.py'
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    consumer = importlib.util.module_from_spec(spec)
    sys.modules[name] = consumer
    spec.loader.exec_module(consumer)
    return consumer, consumer.load_dependencies(root)


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def late_terminal_price(dependencies, row):
    """One final quote returns at time 2 under a 1-second cooperative budget."""
    clock = Clock()
    obs = copy.deepcopy(row['observation'])
    obs['step'] = 718
    config = {'episodeSteps': 720}
    offers = (SimpleNamespace(route_id='incumbent', orders=()),
              SimpleNamespace(route_id='alternative', orders=(
                  {'step': 718, 'slot': 0, 'order': ['SELL', 'WOOL', 1], 'delta': 0},)))
    original = dependencies.mechanics.market_price
    calls = []
    def price(*args):
        result = original(*args)
        calls.append(result)
        clock.now = 2.0
        return result
    frozen = copy.deepcopy((obs, config, offers))
    with (patch.object(dependencies.flow, 'time', SimpleNamespace(perf_counter=clock)),
          patch.object(dependencies.mechanics, 'market_price', price)):
        report = dependencies.flow.evaluate_scenarios(offers, obs, config,
            dependencies.mechanics, [dependencies.flow.Scenario('declared')], seconds=1)
    choice = None
    if report['complete']:
        choice = dependencies.date.DatedSelector(dependencies.flow.as_cash_scenarios(
            report, dependencies.date.CashScenario))(offers, obs)
    assert (obs, config, offers) == frozen
    return {'budget_seconds': 1, 'clock_after': clock.now, 'quotes': calls,
            'complete': report['complete'], 'reason': report['reason'],
            'ranked_choice': choice, 'inputs_unchanged': True}


def late_saved_vector(consumer, dependencies, row, scenarios):
    """The actual final route finishes, then its delegated return crosses time."""
    clock = Clock()
    original = dependencies.flow.value_route
    expected_calls = len(scenarios) * 2
    count = 0
    def late_return(*args, **kwargs):
        nonlocal count
        report = original(*args, **kwargs)
        count += 1
        if count == expected_calls:
            clock.now = 2.0
        return report
    frozen = copy.deepcopy((row, scenarios))
    with (patch.object(dependencies.flow, 'time', SimpleNamespace(perf_counter=clock)),
          patch.object(dependencies.flow, 'value_route', side_effect=late_return),
          patch.object(dependencies.date, 'DatedSelector',
                       wraps=dependencies.date.DatedSelector) as ranker):
        report = consumer.compare_saved_input(row, scenarios, dependencies, seconds=1)
    assert (row, scenarios) == frozen
    assert count == expected_calls
    return {'actual_route_evaluations': count, 'budget_seconds': 1,
            'clock_after': clock.now, 'complete': report['complete'],
            'flow_reason': report['flow']['reason'], 'returned_scenario_rows': len(report['flow']['rows']),
            'ranker_calls': ranker.call_count,
            'choice': None if report['ranking'] is None else report['ranking']['selected'],
            'inputs_unchanged': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', required=True, type=Path)
    parser.add_argument('--updated-root', required=True, type=Path)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--scenarios', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    before, baseline = load_consumer(args.baseline_root, 'route_flow_original_consumer')
    after, candidate = load_consumer(args.updated_root, 'route_flow_updated_consumer')
    row = json.loads(args.input.read_text(encoding='utf-8'))
    scenarios = json.loads(args.scenarios.read_text(encoding='utf-8'))
    frozen = copy.deepcopy((row, scenarios))
    a = before.compare_saved_input(row, scenarios, baseline, seconds=None)
    b = after.compare_saved_input(row, scenarios, candidate, seconds=None)
    a_pins, b_pins = a.pop('source_pins'), b.pop('source_pins')
    assert a == b, 'On-time economic/coverage/input result changed'
    assert (row, scenarios) == frozen
    original_terminal = late_terminal_price(baseline, row)
    fixed_terminal = late_terminal_price(candidate, row)
    assert original_terminal['complete'] and original_terminal['ranked_choice'] == 'alternative'
    assert not fixed_terminal['complete'] and fixed_terminal['ranked_choice'] is None
    original_vector = late_saved_vector(before, baseline, row, scenarios)
    fixed_vector = late_saved_vector(after, candidate, row, scenarios)
    assert original_vector['complete'] and original_vector['ranker_calls'] > 0
    assert not fixed_vector['complete'] and fixed_vector['ranker_calls'] == 0
    report = {
        'scope': 'source-bound conditional valuations; no controller, game or hidden-future execution',
        'input_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'scenario_sha256': hashlib.sha256(args.scenarios.read_bytes()).hexdigest(),
        'baseline_source_pins': a_pins, 'updated_source_pins': b_pins,
        'on_time_complete_report_equal_except_source_pins': True,
        'on_time_canonical_report_sha256': hashlib.sha256(before.canonical(a)).hexdigest(),
        'reconciled_route_scenarios': b['reconciled_route_scenarios'],
        'dynamic_rows': sum(len(r['cash_flow_rows']) for world in b['flow']['rows'] for r in world),
        'final_cash': [[r['final_marked_cash'] for r in world] for world in b['flow']['rows']],
        'conditional_choice': b['ranking']['selected'],
        'original_terminal_price_overrun': original_terminal,
        'updated_terminal_price_overrun': fixed_terminal,
        'original_saved_vector_overrun': original_vector,
        'updated_saved_vector_overrun': fixed_vector,
        'all_inputs_unchanged': True, 'actor_calls': 0, 'game_evaluations': 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k:v for k,v in report.items() if 'source_pins' not in k}, indent=2))


if __name__ == '__main__':
    main()
