#!/usr/bin/env python3
"""host/pfc_truefloat.py — verify the substrate against TRUE FLOAT (the check that catches shared defects).

MORNING_HANDOFF's rule, learned the hard way: "byte-exact vs the path it replaces" compares one substrate path
against ANOTHER and is BLIND to a defect both share. Every optimisation in this engine passed at ~1e-15 while the
real error against float was 28%. Verify BOTH ways: against the path replaced (catches regressions) AND against a
true reference (catches a shared defect). Only the second found it.

Needs nothing but the trusted dequantiser -- deliberately does NOT import pfc_forward (out of spec, quarantined).

  python host/pfc_truefloat.py [WB] [XB]
Thresholds: >1% means quantisation broke. WB=3 -> ~28% (garbage) · WB=8 XB=10 -> ~1.0% (the pick).
"""
import sys, math, random, os
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
from gguf_pp import GGUF, dequant, row_bytes
import pfc_engine as E

def check(WB=8, XB=10, NJ=48, seed=2):
    e=E.PfcEngine(WB=WB, XB=XB)
    name=next(n for n in e.g.tensors if n.endswith("attn_q.weight"))
    t=e.g.tensors[name]; tid=int(t["type"]); n_in=int(t["dims"][0])
    base=e.g.data0+int(t["off"]); rb=row_bytes(tid,n_in); mm=e.g.mm
    random.seed(seed)
    x=[random.gauss(0,0.3) for _ in range(n_in)]                      # outlier-heavy, per the doc
    for i in random.sample(range(n_in),6): x[i]=random.choice([-1,1])*random.uniform(15,23)
    got=e.matvec(name,x); num=den=0.0
    for j in range(NJ):
        w=dequant(mm[base+j*rb:base+j*rb+rb],tid,n_in)
        ref=sum(w[i]*x[i] for i in range(n_in))
        num+=(got[j]-ref)**2; den+=ref*ref
    return math.sqrt(num/den)*100, len(e.dot.gates), name, n_in

if __name__=="__main__":
    WB=int(sys.argv[1]) if len(sys.argv)>1 else 8
    XB=int(sys.argv[2]) if len(sys.argv)>2 else 10
    rel,gates,name,n_in=check(WB,XB)
    print(f"  {name} (n_in={n_in})  WB={WB} XB={XB}  dot {gates:,} gates")
    print(f"  rel-L2 vs TRUE float: {rel:.3f}%   -> {'PASS' if rel<1.0 else 'FAIL (>1% = quantisation broke)'}")
