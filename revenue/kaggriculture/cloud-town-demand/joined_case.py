"""Run declared complete town paths through the existing saved-input consumer.

Uses OSPREY's source-pinned HAZEL -> ROUTE-FLOW -> DATE join unchanged. The input
is a saved observation, not a restored controller; future paths are assumptions.
"""
from __future__ import annotations
import argparse
import dataclasses
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

from flow_scenarios import make_flow_scenario
from test_town_demand import load_engine


def run(row, paths, dependencies, mechanics, compare_saved_input, *,
        max_units=200_000, seconds=None):
    if not isinstance(paths, list) or not paths:
        raise ValueError('Supply at least one named full shop path')
    safe = dependencies.inputs.actor_input(row, row['seat'])
    obs, cfg = safe['observation'], safe['configuration']
    # The consumer's frozen mechanics omits the cap constant; use the exact
    # official engine for timing/cap, and verify the common demand catalogue.
    if (mechanics.SHOPS != dependencies.mechanics.SHOPS
            or mechanics.PRODUCTS != dependencies.mechanics.PRODUCTS
            or mechanics.TOWN_CENTER_PRODUCTS != dependencies.mechanics.TOWN_CENTER_PRODUCTS):
        raise ValueError('Town catalogues differ between the source inputs')
    specifications, bindings = [], []
    for path in paths:
        scenario, binding = make_flow_scenario(
            obs, cfg, mechanics, dependencies.flow.Scenario,
            name=path['name'], future_shops=path['future_shops'],
            rival_orders=path.get('rival_orders', {}))
        specifications.append(dataclasses.asdict(scenario))
        bindings.append(binding)
    start = time.perf_counter()
    result = compare_saved_input(row, specifications, dependencies,
                                 max_units=max_units, seconds=seconds, retain_trace=True)
    elapsed = time.perf_counter() - start
    return {'schema': 'town.reached-flow-join.v1', 'bindings': bindings,
            'scope': 'saved_observation_with_declared_complete_town_paths_not_physical_fills',
            'declared_paths': paths, 'scenario_bank_exhaustive': False,
            'probabilities': None, 'elapsed_quote_flow_rank_seconds': elapsed,
            'result': result}


def load_consumer(source):
    """Execute the exact bytes checked here, then reuse the reader's loader.

    Captured-source execution preserves module metadata without consulting a
    cached bytecode body. Only this reader alias is restored on a failed load;
    transitive import side effects are not rolled back.
    """
    raw = source.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if blob not in ('e8851922cedbf0692a02fa372599e9dbdc3798fa',
                    '794b56813daf89e06b76aaa8cbb291498e15c73c',
                    'f5f64be61dd6277e8436d930286498486ff4f2de'):
        raise ValueError('Saved-input consumer differs from the tested source pin')
    spec = importlib.util.spec_from_file_location('_amber_reached', source)
    if spec is None or spec.loader is None:
        raise ImportError('Cannot prepare the saved-input reader')
    code = compile(raw, str(source), 'exec', dont_inherit=True)
    module = importlib.util.module_from_spec(spec)
    missing = object()
    previous = sys.modules.get(spec.name, missing)
    sys.modules[spec.name] = module
    try:
        exec(code, module.__dict__)
    except BaseException:
        if previous is missing:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
        raise
    return module, blob


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--paths', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-units', type=int, default=200_000)
    parser.add_argument('--seconds', type=float, default=None)
    args = parser.parse_args()
    try:
        source = args.source_root / 'cloud-capital-bundles/reached_quote_case.py'
        module, blob = load_consumer(source)
        dependencies = module.load_dependencies(args.source_root)
        row = dependencies.inputs.decode(args.input.read_bytes())
        paths = dependencies.inputs.decode(args.paths.read_bytes())
        report = run(row, paths, dependencies, load_engine(args.engine),
                     module.compare_saved_input, max_units=args.max_units,
                     seconds=args.seconds)
        report['joined_consumer_git_blob'] = blob
        report['input_file_sha256'] = hashlib.sha256(args.input.read_bytes()).hexdigest()
        report['adapter_sha256'] = hashlib.sha256(Path(__file__).with_name('flow_scenarios.py').read_bytes()).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        parser.exit(2, f'Town flow consumer: {exc}\n')
    result = report['result']
    print(json.dumps({'complete': result['complete'],
                      'reason': result['flow']['reason'],
                      'conditional_choice': None if result['ranking'] is None else result['ranking']['selected'],
                      'paths': len(paths), 'games': 0,
                      'wall_seconds': report['elapsed_quote_flow_rank_seconds']}))
    if not result['complete']:
        raise SystemExit(3)


if __name__ == '__main__':
    main()
