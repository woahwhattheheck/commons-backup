# SPDX-License-Identifier: MIT
"""Verify and decode the committed 80-game action evidence; executes no policy."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import lzma
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKED_SHA256 = 'f4ad39e2aad885ae563d8119ccf95b499a81b33585b2adaa4dc0e7f424b05ea1'


def decode(path: Path) -> dict:
    packed = base64.b64decode(b''.join(path.read_bytes().split()), validate=True)
    if hashlib.sha256(packed).hexdigest() != PACKED_SHA256:
        raise ValueError('Action evidence bytes do not match the published receipt')
    unpacker = lzma.LZMADecompressor(memlimit=128 * 1024 * 1024)
    raw = unpacker.decompress(packed, max_length=1_000_001)
    if not unpacker.eof or unpacker.unused_data or len(raw) > 1_000_000:
        raise ValueError('Invalid or oversized action evidence')
    packet = json.loads(raw)
    actions, records = packet['actions'], packet['runs']
    if len(records) != 80:
        raise ValueError('Expected exactly 80 scored game records')
    seen = set()
    for row in records:
        key = tuple(row[k] for k in ('phase', 'seed', 'opponent', 'seat', 'arm'))
        if key in seen or len(row['sequence']) != 719:
            raise ValueError('Duplicate or incomplete scored game')
        seen.add(key)
        if any(type(i) is not int or not 0 <= i < len(actions) for i in row['sequence']):
            raise ValueError('Invalid action dictionary index')
        actual = [actions[i] for i in row['sequence']]
        encoded = json.dumps(actual, separators=(',', ':'), sort_keys=True,
                             ensure_ascii=False).encode()
        if hashlib.sha256(encoded).hexdigest() != row['action_trace_sha256']:
            raise ValueError(f'Action trace hash mismatch: {key}')
    return packet


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=HERE / 'ACTION-TRACES.json.xz.b64')
    parser.add_argument('--output', type=Path, help='Optional new JSON output; never overwritten')
    args = parser.parse_args()
    packet = decode(args.input)
    if args.output:
        with args.output.open('x') as handle:
            json.dump(packet, handle, separators=(',', ':'), sort_keys=True)
            handle.write('\n')
    print(json.dumps({'verified_games': len(packet['runs']),
                      'unique_actions': len(packet['actions']),
                      'packed_sha256': PACKED_SHA256}))
