# SPDX-License-Identifier: Apache-2.0
"""Build a relocatable optional capital-route agent with the existing packager.

No dependency download or policy selection. Use existing Commons source files
and a fresh cloud output directory; the output is not a Kaggle submission.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_COMMIT = '3708a125158b6e39ffaf61b6e9e54b632eb2760e'
SOURCE_BLOBS = {
    'capital_routes.py': '00abee3c99641eb0ab1729fd80e6f9a5c783f373',
    'entry.py': '03c11c75941826b814002d3f067a67abcb1b0000',
}
SELL_SHA256 = '32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(destination: Path, *, source_root: Path = HERE) -> dict:
    source_root = source_root.resolve()
    base = source_root.parent
    for name, expected in SOURCE_BLOBS.items():
        raw = (source_root / name).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != expected:
            raise ValueError(f'Original HAZEL source differs: {name}')
    vendor = base / 'cloud-titan-composition/vendor/sell'
    if sha256(vendor / 'scheduler.py') != SELL_SHA256:
        raise ValueError('This export requires the unchanged frozen SELL dependency')
    files = {'main.py': source_root / 'main.py',
             'policy/entry.py': source_root / 'entry.py',
             'policy/capital_routes.py': source_root / 'capital_routes.py',
             'LICENSE': source_root / 'LICENSE', 'NOTICE': source_root / 'NOTICE'}
    for path in sorted(vendor.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            files['cloud-titan-composition/vendor/sell/' + path.relative_to(vendor).as_posix()] = path
    spec = {'schema_version': 1, 'label': 'HAZEL complete-route research agent / raw loader',
            'source_callable': 'agent',
            'provenance': {'original_source': SOURCE_COMMIT,
                'selection_status': 'Optional research control; shared selected/hosted policy unchanged',
                'license': 'Apache-2.0; retain original source attribution and licenses'},
            'files': {name: {'source': str(path), 'sha256': sha256(path)}
                      for name, path in files.items()}}
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    spec_path = destination / 'spec.json'
    spec_path.write_text(json.dumps(spec, sort_keys=True, indent=2)+'\n')
    module_spec = importlib.util.spec_from_file_location('capital_existing_pack', base / 'cloud-pack/pack.py')
    pack = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(pack)
    receipt = pack.build(spec_path, destination / 'bundle')
    pack.verify(destination / 'bundle', destination / 'extracted')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.destination), indent=2))
