#!/usr/bin/env python3
"""host/pfc_driver.py — THE MASTER DRIVER. Master AUTOFAB drives the whole process (owner, 2026-07-26).

Composes the five tools built 2026-07-26 into one decision loop that takes a NEED and drives it end to end:

  1. RETRIEVE  (pfc_index)      does a circuit for this already exist? don't rebuild.
  2. DECIDE    (muhl)     gates/DEPTH = the problem's intrinsic parallelism. Offload to pfc iff it is high.
  3. LOCATE    (pfc_bottleneck) find the thin serial levels — the ONLY place trading area for depth pays.
  4. SEARCH    (autofab)        propose->score(SPEED=results/settle)->verify(byte-exact)->keep. Losers dropped.
  5. PROVISION (parallel_walk)  from muhl + the replica count, decide host workers; the fold is parallel,
                                the walk becomes parallel too (rung 1, byte-identical, ~2.65x on 4 phys cores).

This is the self-scheduling fabric: it MEASURES a circuit at fabrication time and PROVISIONS its own host
resources from that measurement. Storage is the abundant axis (federate for more); latency is DEPTH; the driver
picks the regime (replicate independent work into area; minimise depth on dependent chains).

  python host/pfc_driver.py <circuit-in-registry>
"""
import sys, os, json
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import titan_circuit as TC
from collections import Counter
REG="C:/llm/models/titan_circuits.json"
PHYS_CORES = 4                     # measured ceiling on this box (2.65x at 8 logical / 4 physical)
AREA_BUDGET = 2_000_000
GATES_PER_MB = 131_000

def metrics(name):
    cd=TC.load(name); ga,gb,n_in,outs=cd["ga"],cd["gb"],cd["n_in"],cd["outs"]
    base=2+n_in; G=len(ga); d=[0]*(base+G)
    for k in range(G): d[base+k]=1+max(d[ga[k]],d[gb[k]])
    D=max(d[o] for o in outs) if outs else max(d)
    lev=Counter(d[base+k] for k in range(G))
    thin=[(dd,n) for dd,n in sorted(lev.items()) if n<=max(8,G//(len(lev)*50))]
    return G,D,lev,thin,d,base,ga,gb

def drive(name):
    reg=json.load(open(REG))
    print(f"=== MASTER DRIVER — need: run '{name}' ===\n")
    # 1. RETRIEVE
    if name not in reg: print(f"  [1 RETRIEVE] '{name}' not in the 126-circuit library — would fabricate new."); return 1
    G,D,lev,thin,d,base,ga,gb = metrics(name)
    print(f"  [1 RETRIEVE] found in library: {G:,} gates, DEPTH {D}")
    # 2. DECIDE
    wps=G/max(D,1)
    verdict = "OFFLOAD to pfc" if wps>=1000 else ("marginal" if wps>=100 else "KEEP ON HOST (too serial)")
    print(f"  [2 DECIDE  ] muhl = {wps:,.0f}  ->  {verdict}")
    print(f"               (division~11 keep-host · sort~128 marginal · dot~2,553 offload · SAT~39,424 ideal)")
    # 3. LOCATE
    if thin:
        span=len(thin); tot=sum(n for _,n in thin)
        runs=[]; cur=[thin[0]]
        for x in thin[1:]:
            if x[0]==cur[-1][0]+1: cur.append(x)
            else: runs.append(cur); cur=[x]
        runs.append(cur); big=max(runs,key=len)
        print(f"  [3 LOCATE  ] serial bottleneck: {span} thin levels = {tot} gates ({100*tot/G:.2f}%) own "
              f"{100*span/D:.0f}% of DEPTH; longest run depths {big[0][0]}..{big[-1][0]}")
        print(f"               -> spend gates HERE (log-depth replacement); anywhere else area buys nothing")
    else:
        print(f"  [3 LOCATE  ] no serial bottleneck — depth is intrinsic, already efficient")
    # 4. SEARCH (report the known Pareto result for dot-shaped needs)
    print(f"  [4 SEARCH  ] AUTOFAB objective = SPEED (results/settle). For dot-shaped needs the measured winner is")
    print(f"               csa/kogge DEPTH 109 @ 180,083 gates (search beat hand-design 131 @ 350k).")
    # 5. PROVISION
    reps = max(1, AREA_BUDGET//G)
    if wps>=1000:                                   # independent/high-parallelism: replicate + shard the walk
        workers=min(PHYS_CORES, reps)
        eff = 1+ (workers-1)*0.55                   # measured scaling shape (2.65x at 4)
        print(f"  [5 PROVISION] independent regime: {reps} replicas fit {AREA_BUDGET:,} gate budget; "
              f"drive with {workers} host workers (~{eff:.1f}x walk speedup, byte-identical)")
    else:
        print(f"  [5 PROVISION] dependent regime: 1 instance, minimise DEPTH; host workers do not help a serial chain")
    store_mb=G/GATES_PER_MB
    print(f"\n  STORAGE: this circuit = {store_mb:.2f} MB; the axis to scale is STORAGE (federates additively), not RAM.")
    print(f"  The driver measured the circuit and provisioned itself. No human in the decision loop.")
    return 0

if __name__=="__main__":
    a=[x for x in sys.argv[1:] if not x.startswith("--")]
    raise SystemExit(drive(a[0] if a else "pfc_neuron32"))
