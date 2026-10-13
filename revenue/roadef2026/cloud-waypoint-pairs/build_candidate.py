#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Add the paired-waypoint neighborhood to the pinned fleet kernel, offline.

Writes ONE new source file. Existing kernel, runtime, portfolio, incumbent, and
submission files are not modified. Build the generated source as the candidate
with the already-installed RapidJSON include path. No download or compiler is
invoked here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

BASE_COMMIT = '2885d176373c33410148829fef93c310c3752c0b'
BASE_BLOB = '9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df'

def blob(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()

def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('Expected exactly one compatible source anchor: ' + old[:70])
    return text.replace(old, new, 1)

def generate(raw: bytes, root: Path) -> bytes:
    if blob(raw) != BASE_BLOB:
        raise ValueError('Base differs from the recorded fleet kernel; reconcile explicitly')
    text = raw.decode('utf-8')
    header = (root / 'ordered_pairs.hpp').read_text(encoding='utf-8').replace('#pragma once\n', '')
    method = (root / 'pair_moves.inc').read_text(encoding='utf-8')
    text = once(text, 'class Solver {', header + '\nclass Solver {')
    text = once(text, '    struct Change { int d, left, right; Route next; };',
        '    bool cedarEnabled = setting("CEDAR_PAIRS", 1) != 0;\n'
        '    std::size_t cedarWidth = static_cast<std::size_t>(std::clamp(setting("CEDAR_PAIR_WIDTH", 16), 2.0, 128.0));\n'
        '    std::size_t cedarTrialLimit = static_cast<std::size_t>(std::clamp(setting("CEDAR_PAIR_TRIALS", 4096), 1.0, 1000000.0));\n'
        '    long long cedarChecks = 0, cedarAccepted = 0;\n\n'
        '    struct Change { int d, left, right; Route next; };')
    text = once(text, '    void writeSolution() const {', method + '    void writeSolution() const {')
    text = once(text, '            if (accepted > oldAccepted) stalled = 0; else ++stalled;',
        '            if (accepted == oldAccepted && !finished() && !contributing.empty())\n'
        '                cedarPairMoves(t, e, contributing, adaptive);\n'
        '            if (accepted > oldAccepted) stalled = 0; else ++stalled;')
    text = once(text, '            << ",\\"ranked_candidates\\":" << rankedCandidates',
        '            << ",\\"cedar_pair_checks\\":" << cedarChecks\n'
        '            << ",\\"cedar_pair_accepted\\":" << cedarAccepted\n'
        '            << ",\\"ranked_candidates\\":" << rankedCandidates')
    return text.encode('utf-8')

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    raw = args.base.read_bytes()
    generated = generate(raw, Path(__file__).resolve().parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as f:
        f.write(generated)
    print(json.dumps({'base_commit': BASE_COMMIT, 'base_blob': blob(raw),
                      'output': str(args.output), 'bytes': len(generated),
                      'sha256': hashlib.sha256(generated).hexdigest(),
                      'blob': blob(generated)}, sort_keys=True))

if __name__ == '__main__':
    main()
