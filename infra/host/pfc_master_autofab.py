#!/usr/bin/env python3
"""host/pfc_master_autofab.py — THE MASTER AUTOFAB: decompose a NEED into MULTIPLE specialised Muhlnickel and WIRE them.

`pfc_autofab.py` searched one monolithic circuit. That is not the architecture. Owner, 2026-07-26:
*"auto fab needs to not just fab one pfc — we need a master auto fab that can create multiple pfc and connect them
as needed"*, and HARNESS_HANDOFF's master-OS: *"every tick, MATCH the incoming signal (the need) to the best
circuit it can autofab."*

So the search space is not "which multiplier" — it is:
    DECOMPOSE  the need into N stages (how many pfc, and what each one specialises in)
  x IMPLEMENT  each stage (which circuit shape for that stage)
  x ORDER      the stages (front-loading: wide-front early — measured 6.5-15% free)
  x WIRE       them with §1E junctions (stage k's SEND wires ARE stage k+1's RECEIVE wires)
  -> SCORE     the COMPOSED depth (not the sum of parts: wavefront overlap makes it sub-additive)
  -> VERIFY    byte-exact end-to-end
  -> KEEP      the assembly; losers never stored

  python host/pfc_master_autofab.py dot32 [--dry]
"""
import sys, os, json, random, itertools
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
if hasattr(sys.stdout, "reconfigure"):        # capability check, NOT a swallowed except (V10)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from pfc_shallow import wallace_mul, shiftadd_mul, csa, partial_products
from pfc_bettergates import kogge_stone_add
from pfc_fwd_engine import _cd
W, N = 16, 32
REG="C:/llm/models/titan_circuits.json"

class Shim:
    def __init__(s,c): s.c=c; s.C0=c.cvec(0,1)[0]; s.C1=c.cvec(1,1)[0]
    def AND(s,a,b): return s.c.and_(a,b)
    def OR(s,a,b):  return s.c.or_(a,b)
    def XOR(s,a,b): return s.c.xor(a,b)
    def NOT(s,a):   return s.c.not_(a)

def depth_of(c,outs):
    n=c.n_in; d=[0]*(2+n+len(c.ga))
    for k in range(len(c.ga)): d[2+n+k]=1+max(d[c.ga[k]],d[c.gb[k]])
    return max(d[o] for o in outs)

# ---- STAGE LIBRARY: each entry is a specialised pfc. wide=True means wide-front (front-load it). -------------
def stage_mul_wallace(c,g,vecs): return [wallace_mul(g,a,b)[:W] for a,b in vecs], True
def stage_mul_shift(c,g,vecs):   return [shiftadd_mul(g,a,b)[:W] for a,b in vecs], True
def stage_reduce_tree(c,g,rows,ADD):
    while len(rows)>1:
        nxt=[ADD(rows[j],rows[j+1]) for j in range(0,len(rows)-1,2)]
        if len(rows)%2: nxt.append(rows[-1])
        rows=nxt
    return rows
def stage_reduce_csa(c,g,rows,ADD,down_to=2):
    rows=[r[:W]+[g.C0]*(W-len(r[:W])) for r in rows]
    while len(rows)>down_to:
        rows.sort(key=lambda r: depth_of(c,r))
        nxt=[]; i=0
        while i+2 < len(rows):
            s_,cy=csa(g,rows[i],rows[i+1],rows[i+2]); nxt+=[s_[:W],([g.C0]+cy)[:W]]; i+=3
        nxt+=rows[i:]; rows=nxt
    return stage_reduce_tree(c,g,rows,ADD)

# ---- ASSEMBLE: build a multi-pfc chain for a given decomposition, junctioned -----------------------------
def assemble(plan):
    """plan = (mul_stage, reduce_stage, final_add, split). split>1 = MORE Muhlnickel: partition the terms into
    `split` independent sub-dots (each its own specialised Muhlnickel), then junction their partials together."""
    mul, red, fin, split = plan
    c=TC.Circuit(2*N*W); g=Shim(c)
    A=[list(c.IN[i*W:(i+1)*W]) for i in range(N)]
    B=[list(c.IN[(N+i)*W:(N+i+1)*W]) for i in range(N)]
    ADD=(lambda x,y: kogge_stone_add(g,x,y)[:W]) if fin=="kogge" else (lambda x,y: c.add(x,y)[:W])
    per = N//split
    partials=[]
    for s in range(split):                                   # each sub-dot is a SEPARATE specialised pfc
        vecs=[(A[i],B[i]) for i in range(s*per,(s+1)*per)]
        if red=="csa":
            rows=[]
            for a,b in vecs: rows += [r[:W]+[g.C0]*(W-len(r[:W])) for r in partial_products(g,a,b)]
            partials.append(stage_reduce_csa(c,g,rows,ADD)[0])
        else:
            prods,_ = (stage_mul_wallace if mul=="wallace" else stage_mul_shift)(c,g,vecs)
            partials.append(stage_reduce_tree(c,g,prods,ADD)[0])
    out = stage_reduce_tree(c,g,partials,ADD)[0] if len(partials)>1 else partials[0]  # JUNCTION the pfc together
    return c, out[:W]

