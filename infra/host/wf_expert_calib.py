#!/usr/bin/env python3
"""host/wf_expert_calib.py — calibrate byte-entropy: what does NORMAL Q4_0 read vs the expert banks?
READ-ONLY, bounded samples. Compares titan dense FFN, titan expert banks (multi-window), and the
base gemma-4-26B expert bank so we know whether ~2.0 entropy is 'baked' or an artifact.
"""
import math, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT

TITAN = "C:/llm/models/titan.gguf"
BASE  = "C:/llm/models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
SAMPLE = 6144

def ent(b):
    if not b: return 0.0
    c = Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def tent(g, name, nwin=5):
    t = g.tensors.get(name)
    if not t: return None
    bpb, wpb = _QT.get(t["type"], (None,None))
    if bpb is None: return (t["type"], "not-quant")
    import functools, operator
    total = functools.reduce(operator.mul, t["dims"], 1)
    tbytes = total // wpb * bpb
    base = g.data0 + t["off"]
    es = []
    for k in range(nwin):
        off = base + int((k+0.5)/nwin * tbytes)
        off = min(off, base + tbytes - SAMPLE)
        es.append(ent(bytes(g.mm[off:off+SAMPLE])))
    return (t["type"], t["dims"], [round(x,2) for x in es])

def main():
    gt = GGUF(TITAN)
    print("== TITAN ==")
    for nm in ["blk.0.ffn_up.weight","blk.5.ffn_up.weight","blk.0.ffn_down.weight",
               "blk.1.ffn_gate_up_exps.weight","blk.2.ffn_gate_up_exps.weight",
               "blk.0.ffn_down_exps.weight","blk.1.ffn_down_exps.weight"]:
        print(f"  {nm:34} {tent(gt,nm)}")
    if os.path.exists(BASE):
        gb = GGUF(BASE)
        print("== BASE gemma-4-26B-A4B ==")
        # find its expert tensor names
        exps=[n for n in gb.tensors if 'exps' in n][:4]
        for nm in ["blk.0.ffn_up.weight"]+exps:
            print(f"  {nm:34} {tent(gb,nm)}")
    else:
        print("== BASE not found at", BASE)

if __name__ == "__main__":
    raise SystemExit(main())
