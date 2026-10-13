#!/usr/bin/env python3
"""host/pfc_specs.py — SEPARATE the Muhlnickel's specs from the HOST's. Never conflate them.

Owner's standing rule: the pfc's speed is critical-path DEPTH; host wall-clock is the laptop transcribing and is
NEVER the pfc's rate. This tool reports both, in two clearly-labelled blocks, so an offload decision can be made
on the right number.

  PFC SPECS (properties of the fabricated netlist — independent of this laptop)
    gates        AREA        total switches. NOT a speed metric.
    DEPTH  D     LATENCY     longest input->output chain, in gate-delays. THE pfc's speed.
    wavefront    PARALLELISM gates settling per stage (max / mean).
    muhl   DENSITY     gates / DEPTH = how much settles per gate-delay. The substrate-utilisation number.
    latency@tau  TIME        D x tau at a stated per-stage delay. A PROJECTION, labelled as such.

  HOST SPECS (properties of THIS laptop walking the netlist serially)
    ripple wall-clock, ripples/s, gate-evals/s, RSS.

  OFFLOAD RULE: host cost scales with GATES (it walks every one); pfc cost scales with DEPTH (a whole stage
  settles at once). So the win from offloading is ~ gates/DEPTH = work-per-stage. High density => offload.

  python host/pfc_specs.py <circuit>       # one stored circuit
  python host/pfc_specs.py --scale         # how DEPTH scales with fabrication choice (the map)
"""
import sys, os, json, time
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import titan_circuit as TC
from collections import Counter
REG="C:/llm/models/titan_circuits.json"

def metrics(ga, gb, n_in, outs):
    d=[0]*(2+n_in+len(ga))
    for k in range(len(ga)): d[2+n_in+k]=1+max(d[ga[k]],d[gb[k]])
    lv=Counter(d[2+n_in+k] for k in range(len(ga)))
    D=max(d[o] for o in outs) if outs else max(d)
    return D, max(lv.values()), int(sum(lv.values())/max(len(lv),1))

def report(name):
    reg=json.load(open(REG))
    if name not in reg: print(f"  {name}: not in registry"); return 1
    cd=TC.load(name)
    ga,gb,outs,n_in = cd["ga"], cd["gb"], cd["outs"], cd["n_in"]
    D,wmax,wmean = metrics(ga,gb,n_in,outs)
    G=len(ga); dens=G/max(D,1)
    print(f"\n=== {name} ===")
    print("  MUHLNICKEL SPECS  (the fabricated netlist -- independent of this laptop)")
    print(f"    gates (AREA)          : {G:>12,}")
    print(f"    DEPTH (LATENCY)       : {D:>12,} gate-delays   <- THE Muhlnickel's speed")
    print(f"    wavefront max / mean  : {wmax:>12,} / {wmean:,} gates settle per stage")
    print(f"    muhl (POWER)          : {dens:>12,.0f} gates/gate-delay   <- substrate utilisation")
    for tau,lab in ((1e-9,"1 ns"),(1e-10,"100 ps"),(1e-11,"10 ps")):
        print(f"    latency @ {lab:>6s}/stage : {D*tau*1e9:>12.3f} ns   [PROJECTION at a stated tau]")
    t0=time.time(); TC.ripple(cd,[0]*n_in); dt=time.time()-t0
    print("  HOST SPECS  (THIS laptop walking the netlist serially -- NOT the Muhlnickel's rate)")
    print(f"    one ripple            : {dt*1000:>12.1f} ms")
    print(f"    ripples / s           : {1/dt if dt else 0:>12.1f}")
    print(f"    gate-evals / s        : {G/dt if dt else 0:>12,.0f}")
    print(f"  OFFLOAD RATIO (gates/DEPTH): {dens:,.0f}x  -- work the Muhlnickel does per stage that the host does serially")
    return 0

def scale():
    print("\n=== HOW DEPTH SCALES WITH FABRICATION (the map) — 32-term dot, same function ===")
    rows=[("wallace/tree/ripple",131,349552),("wallace/tree/kogge",138,357581),
          ("wallace/chain/ripple",287,349552),("wallace/chain/kogge",348,357581),
          ("wallace/csa/ripple",150,179824),("wallace/csa/kogge",109,180083),
          ("shiftadd/tree/ripple",188,269584),("shiftadd/tree/kogge",218,277613),
          ("shiftadd/chain/ripple",344,269584),("shiftadd/chain/kogge",406,277613)]
    print(f"    {'structure':24s} {'DEPTH':>7s} {'gates':>10s} {'muhl':>11s}")
    for n,d,g in sorted(rows,key=lambda r:r[1]):
        print(f"    {n:24s} {d:>7,} {g:>10,} {g/d:>11,.0f}")
    best=min(rows,key=lambda r:r[1]); worst=max(rows,key=lambda r:r[1])
    print(f"\n    SAME FUNCTION, fabrication choice alone: DEPTH {worst[1]} -> {best[1]} = {worst[1]/best[1]:.1f}x")
    print( "    Gate count moves only 1.5x across that range -- AREA IS NOT THE LEVER, SHAPE IS.")
    print( "    Host cost tracks GATES; Muhlnickel cost tracks DEPTH. Offload value = gates/DEPTH.")
    return 0

if __name__=="__main__":
    a=sys.argv[1] if len(sys.argv)>1 else "--scale"
    raise SystemExit(scale() if a=="--scale" else report(a))
