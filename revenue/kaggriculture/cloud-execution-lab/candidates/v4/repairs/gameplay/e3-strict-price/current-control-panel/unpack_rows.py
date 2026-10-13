# SPDX-License-Identifier: Apache-2.0
"""Expand the complete, losslessly columnar-encoded E3 positive-row evidence."""
from __future__ import annotations
import argparse
import base64
from copy import deepcopy
import hashlib
import json
import lzma
from pathlib import Path

ENCODED_SHA256 = '74582705c4eacebb7339476ffd0b788d07e83bbeac9078a9e0d2f4c277d4f171'
PACKET_SHA256 = '7daaa8cdf02a0807aeebe4a376e65fa1888737680cfd358f61083802e94798a3'
ROWS_SHA256 = '0c5c9caf89c5fa8d45bac5e5b67de7a5973b2496049d0d8a86e212272c3fbcfd'


def expand(encoded: bytes) -> bytes:
    if hashlib.sha256(encoded).hexdigest() != ENCODED_SHA256:
        raise ValueError('Encoded evidence hash mismatch')
    compressed = base64.b64decode(b''.join(encoded.split()), validate=True)
    packet_bytes = lzma.decompress(compressed, memlimit=128 * 1024 * 1024)
    if hashlib.sha256(packet_bytes).hexdigest() != PACKET_SHA256:
        raise ValueError('Decoded evidence packet hash mismatch')
    packet = json.loads(packet_bytes)
    if packet['schema'] != 'titan.e3.columnar.v1':
        raise ValueError('Unsupported evidence schema')
    columns = packet['columns']
    if packet['row_count'] != 10655 or len(columns) != 8 or any(len(c) != 10655 for c in columns):
        raise ValueError('Incomplete positive-row evidence')
    result = []
    for seed_offset, seat, step, stage, index, product, prefix_id, diagnostic_id in zip(*columns):
        if not 0 <= seed_offset < 8 or seat not in (0, 1):
            raise ValueError('Unexpected panel cell')
        prefix = deepcopy(packet['prefixes'][prefix_id])
        day, hour = divmod(step, 24)
        row = {'seed': packet['seed_base'] + seed_offset, 'seat': seat, 'step': step,
               'day': day, 'hour': hour, 'stage': 'ABCDR'[stage],
               'product': ('WHEAT', 'FERTILIZER')[product],
               'quantity_requested': int(prefix[index][2]), 'market_index': index,
               'executable_prefix': prefix,
               'diagnostics': deepcopy(packet['diagnostics'][diagnostic_id])}
        if (row['day'], row['hour']) != divmod(row['step'], 24):
            raise ValueError('Row clock mismatch')
        order = row['executable_prefix'][row['market_index']]
        if order[:2] != ['SELL', row['product']] or int(order[2]) != row['quantity_requested']:
            raise ValueError('Row does not describe its original raw-prefix slot')
        result.append(json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n')
    data = ''.join(result).encode('utf-8')
    if hashlib.sha256(data).hexdigest() != ROWS_SHA256 or packet['expanded_jsonl_sha256'] != ROWS_SHA256:
        raise ValueError('Expanded JSONL hash mismatch')
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(__file__).with_name('RESIDUAL-ROWS.json.xz.b64'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = expand(args.input.read_bytes())
    with args.output.open('xb') as out:
        out.write(data)
    print(json.dumps({'rows': 10655, 'bytes': len(data), 'sha256': ROWS_SHA256}))


if __name__ == '__main__':
    main()
