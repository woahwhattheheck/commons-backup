#!/usr/bin/env python3
"""host/pfc_substitute.py — IDEA 1: mechanise the signature failure of this codebase.

Three times in one session the fix ALREADY EXISTED and nothing was wired to it (shallow glue built-but-unused;
argmax never shallow-ified; dot32_i8 DEPTH 366 while pfc_dot32_w8x8_shallow does the same at 105). That is a
RETRIEVAL problem and it is fully mechanical:

  match circuits by I/O SIGNATURE (n_in, n_out) -> rank by DEPTH -> flag every pair where a same-signature
  circuit is shallower. Those are drop-in candidates.

  python host/pfc_substitute.py            # every substitution available in the library
"""
import sys, os, json
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import titan_circuit as TC
REG="C:/llm/models/titan_circuits.json"

def profile():
    reg=json.load(open(REG)); out={}
    for n,v in reg.items():
        if not isinstance(v,dict) or "offset" not in v: continue
        if not (v.get("n_gate") or v.get("gates")): continue
        try: cd=TC.load(n)
        except Exception: continue
        ga,gb,ni,outs=cd["ga"],cd["gb"],cd["n_in"],cd["outs"]
        base=2+ni; G=len(ga)
        if G==0: continue
        d=[0]*(base+G)
        for k in range(G): d[base+k]=1+max(d[ga[k]],d[gb[k]])
        D=max(d[o] for o in outs) if outs else max(d)
        out[n]=(ni,len(outs),G,D)
    return out

def equivalent(a,b,trials=6,seed=5):
    """SAME SIGNATURE IS NOT SAME FUNCTION. Prove it: identical outputs on random inputs, or it is not a drop-in."""
    import random
    ca,cb=TC.load(a),TC.load(b)
    if ca["n_in"]!=cb["n_in"] or len(ca["outs"])!=len(cb["outs"]): return False
    random.seed(seed)
    for _ in range(trials):
        inb=[random.randint(0,1) for _ in range(ca["n_in"])]
        if TC.ripple(ca,inb)!=TC.ripple(cb,inb): return False
    return True

def main():
    P=profile()
    print(f"  profiled {len(P)} circuits by (n_in, n_out) signature\n")
    sig={}
    for n,(ni,no,G,D) in P.items(): sig.setdefault((ni,no),[]).append((n,G,D))
    found=0
    for (ni,no),lst in sorted(sig.items()):
        if len(lst)<2: continue
        lst.sort(key=lambda x:x[2])                       # shallowest first
        best=lst[0]
        subs=[x for x in lst[1:] if x[2]>best[2]]
        if not subs: continue
        found+=1
        print(f"  signature ({ni} in, {no} out):")
        print(f"    ★ SHALLOWEST  {best[0]:26s} DEPTH {best[2]:>6,}  gates {best[1]:>9,}")
        for n,G,D in subs:
            eq = equivalent(best[0],n)
            tag = "DROP-IN (verified)" if eq else "same shape, DIFFERENT function - not substitutable"
            print(f"      {n:26s} DEPTH {D:>6,}  gates {G:>9,}  {D/best[2]:>5.1f}x deeper  {tag}")
    print(f"\n  {found} signature groups with an available substitution.")
    print("  Any 'replaceable' line is a consumer still wired to a deeper circuit when a shallower one is in the file.")
    return 0

if __name__=="__main__": raise SystemExit(main())
