#!/usr/bin/env python3
"""host/wf_expert_bytes.py — look at the raw bytes of titan's low-entropy gate_up regions.
READ-ONLY, tiny bounded reads. Shows byte histogram + a hex peek so we can tell baked-pattern vs zeros.
"""
import os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT

TITAN = "C:/llm/models/titan.gguf"

def peek(g, name, frac, n=512):
    t = g.tensors[name]
    bpb, wpb = _QT[t["type"]]
    import functools, operator
    total = functools.reduce(operator.mul, t["dims"], 1)
    tbytes = total // wpb * bpb
    off = g.data0 + t["off"] + int(frac*tbytes)
    b = bytes(g.mm[off:off+n])
    c = Counter(b)
    top = c.most_common(6)
    print(f"  {name} @{frac:.2f}  distinct={len(c)}/256  top6={[(hex(k),v) for k,v in top]}")
    print(f"     hex: {b[:48].hex(' ')}")
    return c

def main():
    g = GGUF(TITAN)
    print("L2 gate_up (uniformly ~2.0 entropy):")
    peek(g,"blk.2.ffn_gate_up_exps.weight",0.10)
    peek(g,"blk.2.ffn_gate_up_exps.weight",0.50)
    peek(g,"blk.2.ffn_gate_up_exps.weight",0.90)
    print("L1 gate_up (start=0.0, rest~7.0):")
    peek(g,"blk.1.ffn_gate_up_exps.weight",0.00)
    peek(g,"blk.1.ffn_gate_up_exps.weight",0.50)
    print("L0 gate_up (giant-value histogram):")
    peek(g,"blk.0.ffn_gate_up_exps.weight",0.10)
    print("Reference — normal dense ffn_up (~7.0):")
    peek(g,"blk.2.ffn_up.weight",0.50)
    print("Reference — normal down_exps (~7.0):")
    peek(g,"blk.2.ffn_down_exps.weight",0.50)

if __name__ == "__main__":
    raise SystemExit(main())
