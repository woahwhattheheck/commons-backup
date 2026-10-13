#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compose opt-in edge-seeded pairs with exact PR10222 generated source.

Offline, additive source generation only. Does not change or replace the parent,
select a portfolio candidate, fetch source, compile, or modify a submission.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

PARENT_SHA256 = 'e91dfb7600f8ae9f4c1c65251d4fc8994221f98cc1929341148afb1746177cd4'


def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('Expected one compatible parent source anchor: ' + old[:70])
    return text.replace(old, new, 1)


def generate(raw: bytes, root: Path) -> bytes:
    if hashlib.sha256(raw).hexdigest() != PARENT_SHA256:
        raise ValueError('Expected the exact paired-waypoint parent source from PR10222')
    text = raw.decode('utf-8')
    text = once(text, '    struct Change { int d, left, right; Route next; };',
        '    bool cedarEdgeSeeds = setting("CEDAR_EDGE_SEEDS", 0) != 0;\n'
        '    std::size_t cedarSeedArcLimit = static_cast<std::size_t>(std::clamp(setting("CEDAR_SEED_ARCS", 2048), 0.0, 1000000.0));\n'
        '    long long cedarSeedScans = 0, cedarSeedCandidates = 0, cedarSeedSegmentChecks = 0;\n'
        '    long long cedarSeedTrials = 0, cedarSeedAccepted = 0;\n\n'
        '    struct Change { int d, left, right; Route next; };')
    method = (root / 'edge_seed_moves.inc').read_text(encoding='utf-8')
    anchor = '    bool cedarPairMoves(int t, int edge,'
    text = once(text, anchor, method + anchor)
    anchor = '            const int d = contributing[index].second;\n            Route pool;'
    text = once(text, anchor,
        '            const int d = contributing[index].second;\n'
        '            if (cedarEdgeSeeds && cedarEdgeSeedMoves(d, t, edge, adaptive, until, checks)) return true;\n'
        '            Route pool;')
    text = once(text, '            << ",\\"cedar_pair_checks\\":" << cedarChecks',
        '            << ",\\"cedar_seed_scans\\":" << cedarSeedScans\n'
        '            << ",\\"cedar_seed_candidates\\":" << cedarSeedCandidates\n'
        '            << ",\\"cedar_seed_segment_checks\\":" << cedarSeedSegmentChecks\n'
        '            << ",\\"cedar_seed_trials\\":" << cedarSeedTrials\n'
        '            << ",\\"cedar_seed_accepted\\":" << cedarSeedAccepted\n'
        '            << ",\\"cedar_pair_checks\\":" << cedarChecks')
    return text.encode('utf-8')


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    raw = generate(a.parent.read_bytes(), Path(__file__).resolve().parent)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('xb') as f:
        f.write(raw)
    print(json.dumps({'parent_sha256': PARENT_SHA256, 'bytes': len(raw),
                      'output': str(a.output), 'sha256': hashlib.sha256(raw).hexdigest()}, sort_keys=True))

if __name__ == '__main__':
    main()
