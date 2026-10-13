#!/usr/bin/env python3
"""host/fable_audit.py — MODEL AUDITOR: is this downloaded model clean, or is something baked into its weights?
(fable, 2026-07-22; owner: "maybe it could be good to have a resource like that available")

Sweeps EVERY weight tensor and flags rows that don't look like quantized weights — baked circuits, backdoors, any
hidden structure — then localizes each region and tags whether it carries a known header (PFC*) or is stealth
(headerless, the kind magic-scans miss). Reference-free: needs no clean copy. Bounded, read-only, no inference.

  python host/fable_audit.py model.gguf [model2 ...]
"""
import math, os, statistics, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT

MAGICS = {b"PFCAPP01", b"PFCEXEC1", b"PFCGAME1", b"PFCMBUS1", b"PFCMMU01", b"PFCONE01", b"PFCOPR01", b"PFCPHYS1",
          b"PFCPIPE1", b"PFCPROV1", b"PFCRAY01", b"PFCSCLK1", b"PFCSMACH", b"PFCSMCLK", b"PFCSUBS1", b"PFCTET01",
          b"PFCTUN01", b"PFCTYPED", b"PFCWINMN"}
ABS_DROP = 0.7          # a real baked region craters row-entropy; natural weight variation barely dips


def ent(b):
    if not b: return 0.0
    c = Counter(b); n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def rows_of(dims):
    if len(dims) < 2: return None
    ncol, nrow = dims[0], 1
    for d in dims[1:]: nrow *= d        # flatten experts / heads -> (rows, ncol); catches MoE bakes in *_exps
    return ncol, nrow


def audit(path):
    g = GGUF(path); mm = g.mm; hits = []
    for name, t in g.tensors.items():
        if t["type"] not in _QT: continue
        ro = rows_of(t["dims"])
        if not ro: continue
        ncol, nrow = ro
        bpb, wpb = _QT[t["type"]]
        if nrow < 64 or ncol % wpb: continue
        rb = ncol // wpb * bpb; base = g.data0 + t["off"]; samp = min(rb, 384)
        step = max(1, nrow // 200)
        es = [(i, ent(mm[base + i * rb: base + i * rb + samp])) for i in range(0, nrow, step)]
        med = statistics.median(e for _, e in es)
        if not any(e < med - ABS_DROP for _, e in es): continue          # coarse: nothing suspicious here
        band = [i for i, e in es if e < med - ABS_DROP]
        lo, hi = max(0, min(band) - step), min(nrow, max(band) + step)   # fine: localize the block
        fe = [(i, ent(mm[base + i * rb: base + i * rb + samp])) for i in range(lo, hi)]
        bad = [i for i, e in fe if e < med - ABS_DROP]
        if not bad: continue
        a, b = min(bad), max(bad)
        tag = "headerless (stealth)"
        for i in bad[:40]:
            if bytes(mm[base + i * rb: base + i * rb + 8]) in MAGICS: tag = "PFC header"; break
        low = min(e for i, e in fe if i in set(bad))
        hits.append((name, a, b, len(bad), round(med, 2), round(low, 2), tag))
    return g, hits


def main():
    for path in (sys.argv[1:] or ["C:/llm/models/titan.gguf"]):
        if not os.path.exists(path):
            alt = os.path.join(os.path.dirname(path), "_removed", os.path.basename(path))
            path = alt if os.path.exists(alt) else path
        name = os.path.basename(path)
        if not os.path.exists(path):
            print(f"\n### {name}: NOT FOUND"); continue
        g, hits = audit(path)
        print(f"\n### {name}  ({os.path.getsize(path)/1e9:.1f} GB, {len(g.tensors)} tensors)", flush=True)
        if not hits:
            print("   ✓ CLEAN — every weight tensor reads as normal quantized weights.", flush=True)
            continue
        rows = sum(h[3] for h in hits)
        print(f"   ⚠ {len(hits)} baked region(s), {rows:,} anomalous rows — NOT a clean model:", flush=True)
        for nm, a, b, c, med, low, tag in sorted(hits, key=lambda h: h[5]):
            print(f"     {nm:32} rows {a:,}..{b:,} ({c})  entropy {low}↓ vs {med}  [{tag}]", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
