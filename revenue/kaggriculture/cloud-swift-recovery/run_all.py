# SPDX-License-Identifier: Apache-2.0
"""Run the complete private retained-input suite in isolated Python processes.

Default: use the exact archived TITAN package contained in this private bundle.
--root may instead name an already-extracted prospective package. No package
files are patched by this runner. Python 3.12+ is required for safe tar filters.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile

INPUTS = {
    'TITAN-WIDEFIELD-ECON-consumer-20260908.zip':
        'c7cbcfda0f89b42c1d15d8de42867f0139648db1c794a26d6626ca4cf28e3af4',
    'TITAN-HARBOR-first-pair-99990002-20260908.zip':
        '864d74246c4accefe22a862e5477390cddc6bcb70cd4729ba517dbe04130dafa',
}
ARCHIVE_SHA = '820ed99e09ea22b09ab4e412742c654ad7330e266ab25d92fb1997cda91a18be'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, help='Optional prospective extracted package, not modified')
    parser.add_argument('--inputs', type=Path, default=Path(__file__).resolve().parent.parent/'inputs')
    parser.add_argument('--output', type=Path, required=True,
                        help='New result directory; an existing directory is not overwritten')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error('Use Python 3.12 or newer')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for filename, expected in INPUTS.items():
        actual = sha((args.inputs/filename).read_bytes())
        if actual != expected:
            raise ValueError(f'Input hash mismatch: {filename}')
    scripts = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='titan-swift-inputs-') as temp:
        work = Path(temp)
        with zipfile.ZipFile(args.inputs/'TITAN-WIDEFIELD-ECON-consumer-20260908.zip') as package_zip:
            archive_data = package_zip.read('source/exports/titan-current.tar.gz')
        if sha(archive_data) != ARCHIVE_SHA:
            raise ValueError('Canonical archive hash mismatch')
        archive = work/'package.tar.gz'
        archive.write_bytes(archive_data)
        frozen = work/'frozen'
        frozen.mkdir()
        with tarfile.open(archive, 'r:gz') as tar:
            members = tar.getmembers()
            if any(not (member.isfile() or member.isdir()) for member in members):
                raise ValueError('Unexpected non-file archive member')
            if len({member.name for member in members}) != len(members):
                raise ValueError('Duplicate archive member')
            tar.extractall(frozen, filter='data')
        source = json.loads((frozen/'SOURCE.json').read_text())
        for path, info in source['runtime'].items():
            if sha((frozen/path).read_bytes()) != info['sha256']:
                raise ValueError(f'Frozen runtime member mismatch: {path}')
        root = args.root.resolve() if args.root else frozen
        with zipfile.ZipFile(args.inputs/'TITAN-HARBOR-first-pair-99990002-20260908.zip') as trace_zip:
            for seat in (0, 1):
                filename = f'submitted7b58-99990002-s{seat}.jsonl.gz'
                (work/filename).write_bytes(trace_zip.read('results-shard0/'+filename))
        executions = []
        tasks = [(name, seat) for seat in (0, 1)
                 for name in ('profile_retained', 'check_recovery_contract')]
        tasks.append(('check_discrimination', 0))
        for name, seat in tasks:
            report_path = output/f'{name}-s{seat}.json'
            command = [sys.executable, '-B', str(scripts/f'{name}.py'),
                       '--root', str(root), '--trace', str(work/f'submitted7b58-99990002-s{seat}.jsonl.gz'),
                       '--seat', str(seat), '--output', str(report_path)]
            print(f'Running {name}, retained seat {seat}', flush=True)
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
            (output/f'{name}-s{seat}.stdout.txt').write_text(result.stdout)
            (output/f'{name}-s{seat}.stderr.txt').write_text(result.stderr)
            executions.append({'script': name, 'seat': seat, 'returncode': result.returncode,
                               'report': report_path.name, 'command': command})
        report = {'schema': 1, 'new_games': 0, 'reference_archive_sha256': ARCHIVE_SHA,
                  'reference_runtime_members_verified': len(source['runtime']),
                  'candidate_root_supplied': args.root is not None,
                  'candidate_runtime_sha256': sha((root/'titan_runtime.py').read_bytes()),
                  'candidate_frozen_selected_sha256': sha((root/'frozen_selected.py').read_bytes()),
                  'candidate_config_sha256': sha((root/'TITAN-CONFIG.json').read_bytes()),
                  'package_modified_by_runner': False, 'executions': executions,
                  'passed': all(run['returncode'] == 0 for run in executions)}
        (output/'run-summary.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
