# SPDX-License-Identifier: Apache-2.0
"""Run exact recovered clone tests plus the current-runtime ABI suite.

All prerequisites are mandatory. Sources are copied into a temporary test
sandbox so the original donor suite needs no rewrite and no corpus can skip.
No source tree, archive, feature configuration, or external service is changed.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from port_current_runtime import git_blob, require, REFERENCE_RUNTIME

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--tapes', type=Path, required=True)
    args = parser.parse_args()
    identities = {
        'r04_fast_tape_clone.py': 'b7c1fd2f7f786c5dc5f8a3b9a7116815ea40607a',
        'test_r04_fast_tape_clone.py': 'a292131f3a9b47c00d74585ca2691beb07fbb44a',
    }
    for filename, expected in identities.items():
        require(git_blob((HERE / filename).read_bytes()) == expected,
                'donor identity mismatch: ' + filename)
    require(git_blob(args.runtime.read_bytes()) == REFERENCE_RUNTIME,
            'runtime moved; revalidate this port before continuing')
    require(git_blob(args.tapes.read_bytes()) == 'a43289b9cc5e34a2481fddf652762a7d92f427ef',
            'frozen tape identity mismatch')
    with tempfile.TemporaryDirectory(prefix='titan-fast-clone-') as directory:
        work = Path(directory)
        for filename in (*identities, 'port_current_runtime.py', 'test_current_runtime_port.py'):
            shutil.copyfile(HERE / filename, work / filename)
        shutil.copyfile(args.runtime, work / 'runtime.py')
        shutil.copyfile(args.tapes, work / 'r01_tapes.py')
        for optimized in (False, True):
            interpreter = [sys.executable, '-B'] + (['-O'] if optimized else [])
            commands = [
                interpreter + ['test_r04_fast_tape_clone.py'],
                interpreter + ['test_current_runtime_port.py', '--runtime', 'runtime.py',
                               '--tapes', 'r01_tapes.py'],
            ]
            for command in commands:
                subprocess.run(command, cwd=work, check=True, timeout=60)
    print(json.dumps({'ok': True, 'donor_tests_per_mode': 20, 'port_tests_per_mode': 14,
                      'modes': ['normal', 'optimized'], 'corpus_actions': 9347,
                      'current_method_arms': ['baseline', 'disabled', 'enabled'],
                      'runtime_blob': REFERENCE_RUNTIME,
                      'game_economics_tested': False, 'production_changed': False}, sort_keys=True))


if __name__ == '__main__':
    main()
