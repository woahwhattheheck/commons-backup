# SPDX-License-Identifier: Apache-2.0
"""Exact current-ABI repair for SpatialTempo's two HIRE boundary scans.

This is a source transformer for the single V4 assembler, not a controller or
runtime installer. No feature, action vector, witness or market order is changed.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

PREIMAGE_SHA256 = '9efe9588013b97452813f43dcfe0f5f2c311c2668b5ad64e53f173b7c457a60e'
OLD = """        # HIRE happens after unit moves. Existing positions choose the spawn
        # corner, so every worker must rejoin before the next hiring turn.
        if any(a and a[0]=='HIRE' for a in selected.get('market',[])):return selected
        for step in range(now,end):
            if any(a and a[0]=='HIRE' for a in route[step].get('market',[])):
                end=step;break
"""
NEW = """        # HIRE happens after unit moves. Existing positions choose the spawn
        # corner, so every worker must rejoin before the next executable hire.
        # Raw slots consume the engine cap even when their order is a no-op.
        raw_market_limit=self.configuration.get('maxMarketOrdersPerTurn',10)
        if type(raw_market_limit) is not int:return selected
        market_limit=max(1,raw_market_limit)
        if any(a and a[0]=='HIRE' for a in selected.get('market',[])[:market_limit]):return selected
        for step in range(now,end):
            if any(a and a[0]=='HIRE' for a in route[step].get('market',[])[:market_limit]):
                end=step;break
"""


def repaired_source(source: bytes) -> bytes:
    """Return one deterministic postimage; reject drift rather than overwrite it."""
    if not isinstance(source, bytes):
        raise TypeError('source must be bytes')
    if hashlib.sha256(source).hexdigest() != PREIMAGE_SHA256:
        raise ValueError('spatial_tempo.py source changed; rebase the two-scan repair')
    text = source.decode('utf-8')
    if text.count(OLD) != 1:
        raise ValueError('expected exactly one current transform boundary')
    output = text.replace(OLD, NEW, 1).encode('utf-8')
    compile(output, 'spatial_tempo.py', 'exec')
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('use a separate staging output; this tool never edits production in place')
    result = repaired_source(args.source.read_bytes())
    # Exclusive creation prevents accidental replacement of another staged port.
    with args.output.open('xb') as handle:
        handle.write(result)
    print(hashlib.sha256(result).hexdigest())


if __name__ == '__main__':
    main()
