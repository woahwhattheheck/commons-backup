# SPDX-License-Identifier: Apache-2.0
"""Build one explicit T13 arm; preserve the pinned SELL dependency closure."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
EXPECTED = '32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9'


def verify_sources():
    vendor = HERE / 'vendor/sell'
    if not vendor.is_dir():
        vendor = HERE.parent / 'cloud-titan-composition/vendor/sell'
    if hashlib.sha256((vendor / 'scheduler.py').read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('The build expects the frozen SELL source')
    freeze = json.loads((HERE / 'SOURCE-FREEZE.json').read_text())
    for name, expected in freeze['runtime'].items():
        if name.startswith('policy/'):
            path = HERE / name.removeprefix('policy/')
        elif name.startswith('vendor/sell/'):
            path = vendor / name.removeprefix('vendor/sell/')
        else:
            raise ValueError('Unexpected source namespace')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Frozen source mismatch: {name}')
    return vendor


def build(destination, arm='seed'):
    vendor = verify_sources()
    entry, dependency = {'seed': ('seed_main.py', 'seed_budget.py'),
                         'weed': ('main.py', 'recovery.py')}[arm]
    files = {'main.py': (HERE / entry).read_bytes(),
             dependency: (HERE / dependency).read_bytes()}
    for p in sorted(vendor.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
            files[str(Path('vendor/sell') / p.relative_to(vendor))] = p.read_bytes()
    for name in ('README.md', 'NOTICE.md', 'SOURCE-FREEZE.json'):
        if (HERE / name).is_file():
            files[name] = (HERE / name).read_bytes()
    manifest = {'arm': arm, 'files': {p: hashlib.sha256(b).hexdigest() for p, b in files.items()}}
    files['BUNDLE-MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, body in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(body); info.mode = 0o644; info.mtime = 0
            archive.addfile(info, io.BytesIO(body))
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(gzip.compress(stream.getvalue(), mtime=0))
    return dict(manifest, archive_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                bytes=destination.stat().st_size)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=['seed', 'weed'], default='seed')
    parser.add_argument('--output', type=Path, default=Path('t13-seed.tar.gz'))
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.arm), indent=2))
