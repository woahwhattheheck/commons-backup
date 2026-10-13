"""Lossless, dependency-free T05 evidence packing and restoration.

Repeated JSON subtrees are interned before XZ compression. No pickles, dynamic
imports, eval, or executable serialization. Restored bytes are hash checked.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import lzma
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pack(files, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    nodes, lookup, roots, manifest = [], {}, {}, {}
    def intern(value):
        if isinstance(value, dict):
            node = ('dict', tuple((k, intern(v)) for k, v in value.items()))
        elif isinstance(value, list):
            node = ('list', tuple(intern(v) for v in value))
        else:
            node = (type(value).__name__, value)
        if node not in lookup:
            lookup[node] = len(nodes)
            nodes.append(node)
        return lookup[node]
    for name, path in sorted(files.items()):
        raw = Path(path).read_bytes()
        if name.endswith('.json'):
            value = json.loads(raw)
            if (json.dumps(value, indent=2) + '\n').encode() != raw:
                raise ValueError(f'Noncanonical JSON: {name}')
            kind = 'json'
        else:
            value, kind = raw.decode('utf-8'), 'text'
        roots[name] = {'node': intern(value), 'kind': kind}
        manifest[name] = {'bytes': len(raw), 'sha256': digest(raw)}
    document = {'schema': 't05-evidence-dag/v1', 'nodes': nodes,
                'roots': roots, 'files': manifest}
    compressed = lzma.compress(json.dumps(document, separators=(',', ':')).encode())
    output.mkdir(parents=True)
    parts = []
    for index, start in enumerate(range(0, len(compressed), 12000)):
        data = compressed[start:start + 12000]
        name = f'evidence.xz.part{index:02d}'
        (output / name).write_bytes(data)
        parts.append({'path': name, 'bytes': len(data), 'sha256': digest(data)})
    index = {'schema': document['schema'], 'compression': 'xz',
             'bytes': len(compressed), 'sha256': digest(compressed),
             'parts': parts, 'files': manifest}
    (output / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    return index


def unpack(source, output):
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError(output)
    index = json.loads((source / 'index.json').read_text())
    chunks = []
    for part in index['parts']:
        if Path(part['path']).name != part['path']:
            raise ValueError('Invalid evidence part path')
        raw = (source / part['path']).read_bytes()
        if len(raw) != part['bytes'] or digest(raw) != part['sha256']:
            raise ValueError(f"Changed part: {part['path']}")
        chunks.append(raw)
    compressed = b''.join(chunks)
    if len(compressed) != index['bytes'] or digest(compressed) != index['sha256']:
        raise ValueError('Changed evidence archive')
    document = json.loads(lzma.decompress(compressed))
    if document['schema'] != 't05-evidence-dag/v1' or document['files'] != index['files']:
        raise ValueError('Changed evidence manifest')
    nodes = []
    for kind, value in document['nodes']:
        if kind == 'dict':
            value = {k: nodes[v] for k, v in value}
        elif kind == 'list':
            value = [nodes[v] for v in value]
        elif kind not in ('str', 'int', 'float', 'bool', 'NoneType'):
            raise ValueError('Unknown evidence node type')
        nodes.append(value)
    restored = {}
    for name, root in document['roots'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Invalid evidence output path')
        value = nodes[root['node']]
        raw = ((json.dumps(value, indent=2) + '\n').encode()
               if root['kind'] == 'json' else value.encode('utf-8'))
        expected = index['files'][name]
        if len(raw) != expected['bytes'] or digest(raw) != expected['sha256']:
            raise ValueError(f'Changed restored evidence: {name}')
        restored[name] = raw
    for name, raw in restored.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return {'restored_files': len(restored), 'restored_bytes': sum(map(len, restored.values())),
            'archive_sha256': digest(compressed)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('evidence'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(unpack(args.source, args.output), indent=2))
