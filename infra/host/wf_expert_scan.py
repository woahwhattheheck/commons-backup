#!/usr/bin/env python3
"""host/wf_expert_scan.py — 30-layer map: which titan MoE tensors are baked (low-entropy / magic) vs real weights.
READ-ONLY, bounded multi-window byte sampling. Detects the 'TITANCIR' magic and the 8-byte 'WOF0' fill.
"""
import math, os, sys, functools, operator
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT

TITAN = "C:/llm/models/titan.gguf"
SAMPLE = 6144
FILL = b"\x00\x00\x00\x00\x57\x4f\x46\x30"   # the repeating WOF0 baked-fill unit (entropy 2.0)

def ent(b):
    if not b: return 0.0
    c = Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def scan(g, name):
    t = g.tensors.get(name)
    if not t: return None
    bpb, wpb = _QT[t["type"]]
    total = functools.reduce(operator.mul, t["dims"], 1)
    tbytes = total // wpb * bpb
    base = g.data0 + t["off"]
    es=[]; fill_frac=0; magic=False
    for k in range(9):
        off = min(base + int(k/8*tbytes), base+tbytes-SAMPLE)
        b = bytes(g.mm[off:off+SAMPLE])
        es.append(ent(b))
        # fraction of this window that matches the 8-byte fill pattern on-phase
        best=0
        for ph in range(8):
            bb=b[ph:ph+ (len(b)-ph)//8*8]
            m=sum(bb[i:i+8]==FILL for i in range(0,len(bb),8))
            best=max(best, m*8/len(b))
        fill_frac=max(fill_frac,best)
        if b"TITANCIR" in b or b"PFC" in b[:16]: magic=True
    head = bytes(g.mm[base:base+8])
    return round(sum(es)/len(es),2), round(min(es),2), round(fill_frac,2), magic, head

def main():
    g = GGUF(TITAN)
    print(f"{'layer':5} | {'gate_up_exps ent(mean/min)  fill  magic':42} | {'down_exps ent(mean/min) fill magic'}")
    for L in range(30):
        gu = scan(g, f"blk.{L}.ffn_gate_up_exps.weight")
        dn = scan(g, f"blk.{L}.ffn_down_exps.weight")
        def fmt(r):
            if not r: return "n/a"
            m,mn,ff,mg,hd = r
            return f"{m:4.2f}/{mn:4.2f} fill={ff:.2f} {'MAGIC' if mg else '     '} hd={hd[:4]!r}"
        print(f"blk.{L:<2d}| {fmt(gu):46} | {fmt(dn)}")

if __name__ == "__main__":
    raise SystemExit(main())
