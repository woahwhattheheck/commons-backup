# SPDX-License-Identifier: Apache-2.0
"""Require behavioral assertion failures for seven broken stock compositions.

Each mutant runs one focused check in a fresh interpreter, not an imported suite
with cached native modules. Hash-only tests are intentionally NOT selected.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import stock_bridge as bridge


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('mutation anchor drift')
    return source.replace(before, after, 1)


def run(source, composed, *, gameplay=None):
    here = Path(__file__).resolve().parent
    gameplay = gameplay or here.parent
    donor = bridge.peers(gameplay)
    base = (source/'operating_stock.py').read_text()
    selected = [
        ('omit_prefix', 'test_dead_tail_fertilizer_hire_and_sale_slots'),
        ('omit_harvest', 'test_harvest_rejection_does_not_erase_fertilizer'),
        ('terminal_noop', 'test_terminal_restores_post_fertilizer_not_parent'),
        ('terminal_undoes_fert', 'test_actual_engine_keeps_fertilizer_payoff_after_terminal_release'),
        ('release_by_default', 'test_observer_is_identity_preserving'),
        ('copy_off_objects', 'test_observer_is_identity_preserving'),
        ('leak_probe', 'test_probe_restores_callables_on_exception'),
    ]
    results = []
    for name, check in selected:
        with tempfile.TemporaryDirectory(prefix='stockbridge-mutant-') as temporary:
            root = Path(temporary)
            repair = root/'gameplay'
            for relative, _ in bridge.PEERS.values():
                target = repair/relative; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(gameplay/relative, target)
            tools = repair/'operating-stock-prefix'
            test = tools/'test_stock_bridge.py'; shutil.copy2(here/test.name, test)
            bridge_text = (here/'stock_bridge.py').read_text()
            runtime = root/'runtime'
            shutil.copytree(composed, runtime, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            if name == 'omit_prefix':
                (runtime/'operating_stock.py').write_text(donor['harvest'].repair_source(base))
            elif name == 'omit_harvest':
                (runtime/'operating_stock.py').write_text(donor['prefix'].port_helper(base))
            elif name == 'terminal_noop':
                bridge_text = replace_once(bridge_text,
                    'return (gated, gate_report) if self.release else (proposed, report)',
                    'return proposed, report')
            elif name == 'terminal_undoes_fert':
                bridge_text = replace_once(bridge_text,
                    'return (gated, gate_report) if self.release else (proposed, report)',
                    "if self.release and 'terminal_feed_gate' in gate_report:\n"
                    "                from copy import deepcopy\n"
                    "                gated = deepcopy(gated)\n"
                    "                for order in gated['market']:\n"
                    "                    if order and order[:2] == ['SELL', 'FERTILIZER']:\n"
                    "                        order[2] += 2\n"
                    '            return (gated, gate_report) if self.release else (proposed, report)')
            elif name == 'release_by_default':
                bridge_text = replace_once(bridge_text, 'self.release = release', 'self.release = True')
            elif name == 'copy_off_objects':
                bridge_text = replace_once(bridge_text,
                    'return (gated, gate_report) if self.release else (proposed, report)',
                    'return (gated, gate_report) if self.release else (dict(proposed), dict(report))')
            elif name == 'leak_probe':
                bridge_text = replace_once(bridge_text,
                    'stock.protect_operating_stock, stock.protect_feed_stock = original_fert, original_feed',
                    'pass  # deliberately fail to restore original objects')
            (tools/'stock_bridge.py').write_text(bridge_text)
            env = dict(os.environ, STOCKBRIDGE_SOURCE=str(source), STOCKBRIDGE_COMPOSED=str(runtime))
            command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + [str(test), 'StockBridgeTests.'+check]
            process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
            log = process.stdout + process.stderr
            killed = process.returncode != 0 and 'FAIL:' in log and 'ERROR:' not in log and 'Ran 1 test' in log
            results.append({'name': name, 'check': check, 'returncode': process.returncode,
                            'behaviorally_rejected': killed, 'log': log})
            if not killed:
                raise RuntimeError(f'mutant not behaviorally rejected: {name}\n{log}')
    return {'optimized': bool(sys.flags.optimize), 'count': len(results), 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--composed', type=Path, required=True)
    parser.add_argument('--gameplay', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.source.resolve(), args.composed.resolve(), gameplay=args.gameplay), indent=2))


if __name__ == '__main__':
    main()
