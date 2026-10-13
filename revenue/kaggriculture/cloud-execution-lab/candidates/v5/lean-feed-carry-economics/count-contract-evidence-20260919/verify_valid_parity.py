"""Boundary-complete slices of ordinary integer inputs, not live-game evidence."""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
REL = Path('revenue/kaggriculture/cloud-execution-lab/candidates/v5/lean-feed-carry-economics/wheat_feed_carry_oracle.py')


def load(name):
    source = ROOT / name / REL
    spec = importlib.util.spec_from_file_location('parity_' + name, source)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load pinned source')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def functions(path):
    return {n.name: ast.dump(n, include_attributes=False)
            for n in ast.parse(path.read_bytes()).body if isinstance(n, ast.FunctionDef)}


def main():
    started = time.monotonic()
    before, after = load('original'), load('patched')
    old_functions = functions(ROOT / 'original' / REL)
    new_functions = functions(ROOT / 'patched' / REL)
    if old_functions.keys() != new_functions.keys():
        raise RuntimeError('Unexpected public/source function set change')
    changed = [k for k in old_functions if old_functions[k] != new_functions[k]]
    if changed != ['analyze_certified_window']:
        raise RuntimeError('Unexpected arithmetic or authority change: ' + repr(changed))
    original_receipt = before.source_theorem_receipt()
    if original_receipt != after.source_theorem_receipt():
        raise RuntimeError('Source theorem receipt changed')

    counters = {'valid_output_pairs_equal': 0, 'unsupported_helper_windows_rejected': 0,
                'upstream_gap_positive_with_minimal_helper': 0, 'inputs_unchanged': 0}
    output_binding = hashlib.sha256()
    for stock in range(101):
        for returned in range(101):
            for offered in sorted({0, 1, 2, stock, 100}):
                executable = min(stock, offered)
                threshold = stock + returned - executable
                requirements = {0, stock + returned, threshold - 1, threshold,
                                threshold + 1, threshold + 2, threshold + 3}
                for required in sorted(q for q in requirements if 0 <= q <= stock + returned):
                    minimum = max(0, required - threshold)
                    packet = {
                        'observed_shed_wheat': stock, 'eod_wheat_credit': returned,
                        'required_wheat': required, 'offered_wheat': offered,
                        'helper_report': {
                            'certified': True, 'changed': minimum > 0,
                            'observed_shed_wheat': stock, 'eod_wheat_credit': returned,
                            'required_wheat': required, 'withheld_units': minimum,
                        },
                    }
                    snapshot = json.dumps(packet, sort_keys=True)
                    if minimum > 2:
                        for subject in (before, after):
                            try:
                                subject.analyze_certified_window(packet)
                            except subject.WheatCensusError as exc:
                                if 'source helper ceiling' not in str(exc):
                                    raise RuntimeError('Wrong unsupported-window diagnostic') from exc
                            else:
                                raise RuntimeError('Unsupported helper window admitted')
                        counters['unsupported_helper_windows_rejected'] += 1
                    else:
                        old_result = before.analyze_certified_window(packet)
                        new_result = after.analyze_certified_window(packet)
                        if old_result != new_result:
                            raise RuntimeError('Valid-input semantic drift at ' + snapshot)
                        if new_result['candidate_build_authorized'] is not False or new_result['promotion_authorized'] is not False:
                            raise RuntimeError('Unexpected candidate authority')
                        if new_result['current_policy_withheld'] != minimum or new_result['min_provable_withheld'] != minimum:
                            raise RuntimeError('Independent arithmetic disagreement')
                        counters['valid_output_pairs_equal'] += 1
                        if new_result['upstream_balance_offer_gap_units'] > 0:
                            counters['upstream_gap_positive_with_minimal_helper'] += 1
                        output_binding.update((json.dumps(new_result, sort_keys=True) + '\n').encode())
                    if json.dumps(packet, sort_keys=True) != snapshot:
                        raise RuntimeError('Input record mutated')
                    counters['inputs_unchanged'] += 1
    result = {
        'state': 'PASS_BOUNDARY_SLICE_PARITY', 'optimized': bool(sys.flags.optimize),
        'source_head': '9d28247a10ad1b911050eb865b7a74bba6eb5cf2',
        'changed_functions': changed, 'all_other_function_asts_identical': True,
        'source_theorem_receipt_identical': True, 'counts': counters,
        'ordered_output_sha256': output_binding.hexdigest(),
        'elapsed_seconds': round(time.monotonic() - started, 3),
        'domain': {'stock': 'every integer 0..100', 'return': 'every integer 0..100',
                   'offer': 'unique {0,1,2,stock,100}',
                   'required': 'valid unique {0,stock+return,threshold-1,threshold,threshold+1,threshold+2,threshold+3}',
                   'threshold': 'stock+return-min(stock,offer)'},
        'limits': ['Boundary slices, not every four-dimensional input.',
                   'Synthetic evidence oracle execution, not the D2 gameplay runtime.',
                   'No empirical candidate or promotion authorization.'],
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
