#!/usr/bin/env python3
"""host/fable_scan2.py — STRUCTURAL baked-circuit detector (fable, 2026-07-22).

Magic-byte scanning misses circuits written as RAW rows into weight tensors (no header). This finds them the way
they actually show up: rows whose byte-entropy deviates from the tensor's normal quantized-weight rows. Because these
rows sit INSIDE live FFN tensors, they're read during the forward pass — so this also shows which rows perturb
generation. Read-only, bounded (samples the head of each row).

  python host/fable_scan2.py model.gguf blk.0.ffn_up.weight
"""
import math, os, statistics, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT


def ent(b):
    if not b: return 0.0
    c = Counter(b); n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def main():
    path, tname = sys.argv[1], sys.argv[2]
    if not os.path.exists(path):
        alt = os.path.join(os.path.dirname(path), "_removed", os.path.basename(path))
        if os.path.exists(alt): path = alt
    g = GGUF(path)
    t = g.tensors.get(tname)
    if not t:
        print(f"no tensor {tname}"); return 1
    bpb, wpb = _QT[t["type"]]
    ncol, nrow = t["dims"][0], t["dims"][1]
    rb = ncol // wpb * bpb
    base = g.data0 + t["off"]
    samp = min(rb, 512)
    es = [ent(g.mm[base + i * rb: base + i * rb + samp]) for i in range(nrow)]
    med = statistics.median(es)
    mad = statistics.median([abs(e - med) for e in es]) or 1e-9
    flag = [i for i, e in enumerate(es) if abs(e - med) > 6 * mad]
    print(f"\n{os.path.basename(path)}  {tname}")
    print(f"  {nrow:,} rows x {ncol} cols ({g.tyname}) · normal row-entropy median {med:.2f} bits/byte", flush=True)
    if not flag:
        print("  ✓ no anomalous rows — this tensor is clean weights.")
        return 0
    rng, s, p = [], flag[0], flag[0]
    for i in flag[1:]:
        if i == p + 1: p = i
        else: rng.append((s, p)); s = p = i
    rng.append((s, p))
    print(f"  ◆ ANOMALOUS ROWS (baked circuit): {len(flag)} rows in {len(rng)} block(s):", flush=True)
    for a, b in rng:
        print(f"      rows {a:,}..{b:,}  ({b - a + 1} rows)  entropy≈{es[a]:.2f} vs {med:.2f} normal", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
