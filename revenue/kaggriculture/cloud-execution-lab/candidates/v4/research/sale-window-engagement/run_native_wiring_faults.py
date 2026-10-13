# SPDX-License-Identifier: Apache-2.0
"""Assertion-detected semantic controls for native sale-window wiring.

Each scratch mutation must run the ordinary complete suite and fail an
assertion; syntax/import failures and unexpected exits are not counted as kills.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

FAULTS = {
    'swallow_deadline_base_exception': ("except Exception as error:", "except BaseException as error:"),
    'permit_unit_mutation': ("raise ValueError('Non-market action fields changed')", "pass  # faulty unit gate"),
    'permit_economic_prefix_edits': ("raise ValueError('Inherited economic/funding prefix changed')", "pass  # faulty prefix gate"),
    'permit_clipped_suffix_edits': ("raise ValueError('Clipped raw suffix changed')", "pass  # faulty suffix gate"),
    'run_optional_policy_during_fallback': ("if agent_self.diagnostics.get('status') != 'completed':", "if agent_self.diagnostics.get('status') == '__never__':"),
    'call_proposal_returned_even_when_discarded': ("returned == frame['_proposed']", "True"),
    'expose_caller_owned_inputs': ("self.policy(deepcopy(obs), deepcopy(cfg), deepcopy(incumbent))", "self.policy(obs, cfg, incumbent)"),
    'copy_final_return_object': ("return returned  # Observation only: exact native return object.", "return deepcopy(returned)  # faulty outer transform"),
}


def run(output):
    here = Path(__file__).resolve().parent
    source = (here / 'native_sale_window.py').read_text()
    tests = (here / 'test_native_sale_window.py').read_text()
    report = {'schema': 'titan.sale_window.native_wiring_faults.v1',
              'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'test_sha256': hashlib.sha256(tests.encode()).hexdigest(), 'runs': []}
    for optimized in (False, True):
        options = ['-O'] if optimized else []
        control = subprocess.run([sys.executable, *options, str(here / 'test_native_sale_window.py')],
                                 capture_output=True, text=True, timeout=30)
        if control.returncode != 0:
            raise RuntimeError('Unmutated control failed: ' + control.stdout + control.stderr)
        report['runs'].append({'optimized': optimized, 'fault': 'unmutated', 'returncode': 0,
                               'log': control.stdout + control.stderr})
        for name, (old, new) in FAULTS.items():
            if source.count(old) != 1:
                raise ValueError('Fault seam is not unique: ' + name)
            with tempfile.TemporaryDirectory(prefix='native-sale-window-fault-') as tmp:
                root = Path(tmp)
                (root / 'native_sale_window.py').write_text(source.replace(old, new, 1))
                (root / 'test_native_sale_window.py').write_text(tests)
                result = subprocess.run([sys.executable, *options, str(root / 'test_native_sale_window.py')],
                                        capture_output=True, text=True, timeout=30)
            log = result.stdout + result.stderr
            assertion_rejected = (result.returncode == 1 and 'AssertionError' in log
                                  and 'FAILED (' in log and 'SyntaxError' not in log
                                  and 'ModuleNotFoundError' not in log)
            report['runs'].append({'optimized': optimized, 'fault': name,
                                   'returncode': result.returncode,
                                   'assertion_rejected': assertion_rejected, 'log': log})
            if not assertion_rejected:
                output.write_text(json.dumps(report, indent=2) + '\n')
                raise RuntimeError('Fault did not fail by assertion: ' + name)
    report['assertion_rejected'] = sum(r.get('assertion_rejected', False) for r in report['runs'])
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'controls': 2, 'faults_per_mode': len(FAULTS),
                      'assertion_rejected': report['assertion_rejected']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
