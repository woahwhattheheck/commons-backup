# SPDX-License-Identifier: Apache-2.0
"""Compact full observation traces as lossless JSON patches; offline CLI."""
import argparse
import copy
import gzip
import hashlib
import json
import lzma
from pathlib import Path


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def changes(before, after, path=()):
    if type(before) is not type(after):
        return [['set', list(path), after]]
    if isinstance(after, dict):
        result = [['del', list(path + (k,))] for k in before if k not in after]
        for k, value in after.items():
            result += changes(before[k], value, path + (k,)) if k in before else [['set', list(path + (k,)), value]]
        return result
    if isinstance(after, list) and len(before) == len(after):
        return [operation for i, (a, b) in enumerate(zip(before, after)) for operation in changes(a, b, path + (i,))]
    return [] if before == after else [['set', list(path), after]]


def apply(value, patch):
    for operation in patch:
        op, path = operation[:2]
        if not path:
            value = copy.deepcopy(operation[2])
            continue
        parent = value
        for key in path[:-1]:
            parent = parent[key]
        if op == 'del':
            del parent[path[-1]]
        elif op == 'set':
            parent[path[-1]] = copy.deepcopy(operation[2])
        else:
            raise ValueError('Unknown patch operation')
    return value


def pack(directory, output):
    members, unique = {}, {}
    for path in sorted(directory.rglob('*.jsonl.gz')):
        previous, deltas = None, []
        stream_hash = hashlib.sha256()
        with gzip.open(path, 'rt') as stream:
            for line in stream:
                row = json.loads(line)
                stream_hash.update(encoded(row) + b'\n')
                deltas.append(changes(previous, row))
                previous = row
        key = stream_hash.hexdigest()
        members[str(path.relative_to(directory))] = {'semantic_sha256': key, 'rows': len(deltas),
            'original_gzip_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        if key not in unique:
            # Check every lossless reconstruction before storing its canonical stream.
            current, checked = None, hashlib.sha256()
            for delta in deltas:
                current = apply(current, delta)
                checked.update(encoded(current) + b'\n')
            if checked.hexdigest() != key:
                raise ValueError('Trace reconstruction differs')
            unique[key] = deltas
    payload = {'schema_version': 1, 'members': members, 'streams': unique}
    output.write_bytes(lzma.compress(encoded(payload), preset=6))
    return {'files': len(members), 'unique_streams': len(unique), 'observations': sum(m['rows'] for m in members.values()),
        'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'bytes': output.stat().st_size,
        'format': 'XZ compressed JSON patch streams; preserves every semantic observation/action/cash row',
        'gzip_container': 'original gzip hashes retained; decoder writes canonical JSONL, not original gzip metadata'}


def unpack(archive, output):
    payload = json.loads(lzma.decompress(archive.read_bytes()))
    output.mkdir(parents=True, exist_ok=True)
    for name, item in payload['members'].items():
        path = output / Path(name).with_suffix('')
        if not path.resolve().is_relative_to(output.resolve()) or path.exists():
            raise ValueError('Use new output paths within the target directory')
        path.parent.mkdir(parents=True, exist_ok=True)
        current, checked = None, hashlib.sha256()
        with path.open('wb') as target:
            for delta in payload['streams'][item['semantic_sha256']]:
                current = apply(current, delta)
                data = encoded(current) + b'\n'
                checked.update(data)
                target.write(data)
        if checked.hexdigest() != item['semantic_sha256']:
            raise ValueError('Decoded trace differs from manifest')
    return len(payload['members'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['pack', 'unpack'])
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    print(json.dumps(pack(a.input, a.output) if a.operation == 'pack' else unpack(a.input, a.output), indent=2))
