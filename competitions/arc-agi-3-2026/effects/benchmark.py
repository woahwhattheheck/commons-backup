"""Held-out synthetic benchmark for effect taxonomy invariance.

Cases are generated from seeds not used by the hand-authored unit fixtures. The benchmark
measures wiring/generalization of the deterministic taxonomy only; it is not an ARC score.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from random import Random

from factorizer import factor_pair

FAMILIES = ("NO_CHANGE", "MOTION", "SPAWN", "DESPAWN", "RECOLOR", "TOPOLOGY", "UI", "CAMERA", "COMPOUND")


def _scene(seed: int):
    rng = Random(seed)
    bg = (0, 9)[seed % 2]
    colors = [c for c in range(1, 9) if c != bg]
    rng.shuffle(colors)
    c1, c2, c3, c4 = colors[:4]
    g = [[bg] * 12 for _ in range(12)]
    oy = seed % 2
    a = ((2, 2 + oy), (3, 2 + oy))
    b = ((7, 4), (7, 5))
    c = ((4, 8),)
    for x, y in a:
        g[y][x] = c1
    for x, y in b:
        g[y][x] = c2
    for x, y in c:
        g[y][x] = c3
    return g, bg, (c1, c2, c3, c4), (a, b, c)


def _freeze(g):
    return tuple(tuple(row) for row in g)


def make_case(seed: int, family: str):
    before, bg, colors, comps = _scene(seed)
    after = [row[:] for row in before]
    c1, c2, c3, c4 = colors
    a, b, c = comps
    expected = family
    if family == "NO_CHANGE":
        pass
    elif family == "MOTION":
        for x, y in a:
            after[y][x] = bg
        for x, y in a:
            after[y + 1][x] = c1
    elif family == "SPAWN":
        after[8][9] = c4
    elif family == "DESPAWN":
        for x, y in c:
            after[y][x] = bg
    elif family == "RECOLOR":
        for x, y in b:
            after[y][x] = c4
    elif family == "TOPOLOGY":
        before = [[bg] * 12 for _ in range(12)]
        for x in range(3, 8):
            before[5][x] = c1
        after = [row[:] for row in before]
        after[5][5] = bg
    elif family == "UI":
        for x in range(2, 10):
            after[0][x] = c4
    elif family == "CAMERA":
        after = [[bg] * 12 for _ in range(12)]
        for cells, color in ((a, c1), (b, c2), (c, c3)):
            for x, y in cells:
                after[y][x + 1] = color
    elif family == "COMPOUND":
        for x, y in a:
            after[y][x] = bg
        for x, y in a:
            after[y + 1][x] = c1
        after[8][9] = c4
    else:
        raise ValueError(family)
    return _freeze(before), _freeze(after), expected


def run(seeds: int = 100) -> dict[str, object]:
    if type(seeds) is not int or seeds <= 0 or seeds > 10000:
        raise ValueError("seeds must be exact int in 1..10000")
    rows = []
    counts = {family: 0 for family in FAMILIES}
    failures = []
    for seed in range(10000, 10000 + seeds):
        for family in FAMILIES:
            before, after, expected = make_case(seed, family)
            effect = factor_pair(before, after)
            ok = expected in effect.kinds
            counts[family] += int(ok)
            row = (seed, family, effect.kinds, effect.confidence_bps, ok)
            rows.append(row)
            if not ok:
                failures.append(row)
    body = {
        "seeds": seeds,
        "cases": len(rows),
        "passed": len(rows) - len(failures),
        "family_passed": counts,
        "failures": failures[:20],
        "claim_boundary": "synthetic taxonomy wiring only; not an ARC/Kaggle score",
    }
    body["receipt_sha256"] = sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=list).encode()).hexdigest()
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=100)
    args = parser.parse_args()
    report = run(args.seeds)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] == report["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
