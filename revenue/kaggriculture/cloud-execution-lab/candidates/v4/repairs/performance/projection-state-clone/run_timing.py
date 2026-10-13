# SPDX-License-Identifier: Apache-2.0
"""Serial alternating-order full-game timing; no filtered/retried samples."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--count', type=int, default=6)
    args = p.parse_args()
    if args.start < 0 or args.count < 1:
        raise SystemExit('Invalid repetition range')
    args.output.mkdir(parents=True, exist_ok=True)
    for rep in range(args.start, args.start + args.count):
        order = ('base', 'clone') if rep % 2 == 0 else ('clone', 'base')
        for arm in order:
            output = args.output / f'timing-{rep:02d}-{arm}.json'
            command = [sys.executable, *(['-O'] if sys.flags.optimize else []),
                       str(Path(__file__).with_name('run_native.py')), '--package', str(args.package),
                       '--arm', arm, '--seed', '9922999', '--seat', '0', '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            if result.returncode:
                raise RuntimeError(f'Timing run failed, not discarded: {output}\n{result.stderr}')
            data = json.loads(output.read_text())
            print(json.dumps({'replicate': rep, 'arm': arm, 'agent_wall_seconds': data['agent_wall_seconds'],
                              'agent_cpu_seconds': data['agent_cpu_seconds'], 'statuses': data['statuses']}), flush=True)


if __name__ == '__main__':
    main()
