# SPDX-License-Identifier: Apache-2.0
"""Run the canonical seed-repair composition gate and eight local mutants.

This reads source and compiles syntax only; no TitanAgent or game is executed.
Mutants are process-local functions and are never written into candidate files.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import platform
import sys
import unittest

import check_seed_prefix_composition as checks


def execute(case):
    suite = unittest.TestLoader().loadTestsFromTestCase(case)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=1).run(suite)
    return {'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
            'failures': len(result.failures), 'errors': len(result.errors),
            'failed_check_sample': [str(test) for test, _ in (result.failures + result.errors)[:8]]}


def main():
    baseline = execute(checks.SeedCompositionTests)
    report = {'python': platform.python_version(), 'optimize': sys.flags.optimize,
              'baseline': baseline, 'mutations': [],
              'runtime_git_blob': checks.RUNTIME_BLOB, 'repair_git_blob': checks.REPAIR_BLOB,
              'postimage_method_sha256': checks.AFTER_SHA256,
              'source_scope': 'byte-preserving exact-current-source transformation only',
              'full_current_router_executed': False, 'full_games_executed': 0,
              'natural_engagement_measured': False, 'production_changed': False}
    if not baseline['passed']:
        report['passed'] = False
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    original = checks.SeedCompositionTests.repair
    source = checks.SeedCompositionTests.source
    before = checks.SeedCompositionTests.before
    after = checks.SeedCompositionTests.after
    post = original(source)

    def unsafe_drift(data):
        try:
            return original(data)
        except ValueError:
            return data

    def no_repeat(data):
        if checks.section(data)[1] == after:
            raise ValueError('deliberate idempotence regression')
        return original(data)

    mutants = {
        'identity_not_repair': lambda data: data,
        'rewind_unrelated_peer_edits': lambda data: post,
        'textual_splice_without_target_authentication': lambda data: data.replace(before, after, 1),
        'drop_terminal_newlines': lambda data: original(data).rstrip(b'\r\n'),
        'erase_nonascii_peer_bytes': lambda data: original(data).decode().encode('ascii', 'ignore'),
        'reject_second_application': no_repeat,
        'accept_method_drift': unsafe_drift,
        'unreviewed_method_postimage': lambda data: original(data).replace(
            b"selected['market'][i+1:maximum]", b"selected['market'][i+1:]"),
    }
    for name, candidate in mutants.items():
        def setup(cls, transform=candidate):
            checks.SeedCompositionTests.setUpClass.__func__(cls)
            cls.repair = staticmethod(transform)
        case = type('Mutant_' + name, (checks.SeedCompositionTests,), {'setUpClass': classmethod(setup)})
        result = execute(case)
        report['mutations'].append({'name': name, 'rejected': not result['passed'], **result})
    report['passed'] = all(row['rejected'] for row in report['mutations'])
    report['support_git_blobs'] = {name: checks.blob((Path(__file__).parent / name).read_bytes())
                                  for name in ('check_seed_prefix_composition.py',
                                               'run_seed_composition_controls.py')}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
