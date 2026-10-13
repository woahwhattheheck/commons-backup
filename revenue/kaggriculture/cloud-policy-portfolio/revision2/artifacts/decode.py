# SPDX-License-Identifier: Apache-2.0
"""Decode the adjacent manifest's text parts to exact archive bytes, offline."""
import argparse
import base64
import hashlib
import json
from pathlib import Path


def decode(directory, output):
    manifest = json.loads((directory / 'MANIFEST.json').read_text())
    output.mkdir(parents=True, exist_ok=True)
    result = []
    for item in manifest['archives']:
        chunks = []
        for part in item['parts']:
            path = directory / part['name']
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Part path leaves archive directory')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != part['sha256']:
                raise ValueError('Part checksum differs')
            chunks.append(raw)
        raw = base64.b64decode(b''.join(chunks), validate=True)
        if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Archive checksum differs')
        target = output / item['name']
        if not target.resolve().is_relative_to(output.resolve()) or target.exists():
            raise ValueError('Use new output paths within the target directory')
        target.write_bytes(raw)
        result.append({'name': item['name'], 'bytes': len(raw), 'sha256': item['sha256']})
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(decode(Path(__file__).resolve().parent, a.output.resolve()), indent=2))
