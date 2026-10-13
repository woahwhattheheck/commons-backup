# SPDX-License-Identifier: Apache-2.0
"""Build the crop-choice experiment from the exact submitted V4 archive."""
import argparse
import hashlib
import gzip
import io
import json
from pathlib import Path
import shutil
import tarfile

BASE_SHA = '4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b'


def entry_bytes(max_active=4):
    if max_active not in (4, 8, 12):
        raise ValueError('supported capacity profiles are4,8,12')
    raw = (Path(__file__).resolve().parent/'choice_entry.py').read_bytes()
    anchor = b'_CHOICE = CropChoice(market_price)'
    if raw.count(anchor) != 1:
        raise ValueError('wrapper profile seam changed')
    return raw if max_active == 4 else raw.replace(anchor,
        f'_CHOICE = CropChoice(market_price, max_active={max_active})'.encode())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--tar', type=Path)
    p.add_argument('--max-active', type=int, choices=[4,8,12], default=4)
    args = p.parse_args()
    if args.out.exists():
        p.error('output directory must be new')
    if hashlib.sha256(args.baseline.read_bytes()).hexdigest() != BASE_SHA:
        raise ValueError('expected exact submitted V4 archive')
    args.out.mkdir(parents=True)
    with tarfile.open(args.baseline) as tar:
        tar.extractall(args.out, filter='data')
    (args.out/'main.py').rename(args.out/'baseline_main.py')
    here = Path(__file__).resolve().parent
    (args.out/'main.py').write_bytes(entry_bytes(args.max_active))
    shutil.copyfile(here/'selective_carrot.py', args.out/'selective_carrot.py')
    files = {str(f.relative_to(args.out)).replace('\\', '/'): hashlib.sha256(f.read_bytes()).hexdigest()
             for f in sorted(args.out.rglob('*')) if f.is_file()}
    receipt = {'base_archive_sha256': BASE_SHA, 'intervention': 'selective_age3_carrot',
               'max_active': args.max_active, 'minimum_edge': 12, 'receipt_discount': .8,
               'files': files}
    if args.tar:
        if args.tar.exists():
            raise ValueError('archive output must be new')
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w') as tar:
            for name in sorted(files):
                content = (args.out/name).read_bytes()
                info = tarfile.TarInfo(name); info.size = len(content); info.mode = 0o644
                tar.addfile(info, io.BytesIO(content))
        args.tar.parent.mkdir(parents=True, exist_ok=True)
        with args.tar.open('wb') as f, gzip.GzipFile(filename='', mode='wb', fileobj=f, mtime=0) as z:
            z.write(raw.getvalue())
        receipt['candidate_archive_sha256'] = hashlib.sha256(args.tar.read_bytes()).hexdigest()
    (args.out.parent/(args.out.name+'-manifest.json')).write_text(json.dumps(receipt, indent=2))
    print(json.dumps({'out': str(args.out.resolve()), 'files': len(files)}))


if __name__ == '__main__':
    main()
