# SPDX-License-Identifier: Apache-2.0
"""Join retained public inputs, static HAZEL programs, ROUTE-FLOW and DATE.

This is an offline conditional quote consumer, not a live agent. A saved input
is not a restored controller. No actor action, physical rollout, future-state
replay, learned scenario, or alternative ranking implementation is introduced.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
DEPENDENCIES = {
    'hazel': ('cloud-capital-bundles/capital_routes.py', '00abee3c99641eb0ab1729fd80e6f9a5c783f373'),
    'flow': ('cloud-capital-route-flow/dated_flow.py', 'ddbbe439c93082ab68b2e7e8dcfe302bbee052e7'),
    'date': ('cloud-capital-scenarios/dated_scenarios.py', '5e418aeca191e71d281f669a9fdd9f4b0730617f'),
    'inputs': ('cloud-terminal-sell/reached_states.py', '24f8bd4cac2e88c609f309aa241eca8f3d1e05ee'),
    'programs': ('cloud-titan-composition/vendor/sell/reference/next-panel/vendor/arlene.py',
                 'bdb9cf58148a3c7961c085f4902759537decabf6'),
    'mechanics': ('cloud-titan-composition/vendor/sell/mechanics.py', '044a4f9c0a4a44dde10ada57563238bcaf82075d'),
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_dependencies(root: Path = HERE.parent) -> SimpleNamespace:
    """Execute the exact verified source bytes, without consulting bytecode.

    Preserve normal module metadata and restore this loader's prior aliases if
    any source fails. Imported transitive dependencies and arbitrary import
    side effects are not snapshotted or rolled back.
    """
    modules, pins = {}, {}
    missing = object()
    previous = {}
    try:
        for key, (relative, expected) in DEPENDENCIES.items():
            path = root.resolve() / relative
            raw = path.read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if actual != expected:
                raise ValueError(f'This consumer was tested against different source: {relative}')
            name = '_reached_quote_' + key
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f'Cannot load source module: {relative}')
            code = compile(raw, str(path), 'exec', dont_inherit=True)
            module = importlib.util.module_from_spec(spec)
            previous[name] = sys.modules.get(name, missing)
            sys.modules[name] = module
            exec(code, module.__dict__)
            modules[key] = module
            pins[relative] = {'git_blob': actual, 'sha256': sha256(raw)}
    except BaseException:
        for name, prior in previous.items():
            if prior is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
        raise
    return SimpleNamespace(**modules, pins=pins)


def _steps(value: Mapping) -> dict:
    if not isinstance(value, Mapping):
        raise ValueError('Dated flows must map integer steps to declared values')
    output = {}
    for key, rows in value.items():
        if type(key) is int:
            step = key
        elif isinstance(key, str) and key.isascii() and key.isdecimal():
            step = int(key)
        else:
            raise ValueError('Dated scenario step must be an integer or decimal JSON key')
        if step in output:
            raise ValueError('Repeated scenario step after integer conversion')
        output[step] = rows
    return output


def make_scenarios(specifications: list[dict], flow: Any) -> tuple:
    """Convert caller-declared scenarios, never derive them from future rows."""
    if not isinstance(specifications, list) or not specifications:
        raise ValueError('Supply at least one explicit scenario')
    answer = []
    for spec in specifications:
        if not isinstance(spec, dict) or not isinstance(spec.get('name'), str) or not spec['name']:
            raise ValueError('Each scenario needs a nonempty name')
        unexpected = set(spec) - {'name', 'rival_orders', 'shop_additions', 'description'}
        if unexpected:
            raise ValueError('Unrecognized scenario fields: ' + ', '.join(sorted(unexpected)))
        answer.append(flow.Scenario(
            name=spec['name'], rival_orders=_steps(spec.get('rival_orders', {})),
            shop_additions=_steps(spec.get('shop_additions', {})),
            description=spec.get('description', 'Explicit conditional sensitivity; no probability assigned')))
    return tuple(answer)


def compare_saved_input(row: dict, specifications: list[dict], dependencies: SimpleNamespace,
                        *, max_units: int = 100_000, seconds: float | None = 0.2,
                        retain_trace: bool = True) -> dict:
    """Compare two static program quotations at an actual or constructed input.

    This function does not certify how the caller obtained the input. Keep its
    origin receipt beside the report. Expected actions and other record labels
    are excluded by the existing input normalizer before any quotation runs.
    Neither Agent(), Agent.act(), choose_before_action(), nor SELL is called.
    The static programs omit future live-controller amendments by design.
    """
    seat = row['seat']
    if type(seat) is not int or seat not in (0, 1):
        raise ValueError('Recorded seat must be zero or one')
    safe = dependencies.inputs.actor_input(row, seat)
    obs, cfg = safe['observation'], safe['configuration']
    if obs['step'] != dependencies.hazel.DECISION_STEP:
        raise ValueError('This two-program consumer is defined at checkpoint226')
    scenarios = make_scenarios(specifications, dependencies.flow)
    # Decode immutable published programs, not a fresh or reconstructed Agent.
    programs = dependencies.programs.routes()
    ids = (dependencies.hazel.MAIN, dependencies.hazel.SHEEP)
    offers = tuple(dependencies.hazel.quote_program(key, programs[key], obs, cfg,
                                                    dependencies.mechanics) for key in ids)
    report = {
        'schema': 'capital.reached-static-quote.v1',
        'scope': 'conditional_static_program_quantities_not_live_controller_or_physical_feasibility',
        'input_sha256': sha256(canonical(safe)), 'step': obs['step'], 'seat': seat,
        'source_pins': dependencies.pins,
        'program_sha256': {key: sha256(canonical(programs[key])) for key in ids},
        'scenario_specifications': copy.deepcopy(specifications),
        'marked_offers': [dataclasses.asdict(offer) for offer in offers],
        'original_mark_choice': dependencies.hazel.quote_screen(offers, obs),
        'flow': None, 'ranking': None, 'individual_rankings': [],
        'complete': False, 'live_route_applied': False,
        'actor_calls': 0, 'new_game_evaluations': 0,
    }
    flow = dependencies.flow.evaluate_scenarios(
        offers, obs, cfg, dependencies.mechanics, scenarios,
        max_units=max_units, seconds=seconds, retain_trace=retain_trace)
    report['flow'] = flow
    if not flow['complete']:
        return report
    cash = dependencies.flow.as_cash_scenarios(flow, dependencies.date.CashScenario)
    ranking = dependencies.date.DatedSelector(cash)
    ranking(offers, obs)
    report['ranking'] = ranking.last_report
    for item in cash:
        single = dependencies.date.DatedSelector((item,))
        single(offers, obs)
        report['individual_rankings'].append(single.last_report)
    # Reconcile the composition, not another pricing or optimization method.
    if len(flow['rows']) != len(scenarios) or len(report['ranking']['scenarios']) != len(scenarios):
        raise ValueError('Incomplete scenario identities in the joined reports')
    reconciled = 0
    for world, ranked in zip(flow['rows'], report['ranking']['scenarios']):
        if ({item['route_id'] for item in world} != set(ids)
                or set(ranked['routes']) != set(ids)
                or any(item['scenario'] != ranked['name'] for item in world)):
            raise ValueError('Route/scenario identity mismatch in the joined reports')
        for trajectory in world:
            result = ranked['routes'][trajectory['route_id']]
            if (not result['complete'] or result['final_nominal_cash'] != trajectory['final_marked_cash']
                    or result['minimum_nominal_cash'] != trajectory['minimum_marked_cash']
                    or result['first_negative'] != trajectory['first_negative']):
                raise ValueError('FLOW and DATE cash reports do not reconcile')
            reconciled += 1
    report.update(complete=True, reconciled_route_scenarios=reconciled)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_row', type=Path)
    parser.add_argument('scenarios', type=Path, help='JSON list of explicitly declared scenarios')
    parser.add_argument('--kaggriculture-root', type=Path, default=HERE.parent)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=0.2)
    parser.add_argument('--max-units', type=int, default=100_000)
    args = parser.parse_args()
    try:
        dependencies = load_dependencies(args.kaggriculture_root)
        row = dependencies.inputs.decode(args.input_row.read_bytes())
        scenarios = dependencies.inputs.decode(args.scenarios.read_bytes())
        report = compare_saved_input(row, scenarios, dependencies,
                                    max_units=args.max_units, seconds=args.seconds)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        parser.exit(2, f'Reached quote consumer: {exc}\n')
    print(json.dumps({'complete': report['complete'],
                      'reason': report['flow']['reason'],
                      'conditional_choice': None if report['ranking'] is None else report['ranking']['selected'],
                      'live_route_applied': False}))
    if not report['complete']:
        raise SystemExit(3)


if __name__ == '__main__':
    main()
