# SPDX-License-Identifier: Apache-2.0
"""Exercise exact-source loading through the real saved-input consumer.

The stale-cache witness is constructed locally from two existing source files;
no historical report is alleged to have consumed stale code. The complete
on-time comparison uses the retained input and existing declared scenarios.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import shutil
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_reader(root: Path, name: str):
    path = root / 'cloud-capital-bundles/reached_quote_case.py'
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def cached_witness(reader, root: Path, old_flow: bytes, row: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix='quote-source-binding-') as directory:
        copy_root = Path(directory) / 'source'
        shutil.copytree(root, copy_root, ignore=shutil.ignore_patterns('__pycache__'))
        path = copy_root / 'cloud-capital-route-flow/dated_flow.py'
        current = path.read_bytes()
        if len(current) < len(old_flow) + 2:
            raise ValueError('Existing source versions do not fit this timestamp-cache fixture')
        stale = old_flow + b'\n#' + b' ' * (len(current) - len(old_flow) - 2)
        stamp = 1788820000
        path.write_bytes(stale)
        os.utime(path, (stamp, stamp))
        cache = py_compile.compile(str(path), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        cached_bytes = Path(cache).read_bytes()
        path.write_bytes(current)
        os.utime(path, (stamp, stamp))
        dependencies = reader.load_dependencies(copy_root)
        observation = copy.deepcopy(row['observation'])
        observation['step'] = 718
        original = dependencies.mechanics.market_price
        clock = SimpleNamespace(now=0.0)
        def price(*args):
            result = original(*args)
            clock.now = 2.0
            return result
        offers = (SimpleNamespace(route_id='incumbent', orders=()),
                  SimpleNamespace(route_id='alternative', orders=(
                    {'step': 718, 'slot': 0, 'order': ['SELL', 'WOOL', 1], 'delta': 0},)))
        saved = copy.deepcopy(observation)
        with (patch.object(dependencies.flow, 'time',
                           SimpleNamespace(perf_counter=lambda: clock.now)),
              patch.object(dependencies.mechanics, 'market_price', price)):
            report = dependencies.flow.evaluate_scenarios(offers, observation,
                {'episodeSteps': 720}, dependencies.mechanics,
                [dependencies.flow.Scenario('declared')], seconds=1)
        choice = None
        if report['complete']:
            choice = dependencies.date.DatedSelector(dependencies.flow.as_cash_scenarios(
                report, dependencies.date.CashScenario))(offers, observation)
        assert observation == saved
        assert path.read_bytes() == current
        assert Path(cache).read_bytes() == cached_bytes
        return {'complete': report['complete'], 'reason': report['reason'],
                'choice': choice, 'declared_source': dependencies.pins[
                    'cloud-capital-route-flow/dated_flow.py'],
                'file_bytes_unchanged': True, 'cache_bytes_unchanged': True,
                'injected_budget_seconds': 1, 'injected_clock_after': clock.now,
                'inputs_unchanged': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-root', 'updated-root', 'old-flow', 'input', 'scenarios', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    baseline = load_reader(args.baseline_root, 'quote_original_reader')
    updated = load_reader(args.updated_root, 'quote_updated_reader')
    row = json.loads(args.input.read_text(encoding='utf-8'))
    scenarios = json.loads(args.scenarios.read_text(encoding='utf-8'))
    original_row = copy.deepcopy(row)
    a = baseline.compare_saved_input(row, scenarios, baseline.load_dependencies(args.baseline_root), seconds=None)
    b = updated.compare_saved_input(row, scenarios, updated.load_dependencies(args.updated_root), seconds=None)
    assert a == b, 'On-time values, scope or provenance changed'
    original = cached_witness(baseline, args.baseline_root, args.old_flow.read_bytes(), row)
    fixed = cached_witness(updated, args.updated_root, args.old_flow.read_bytes(), row)
    assert original['complete'] and original['choice'] == 'alternative'
    assert not fixed['complete'] and fixed['reason'] == 'incomplete_budget' and fixed['choice'] is None
    assert original['declared_source'] == fixed['declared_source']
    assert row == original_row
    output = {'scope': 'local stale-cache witness and retained-input conditional quotation; no actor or game',
              'input_sha256': digest(args.input.read_bytes()),
              'scenario_sha256': digest(args.scenarios.read_bytes()),
              'on_time_complete_report_equal': True,
              'on_time_report_sha256': digest(baseline.canonical(a)),
              'dynamic_rows': sum(len(r['cash_flow_rows']) for world in a['flow']['rows'] for r in world),
              'reconciled_route_scenarios': a['reconciled_route_scenarios'],
              'unchanged_declared_sources': a['source_pins'],
              'original_stale_cache': original, 'updated_stale_cache': fixed,
              'actor_calls': 0, 'game_evaluations': 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(output, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k != 'unchanged_declared_sources'}, indent=2))


if __name__ == '__main__':
    main()
