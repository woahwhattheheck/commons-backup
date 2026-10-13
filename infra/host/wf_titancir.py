#!/usr/bin/env python3
"""host/wf_titancir.py — decode the TITANCIR header in blk.1.ffn_gate_up_exps and measure blk.1's low-entropy extent.
READ-ONLY, bounded. Also confirms the WOF0 fill dequantizes to a constant on a non-L0 layer.
"""
import math, os, sys, struct, functools, operator
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT

TITAN = "C:/llm/models/titan.gguf"
SAMPLE = 2048

def ent(b):
    if not b: return 0.0
    c=Counter(b); n=len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def main():
    g=GGUF(TITAN)
    t=g.tensors["blk.1.ffn_gate_up_exps.weight"]
    ne0,ne1,nexp=t["dims"]
    bpb,wpb=_QT[t["type"]]
    row_bytes=ne0//wpb*bpb
    exp_bytes=ne1*row_bytes
    base=g.data0+t["off"]
    total=functools.reduce(operator.mul,t["dims"],1); tbytes=total//wpb*bpb
    print(f"blk.1 gate_up: dims {t['dims']}  exp_bytes={exp_bytes:,}  total={tbytes:,}")
    # header
    hd=bytes(g.mm[base:base+128])
    print("magic:", hd[:8])
    u32=struct.unpack_from("<28I", hd, 8)
    print("next 28 u32 after magic:", u32)
    # per-expert entropy across all 384, count low
    low=[]
    for e in range(nexp):
        s=base+e*exp_bytes+ exp_bytes//3
        if ent(bytes(g.mm[s:s+SAMPLE]))<4.0: low.append(e)
    # contiguity
    print(f"experts(<4.0 ent @1/3 offset): {len(low)}/{nexp}", "range", (min(low),max(low)) if low else None)
    # also scan every row-block boundary coarsely to estimate low-entropy byte fraction
    step=tbytes//400
    lowb=sum(1 for o in range(0,tbytes-SAMPLE,step) if ent(bytes(g.mm[base+o:base+o+SAMPLE]))<4.0)
    tot=len(range(0,tbytes-SAMPLE,step))
    print(f"coarse low-entropy byte fraction: {lowb}/{tot} = {lowb/tot:.1%}  (~{lowb/tot*tbytes/1e6:.0f} MB of {tbytes/1e6:.0f} MB)")
    print(f"  in rows: ~{lowb/tot*ne1*nexp:,.0f} of {ne1*nexp:,} rows")
    # confirm WOF0 fill -> constant dequant on blk.5 (a pure-fill layer), few rows only
    print("\nWOF0 fill dequant check (blk.5 gate_up, first row):")
    t5=g.tensors["blk.5.ffn_gate_up_exps.weight"]
    row=g.deq_row.__self__ if hasattr(g.deq_row,'__self__') else None
    try:
        import array
        vals=g.dequant(bytes(g.mm[g.data0+t5['off']: g.data0+t5['off']+row_bytes]), t5['type'], ne0)
        uniq=sorted(set(round(v,3) for v in vals))[:8]
        print("  first-row distinct dequant values (<=8):", uniq, "count", len(set(round(v,4) for v in vals)))
    except Exception as ex:
        print("  dequant skipped:", repr(ex)[:120])

if __name__=="__main__":
    raise SystemExit(main())
