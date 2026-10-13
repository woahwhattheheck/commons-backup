# SPDX-License-Identifier: Apache-2.0
"""Falsify the independent oracle using deliberately altered engine semantics.

These are scratch ENGINE mutants, not the donor guard. An assertion rejection
proves the tests distinguish that semantic assumption; it is not guard efficacy.
All pristine dependency pins must validate before any mutation is constructed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

from engine_action_contract import EngineOracle
from check_engine_action_contract import run_suite

MUTATIONS = {
    "atomic_plant_gate_removed": [
        ('blocked = {crop for crop, n in plant_demand.items() if n > seeds.get(crop, 0)}', 'blocked = set()')],
    "ghost_plant_demand_ignored": [
        ('unit_actions = [farmer_action, *hands_actions]',
         'unit_actions = [farmer_action, *hands_actions[:len(obs0.farms[i]["hands"])]]')],
    "empty_market_rows_compacted": [
        ('queues.append(q[:max_orders])', 'queues.append([row for row in q if row][:max_orders])')],
    "zero_order_cap_not_normalized": [
        ('max_orders = max(1, int(get(env.configuration, "maxMarketOrdersPerTurn", 10)))',
         'max_orders = max(0, int(get(env.configuration, "maxMarketOrdersPerTurn", 10)))')],
    "all_numeric_market_fields_filtered": [
        ('    op = order[0]\n',
         '    op = order[0]\n    if len(order) >= 3 and isinstance(order[2], float) and not math.isfinite(order[2]):\n        return None\n')],
    "all_numeric_unit_fields_filtered": [
        ('    op = action[0]\n',
         '    op = action[0]\n    if len(action) >= 3 and isinstance(action[2], float) and not math.isfinite(action[2]):\n        return\n')],
    "market_runs_before_units": [
        ('    day = step // turns_per_day\n\n    for i, s in enumerate(state):',
         '    day = step // turns_per_day\n    _process_market(state, env)\n\n    for i, s in enumerate(state):'),
        ('    _process_market(state, env)\n    _town_consume(env, state, step)',
         '    _town_consume(env, state, step)')],
    "unsupported_product_buys_enabled": [
        ('elif op == "BUY_PRODUCT" and item in ("WHEAT", "FERTILIZER"):',
         'elif op == "BUY_PRODUCT" and item in PRODUCTS:')],
    "one_unfunded_crop_blocks_every_crop": [
        ('and a[1] in blocked:', 'and blocked:')],
}


def replace_once(source, old, new):
    count = source.count(old)
    if count != 1:
        raise ValueError(f"mutation anchor must match once, found {count}: {old!r}")
    return source.replace(old, new, 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--loader', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        pristine = EngineOracle(args.engine_dir, args.loader)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    baseline = run_suite(pristine, io.StringIO())
    if not baseline.wasSuccessful() or baseline.testsRun != 29 or baseline.skipped:
        print('pristine oracle must pass all 29 tests before controls', file=sys.stderr)
        return 2
    original = (pristine.engine_dir / 'kaggriculture.py').read_text()
    rows = []
    for name, edits in MUTATIONS.items():
        source = original
        for old, new in edits:
            source = replace_once(source, old, new)
        compile(source, f'<engine-control:{name}>', 'exec')
        oracle = EngineOracle(args.engine_dir, args.loader)
        with tempfile.TemporaryDirectory(prefix='bridge-engine-control-') as tmp:
            directory = Path(tmp)
            for dep in ('kaggriculture.py', 'kaggriculture.json', 'utils.py'):
                shutil.copyfile(pristine.engine_dir / dep, directory / dep)
            (directory / 'kaggriculture.py').write_text(source)
            # Test-only override AFTER authentication of the original. Nothing
            # replaces the caller's engine file or relaxes verify_inputs().
            oracle.engine = oracle.load_engine(directory)
            stream = io.StringIO()
            result = run_suite(oracle, stream)
        row = {'name': name, 'assertion_rejected': bool(result.failures),
               'tests_run': result.testsRun, 'failures': len(result.failures),
               'errors': len(result.errors), 'skipped': len(result.skipped),
               'engine_sha256': hashlib.sha256(source.encode()).hexdigest(),
               'failed_tests': sorted({str(test) for test, _ in result.failures}),
               'execution': oracle.counts()}
        rows.append(row)
        print(json.dumps(row, sort_keys=True), flush=True)
    success = all(row['assertion_rejected'] and not row['skipped'] for row in rows)
    report = {'schema': 'titan.defensive.engine-contract-controls.v1', 'success': success,
              'python': sys.version, 'optimize': sys.flags.optimize, 'inputs': pristine.identities,
              'pristine_tests': baseline.testsRun, 'controls': rows,
              'scope': 'Changed ENGINE semantics in scratch; not donor mutants, runtime or economic acceptance'}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
