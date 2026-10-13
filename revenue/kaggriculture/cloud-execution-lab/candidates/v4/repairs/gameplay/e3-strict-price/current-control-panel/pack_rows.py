# SPDX-License-Identifier: Apache-2.0
"""Create a lossless columnar JSON/XZ transport of the required census fields."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import lzma
from pathlib import Path


def pack(source: bytes) -> tuple[bytes, bytes]:
    prefixes, diagnostics, prefix_ids, diagnostic_ids = [], [], {}, {}
    columns = [[] for _ in range(8)]
    selected = []
    for line in source.splitlines():
        row = json.loads(line)
        row['diagnostics'] = {key: value for key, value in row['diagnostics'].items()
                              if key in ('operating_stock', 'feed_stock', 'early_capital')}
        selected.append(row)
        for key, values, lookup in (('executable_prefix', prefixes, prefix_ids),
                                    ('diagnostics', diagnostics, diagnostic_ids)):
            value = json.dumps(row[key], separators=(',', ':'))
            if value not in lookup:
                lookup[value] = len(values)
                values.append(row[key])
        values = [row['seed'] - 2611151001, row['seat'], row['step'],
                  'ABCDR'.index(row['stage']), row['market_index'],
                  ('WHEAT', 'FERTILIZER').index(row['product']),
                  prefix_ids[json.dumps(row['executable_prefix'], separators=(',', ':'))],
                  diagnostic_ids[json.dumps(row['diagnostics'], separators=(',', ':'))]]
        for column, value in zip(columns, values):
            column.append(value)
    expanded = ''.join(json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n'
                       for row in selected).encode()
    packet = {'schema': 'titan.e3.columnar.v1', 'seed_base': 2611151001,
              'row_count': len(selected), 'prefixes': prefixes, 'diagnostics': diagnostics,
              'column_names': ['seed_offset', 'seat', 'step', 'stage_id', 'market_index',
                               'product_id', 'prefix_id', 'diagnostic_id'],
              'columns': columns, 'expanded_jsonl_sha256': hashlib.sha256(expanded).hexdigest()}
    raw = json.dumps(packet, separators=(',', ':'), allow_nan=False).encode()
    encoded = base64.b64encode(lzma.compress(raw, preset=9)) + b'\n'
    return raw, encoded


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    raw, encoded = pack(args.source.read_bytes())
    with args.output.open('xb') as out:
        out.write(encoded)
    print(json.dumps({'encoded_sha256': hashlib.sha256(encoded).hexdigest(),
                      'packet_sha256': hashlib.sha256(raw).hexdigest()}))