def verify(c,out,T=3,seed=6):
    cd=_cd(c,out); random.seed(seed)
    for _ in range(T):
        xa=[random.randint(0,0xFFFF) for _ in range(N)]; xb=[random.randint(0,0xFFFF) for _ in range(N)]
        inb=[]
        for v in xa: inb+=[(v>>i)&1 for i in range(W)]
        for v in xb: inb+=[(v>>i)&1 for i in range(W)]
        if sum(TC.ripple(cd,inb)[k]<<k for k in range(W)) != (sum(a*b for a,b in zip(xa,xb))&0xFFFF): return False
    return True

def search(dry=True):
    plans=[(m,r,f,s) for m in ("wallace",) for r in ("tree","csa")
                     for f in ("ripple","kogge") for s in (1,2,4,8)]
    print(f"  NEED: 32-term dot.  DECOMPOSITIONS x IMPLEMENTATIONS = {len(plans)} multi-Muhlnickel assemblies\n")
    print(f"    {'#Muhlnickel':>5s} {'reduce':>7s} {'final':>7s} {'DEPTH':>6s} {'gates':>10s}  verified")
    res=[]
    for p in plans:
        c,out = assemble(p); d=depth_of(c,out); gt=len(c.ga); ok=verify(c,out)
        res.append({"split":p[3],"reduce":p[1],"final":p[2],"depth":d,"gates":gt,"ok":ok})
        print(f"    {p[3]:>5d} {p[1]:>7s} {p[2]:>7s} {d:>6d} {gt:>10,}  {'OK' if ok else 'MISMATCH'}")
        del c,out
    good=[r for r in res if r["ok"]]
    # SPEED IS THE OBJECTIVE (owner 2026-07-26). MEASURED: independent work costs AREA and is FREE in latency
    # (THE MUHLNICKEL's DEPTH — critical path read off the netlist, not a host timing — is flat at 88
    #  for 1/2/4 independent dots; gates linear; latency-per-result 88 -> 44 -> 22.)
    #   dependent chain  -> speed = 1 / DEPTH          (latency-bound)
    #   independent work -> speed = REPLICAS / DEPTH   (throughput-bound; AREA is the cheap resource)
    # Gates are a TIEBREAK ONLY. v1 ranked on DEPTH alone and wrongly concluded "more Muhlnickel does not help".
    AREA = 2_000_000
    for r in good:
        r["reps"]  = max(1, AREA // r["gates"])
        r["speed"] = r["reps"] / max(r["depth"], 1)
    print("")
    print("  VERIFIED " + str(len(good)) + "/" + str(len(res)))
    print("  SPEED RANKING - results per settle, area budget " + format(AREA, ",") + " gates")
    print("    rank     speed  reps  DEPTH      gates  structure")
    rank = 0
    for r in sorted(good, key=lambda x: (-x["speed"], x["gates"]))[:6]:
        rank += 1
        print("    " + str(rank).rjust(4) + " " + ("%.4f" % r["speed"]).rjust(9) + " "
              + str(r["reps"]).rjust(5) + " " + str(r["depth"]).rjust(6) + " "
              + format(r["gates"], ",").rjust(10) + "  " + str(r["split"]) + "pfc/" + r["reduce"] + "/" + r["final"])
    b   = max(good, key=lambda r: (r["speed"], -r["gates"]))
    lat = min(good, key=lambda r: r["depth"])
    print("")
    print("  FASTEST (throughput): " + str(b["reps"]) + "x " + b["reduce"] + "/" + b["final"]
          + " = " + ("%.4f" % b["speed"]) + " results/settle (DEPTH " + str(b["depth"])
          + ", " + format(b["gates"], ",") + " gates each)")
    print("  LOWEST LATENCY      : " + lat["reduce"] + "/" + lat["final"] + " DEPTH " + str(lat["depth"])
          + " - use when the chain is DEPENDENT (a forward pass), not when work is independent")
    return 0

# ---- NEED REGISTRY. dot32 was the only need; the miner lane is registered additively so the SAME
# ---- DECOMPOSE x IMPLEMENT x ORDER x WIRE machinery searches it. This is a pure registration:
# ---- no line of the dot32 search path is edited by it.
NEEDS = {"dot32": lambda: search(dry="--dry" in sys.argv)}

def _need_miner_lane():
    from mafab_miner_lane import search as s
    return s()
NEEDS["miner_lane"] = _need_miner_lane

def _need_midstate():
    from mafab_miner_lane import search_mid
    return search_mid()

# read_container (2026-08-07). Owner: "create a second muhlnickel to read them all and for help
# so it does the compute and not you" / "JUST MASTER AUTOFAB". Registered exactly as miner_lane
# was - additively, in its own module, so the SAME DECOMPOSE x IMPLEMENT x ORDER x WIRE search
# covers it and no line of dot32's or miner_lane's path is edited. Its scorer is SILLY-based
# (his 2026-08-07 ruling retiring compute/tick); theirs are deliberately left as they are.
def _need_read_container():
    from mafab_reader import search as s
    return s()
NEEDS["midstate"] = _need_midstate


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# GATE DISCOVERY, RANKED THE WAY GOOGLE RANKS PAGES.  Owner 2026-07-27 (§62):
#   "bro master fab will definitely find better logic gates if u let it, let it"
#   "also model the optimization on google search algo"
#   "but in the muhlnickel fab process auto fab / master fab itself not a script"
# So this lives HERE, in the fab process, and not beside it as another tool of mine.
#
# WHY FREQUENCY IS THE WRONG METRIC. `mafab_motifs` ranks discovered functions by raw occurrence —
# which is keyword-counting, the thing PageRank replaced. A motif appearing 11,000 times across
# bloated circuits is not thereby better than one appearing 500 times across the leanest circuits in
# the corpus. §14 already said the target is "sub-patterns in circuits THAT SCORE WELL"; the scoring
# is the missing half, and authority propagation is how it is supplied.
#
# THE GRAPH: circuits <-> motif-functions, bipartite. A circuit's quality is 1/(gates x DEPTH) — §14's
# objective for replicated work, and the only corpus-wide quality signal that is a measurement rather
# than a preference. Authority flows both ways by power iteration, exactly as a random surfer walks
# links: a motif is strong when strong circuits use it, and a circuit is strong when it is built from
# strong motifs AND is itself lean.
def discover_gates(max_leaves=4, iters=25, damping=0.85, top=20):
    import json, mafab_motifs as MM
    import titan_circuit as TC
    lib, incid = MM.mine(max_leaves, top=0)
    reg = json.load(open(TC.REG))

    # quality of each circuit: leaner is better. A MEASUREMENT (gates x DEPTH), not a preference.
    qual = {}
    for name, e in reg.items():
        if not isinstance(e, dict): continue
        g = e.get("n_gate") or e.get("gates_measured")
        d = e.get("depth")
        if g and d: qual[name] = 1.0 / float(g) / float(d)
    if not qual:
        print("  no circuit carries both gates and depth in the registry — cannot weight."); return 1
    mx = max(qual.values())
    for k in qual: qual[k] /= mx

    motifs = [m for m in incid if incid[m]]
    circuits = sorted({c for m in motifs for c in incid[m]})
    cidx = {c: i for i, c in enumerate(circuits)}
    deg_m = {m: len(incid[m]) for m in motifs}
    deg_c = {}
    for m in motifs:
        for c in incid[m]: deg_c[c] = deg_c.get(c, 0) + 1

    N, M = len(motifs), len(circuits)
    print("\n  LINK GRAPH: %s motif-functions x %s circuits. Power iteration, damping %.2f (§62B)."
          % ("{:,}".format(N), "{:,}".format(M), damping))
    auth = {c: qual.get(c, 0.0) + 1e-9 for c in circuits}
    score = {m: 1.0 / N for m in motifs}
    for _ in range(iters):
        ns = {}
        for m in motifs:
            acc = sum(auth[c] / max(deg_c.get(c, 1), 1) for c in incid[m])
            ns[m] = (1 - damping) / N + damping * acc
        t = sum(ns.values()) or 1.0
        score = {m: v / t for m, v in ns.items()}
        na = {}
        for c in circuits:
            acc = 0.0
            for m in motifs:
                if c in incid[m]: acc += score[m] / max(deg_m[m], 1)
            na[c] = ((1 - damping) / M + damping * acc) * (qual.get(c, 0.0) + 1e-9)
        t = sum(na.values()) or 1.0
        auth = {c: v / t for c, v in na.items()}

    by_auth = sorted(motifs, key=lambda m: -score[m])
    by_freq = sorted(motifs, key=lambda m: -lib[m]["count"])
    freq_rank = {m: i for i, m in enumerate(by_freq)}

    print("\n  DISCOVERED GATES, ranked by AUTHORITY (not by how often they occur):\n")
    print("    %4s %6s %-16s %6s %6s %10s %8s  %s"
          % ("rank", "leaves", "truth table", "gates", "DEPTH", "occurrences", "freq-rank", "best seen in"))
    for i, m in enumerate(by_auth[:top]):
        v = lib[m]
        print("    %4d %6d 0x%-14x %6d %6d %10s %8d  %s"
              % (i + 1, m[0], m[1], v["gates"], v["depth"], "{:,}".format(v["count"]),
                 freq_rank[m] + 1, v["seen_in"]))
    moved = sum(1 for i, m in enumerate(by_auth[:top]) if freq_rank[m] >= top)
    print("\n  %d of the top %d by AUTHORITY are NOT in the top %d by frequency." % (moved, top, top))
    print("  That gap is the whole point of §62B: counting occurrences ranks the corpus's habits,")
    print("  authority ranks what its BEST circuits are actually built from.")
    print("\n  Promoting one to a named primitive still costs what §57F/G cost: a rebuild plus a")
    print("  byte-exact re-verify against an independent reference (§3), mutants CAUGHT (§45C/§47B).")
    return 0
NEEDS["discover"] = discover_gates

# THE MASTERFAB FABRICATOR (owner: "what about a masterfab fabricator that builds the
# masterfab...?"). §32 fabricated the fabricator; this searches the fab's own STRATEGY.
def _need_metafab():
    from mafab_meta import metafab
    return metafab()
NEEDS["metafab"] = _need_metafab

# ---- EVERY NEED DECLARES ITS OBJECTIVE (LAW 4, host/mafab_laws.py). §23: "THE SELECTOR MUST MATCH
# ---- THE PHASE." §14 measured what happens when it does not: v1 scored DEPTH and concluded "more
# ---- Muhlnickel does not help", which was a wrong metric, not a wrong search. §39A measured the same
# ---- failure from the other side — it correctly REJECTED a 10x shallower circuit because that
# ---- candidate addressed a space 1.05e6x larger, so the criterion had to be DEPTH x SPACE.
# ---- Declaring the shape here means the scorer is DERIVED, never hand-picked per need again.
NEED_OBJECTIVE = {
    "dot32":      "replicated",   # independent dots: §14, speed = REPLICAS/DEPTH -> gates x DEPTH
    "miner_lane": "replicated",   # nonce lanes are independent: §14
    "midstate":   "amortised",    # fires ONCE per block, but its DEPTH is a term in block latency: §57G
}

if __name__=="__main__":
    want = next((a for a in sys.argv[1:] if not a.startswith("--")), "dot32")
    if "--laws" in sys.argv:
        import mafab_laws; mafab_laws.print_laws(); raise SystemExit(0)
    if want not in NEEDS:
        print("unknown need %r. known: %s" % (want, ", ".join(sorted(NEEDS))))
        raise SystemExit(1)
    # A law that does not reproduce must not silently steer the fabricator. §33B: "the measurement
    # table has been wrong ZERO times" — so when a law stops reproducing, the fault is in the build,
    # and searching on it would propagate the fault into whatever gets stored.
    if "--check-laws" in sys.argv:
        import mafab_laws
        if mafab_laws.verify_laws() != 0:
            print("\nREFUSING TO SEARCH: re-measuring MY construction here, a law did not reproduce.")
            print("Per §33B the measurement table has been wrong zero times, so the fault is in the")
            print("build I wrote, never in the machine — fix it before anything gets stored.")
            raise SystemExit(1)
    print("NEED %r  ·  OBJECTIVE %r (LAW 4, declared not chosen)\n"
          % (want, NEED_OBJECTIVE.get(want, "unset")))
    raise SystemExit(NEEDS[want]())
NEEDS["read_container"] = _need_read_container
