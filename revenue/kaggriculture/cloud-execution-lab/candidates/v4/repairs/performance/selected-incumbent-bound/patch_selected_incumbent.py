# SPDX-License-Identifier: Apache-2.0
"""Compose strict incumbent pruning without changing MarketPath or E18 rules.

Only the exact native optimizer blob is accepted. Output is candidate source;
this tool never writes the source path or production archive.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

SOURCE_BLOB = 'f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3'


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def transform(data: bytes) -> bytes:
    if git_blob(data) != SOURCE_BLOB:
        raise ValueError('source differs from reviewed native selected_sell_core: ' + git_blob(data))
    source = data.decode('utf-8')
    before = """            if capacity_ok and not capacity_ok(plan):continue
            scores=[first_score]
"""
    after = """            if capacity_ok and not capacity_ok(plan):continue
            # Preserve the physical callback sequence. Once it passes, this
            # partial minimum is an upper bound on the final primary key.
            # Strict '<' preserves sum/first-quantity ties; round exactly as
            # the final key does, including sub-rounding-unit differences.
            if round(first_score[0]-baseline[0][0],8) < best_key[0]:
                continue
            scores=[first_score]
"""
    old = """                if score[0]-b[0] <= 0:
                    competitive=False
"""
    new = """                delta=score[0]-b[0]
                if delta <= 0 or round(delta,8) < best_key[0]:
                    competitive=False
"""
    if source.count(before) != 1 or source.count(old) != 1:
        raise ValueError('strict optimizer anchors are not unique')
    return source.replace(before, after, 1).replace(old, new, 1).encode('utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('output must be a distinct candidate file')
    result = transform(args.source.read_bytes())
    with args.output.open('xb') as stream:
        stream.write(result)
    print(git_blob(result))


if __name__ == '__main__':
    main()
