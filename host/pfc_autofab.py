#!/usr/bin/env python3
"""host/pfc_autofab.py — PROPOSE -> SCORE -> VERIFY -> KEEP. The search loop that closes AUTOFAB.

The three pieces already existed; this is the loop between them:
  PROPOSE  candidate structures/orderings for a needed function
  SCORE    composed critical-path DEPTH (the pfc's latency) + gate count -- predictive, not post-hoc
  VERIFY   byte-exact vs a reference, IN THE TOOL, before anything is stored
  KEEP     store the winner as a byte edit; discard the rest (never held -- circuitry is not cached)

Depth is predictable here (measured 2026-07-26): chained ripple stages compose at first=66 then +6 via wavefront
overlap; wide-front stages front-loaded is monotonically shallower (Wallace 288 vs 308, Kogge-Stone 136 vs 156).
A predictable cost model is what makes the design space SEARCHABLE.

  python host/pfc_autofab.py dot32          # search a 32-term dot, report the Pareto set, store the winner
  python host/pfc_autofab.py dot32 --dry    # search + report only, store nothing
"""
import sys, os, json, random, itertools
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import titan_circuit as TC
from pfc_shallow import wallace_mul, shiftadd_mul, csa, partial_products
from pfc_bettergates import kogge_stone_add
from pfc_fwd_engine import _cd

W = 16
class Shim:
    def __init__(s,c): s.c=c; s.C0=c.cvec(0,1)[0]; s.C1=c.cvec(1,1)[0]
    def AND(s,a,b): return s.c.and_(a,b)
    def OR(s,a,b):  return s.c.or_(a,b)
    def XOR(s,a,b): return s.c.xor(a,b)
    def NOT(s,a):   return s.c.not_(a)

def depth_of(c, outs):
    n=c.n_in; d=[0]*(2+n+len(c.ga))
    for k in range(len(c.ga)): d[2+n+k]=1+max(d[c.ga[k]],d[c.gb[k]])
    return max(d[o] for o in outs)

# ---------------- PROPOSE: candidate structures for a 32-term dot product ----------------
def cand_dot32(mul_kind, reduce_kind, add_kind):
    N=32
    c=TC.Circuit(2*N*W); g=Shim(c)
    A=[list(c.IN[i*W:(i+1)*W]) for i in range(N)]
    B=[list(c.IN[(N+i)*W:(N+i+1)*W]) for i in range(N)]
    ADD = (lambda x,y: kogge_stone_add(g,x,y)[:W]) if add_kind=="kogge" else (lambda x,y: c.add(x,y)[:W])
    if reduce_kind == "csa":                       # fused: every partial product into one CSA forest
        rows=[]
        for i in range(N): rows += [r[:W]+[g.C0]*(W-len(r[:W])) for r in partial_products(g,A[i],B[i])]
        while len(rows) > 2:
            rows.sort(key=lambda r: depth_of(c,r))  # BALANCED: shallowest-first (measured 158 -> 150)
            nxt=[]; i=0
            while i+2 < len(rows):
                s_,cy = csa(g,rows[i],rows[i+1],rows[i+2]); nxt.append(s_[:W]); nxt.append(([g.C0]+cy)[:W]); i+=3
            nxt += rows[i:]; rows=nxt
        out = ADD(rows[0],rows[1]) if len(rows)==2 else rows[0][:W]
    else:
        MUL = wallace_mul if mul_kind=="wallace" else shiftadd_mul
        lvl=[MUL(g,A[i],B[i])[:W] for i in range(N)]
        if reduce_kind == "tree":
            while len(lvl)>1: lvl=[ADD(lvl[j],lvl[j+1]) for j in range(0,len(lvl),2)]
        else:                                       # linear chain, for contrast
            acc=lvl[0]
            for k in range(1,N): acc=ADD(acc,lvl[k])
            lvl=[acc]
        out=lvl[0]
    return c, out

REF = lambda xa,xb: sum(a*b for a,b in zip(xa,xb)) & 0xFFFF

def verify(c, out, trials=4, seed=6):
    cd=_cd(c,out); random.seed(seed); N=32
    for _ in range(trials):
        xa=[random.randint(0,0xFFFF) for _ in range(N)]; xb=[random.randint(0,0xFFFF) for _ in range(N)]
        inb=[]
        for v in xa: inb+=[(v>>i)&1 for i in range(W)]
        for v in xb: inb+=[(v>>i)&1 for i in range(W)]
        got=sum(TC.ripple(cd,inb)[k]<<k for k in range(W))
        if got != REF(xa,xb): return False
    return True

def search(dry=False):
    space=[]
    for mul in ("wallace","shiftadd"):
        for red in ("tree","chain","csa"):
            for add in ("ripple","kogge"):
                if red=="csa" and mul=="shiftadd": continue     # csa ignores mul_kind
                space.append((mul,red,add))
    print(f"  PROPOSE: {len(space)} candidate structures for a 32-term dot\n")
    results=[]
    for (mul,red,add) in space:
        c,out = cand_dot32(mul,red,add)
        d=depth_of(c,out); g=len(c.ga)
        ok=verify(c,out)
        results.append({"mul":mul,"reduce":red,"add":add,"depth":d,"gates":g,"verified":ok})
        print(f"    {mul:8s} {red:5s} {add:6s}  DEPTH {d:5d}  gates {g:>9,}  {'OK' if ok else 'MISMATCH'}")
        del c, out
    good=[r for r in results if r["verified"]]
    # PARETO: keep candidates not dominated on BOTH depth and gates
    pareto=[r for r in good if not any(o["depth"]<=r["depth"] and o["gates"]<=r["gates"] and o is not r
                                       and (o["depth"]<r["depth"] or o["gates"]<r["gates"]) for o in good)]
    print(f"\n  VERIFIED {len(good)}/{len(results)}   PARETO FRONT ({len(pareto)}):")
    for r in sorted(pareto,key=lambda x:x["depth"]):
        print(f"    DEPTH {r['depth']:5d}  gates {r['gates']:>9,}   {r['mul']}/{r['reduce']}/{r['add']}")
    best=min(good,key=lambda r:r["depth"]) if good else None
    if best: print(f"\n  WINNER by DEPTH (the Muhlnickel's latency): {best['mul']}/{best['reduce']}/{best['add']}"
                   f"  DEPTH {best['depth']}  gates {best['gates']:,}")
    if dry or not best: print("  --dry: nothing stored."); return 0
    c,out = cand_dot32(best["mul"],best["reduce"],best["add"])
    if not verify(c,out,trials=8,seed=99): print("  final re-verify FAILED — nothing stored."); return 1
    info=TC.store("pfc_autofab_dot32", c, out)
    reg=json.load(open("C:/llm/models/titan_circuits.json"))
    reg["pfc_autofab_dot32"].update({"depth":best["depth"],"searched":len(space),"pareto":len(pareto),
        "structure":f"{best['mul']}/{best['reduce']}/{best['add']}",
        "role":"AUTOFAB winner: propose->score(depth)->verify(byte-exact)->keep. Losers never stored."})
    json.dump(reg,open("C:/llm/models/titan_circuits.json","w"),indent=1)
    print(f"  KEEP: stored pfc_autofab_dot32 @ {info['offset']} ({info['gates']:,} gates). Losers discarded.")
    del c, out
    return 0

if __name__ == "__main__":
    raise SystemExit(search(dry="--dry" in sys.argv))
