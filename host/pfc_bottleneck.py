#!/usr/bin/env python3
"""host/pfc_bottleneck.py — WHERE IS THE LATENCY HIDING? Find the serial bottlenecks worth spending gates on.

The cost model says DEPTH is latency and AREA is free-ish (storage is abundant). So the fabricator's question is
never "make everything smaller" -- it is "WHERE does depth accumulate without work getting done?"

A level is a set of gates at the same depth; they all settle together. So:
  WIDE level  -> lots of work per gate-delay -> already efficient, adding area here buys NOTHING
  THIN level  -> almost no work per gate-delay -> pure serial latency -> THE place to trade area for depth

Measured on pfc_neuron32: the last 12 levels hold 54 gates (0.02% of the circuit) but own 9% of the DEPTH.
That tail is a ripple carry-propagate; a parallel-prefix adder collapses it (AUTOFAB: 137 -> 109).

  python host/pfc_bottleneck.py <circuit> [--top N]
"""
import sys, os
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
if hasattr(sys.stdout, "reconfigure"):        # capability check, NOT a swallowed except (V10)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from collections import Counter

def analyse(name, top=12):
    cd=TC.load(name); ga,gb,n_in,outs = cd["ga"],cd["gb"],cd["n_in"],cd["outs"]
    base=2+n_in; G=len(ga)
    d=[0]*(base+G)
    for k in range(G): d[base+k]=1+max(d[ga[k]],d[gb[k]])
    D=max(d[o] for o in outs) if outs else max(d)
    lev=Counter(d[base+k] for k in range(G))
    print(f"=== {name} ===")
    print(f"  gates {G:,} · DEPTH {D:,} · mean width {G//max(len(lev),1):,} gates/level")
    thin=[(dd,n) for dd,n in sorted(lev.items()) if n <= max(8, G//(len(lev)*50))]
    wide=sorted(lev.items(), key=lambda x:-x[1])[:5]
    print(f"  WIDEST levels (already efficient — adding area here buys nothing):")
    for dd,n in wide: print(f"      depth {dd:>5}  {n:>9,} gates settle")
    if not thin:
        print("  no thin levels — this circuit has no serial bottleneck. Depth is intrinsic."); return 0
    span=len(thin); tot=sum(n for _,n in thin)
    print(f"  ★ SERIAL BOTTLENECK: {span} thin levels hold {tot:,} gates ({100*tot/G:.2f}% of the circuit)")
    print(f"    but own {span} of {D} depth ({100*span/D:.0f}% of the LATENCY)")
    runs=[]; cur=[thin[0]]
    for x in thin[1:]:
        if x[0]==cur[-1][0]+1: cur.append(x)
        else: runs.append(cur); cur=[x]
    runs.append(cur)
    print(f"    contiguous serial runs ({len(runs)}):")
    for r in sorted(runs,key=lambda r:-len(r))[:top]:
        print(f"      depths {r[0][0]}..{r[-1][0]}  ({len(r)} levels, {sum(n for _,n in r)} gates)")
    print(f"  => SPEND GATES HERE. A wide/log-depth replacement for the longest run is the whole win;")
    print(f"     anywhere else, area buys nothing. (Search the bottleneck, not the space.)")
    return 0

# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# --slack : THE OTHER DIRECTION. Everything above asks "where does DEPTH accumulate, so I can spend
# gates to buy it back". This asks the dual: "where are gates BUYING SHALLOWNESS NOBODY CONSUMES, so
# I can spend depth to buy gates back". Same instrument, opposite sign — which is why it lives here
# rather than in a rival tool (CLAUDE.md #5: legibility through the instruments, don't duplicate one).
#
# §57F/§57G measured this by hand on two circuits: a ripple adder in the SHA message schedule cost
# ZERO muhlnickel DEPTH and returned 24,978 + 12,960 gates, because W[i] is consumed at round i and
# the rounds are serial (§38B). This makes that a standing measurement instead of a one-off.
#
# SLACK = latest-required-arrival - earliest-arrival, per wire. Forward pass gives arrival; a backward
# pass from the outputs gives required. A gate with slack > 0 settles EARLIER THAN ANYTHING NEEDS IT.
#
# WHAT THIS DOES AND DOES NOT CLAIM. It reports where headroom EXISTS. It does NOT claim those gates
# are removable: harvesting slack means re-implementing a region with a deeper, leaner circuit and
# re-verifying byte-exact (§57F/G did exactly that). Slack is where to LOOK, never a gate count
# already banked. Reporting it as a saving would be quoting a plan as a measurement.

MAGICS = {b"TITANCIR": "nand2", b"PFCTYPED": "typed", b"PFCWINMN": "typed"}


def read_netlist(name):
    """Load any stored netlist as (n_in, n_wire, edges, outs). Dispatches on the stored magic, so the
    sweep covers all three formats in the registry rather than only the NAND-only one."""
    import json, mmap, struct
    reg = json.load(open(TC.REG)); e = reg[name]; off = int(e["offset"])
    f = open(TC.TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    magic = bytes(mm[off:off + 8]); kind = MAGICS.get(magic)
    if kind is None:
        mm.close(); f.close(); return None
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", mm, off + 8); p = off + 24
    if kind == "nand2":
        ga = list(struct.unpack_from("<%di" % ng, mm, p)); p += ng * 4
        gb = list(struct.unpack_from("<%di" % ng, mm, p)); p += ng * 4
        edges = list(zip(ga, gb))
    else:
        edges = [None] * ng
        for k in range(ng):
            _op, a, b = struct.unpack_from("<Bii", mm, p); p += 9; edges[k] = (a, b)
    outs = list(struct.unpack_from("<%di" % n_out, mm, p))
    mm.close(); f.close()
    return n_in, n_wire, edges, outs


def slack_of(n_in, n_wire, edges, outs):
    """Forward arrival, backward required, slack per gate. Pure integer passes over the netlist."""
    base = 2 + n_in; G = len(edges)
    arr = [0] * (base + G)
    for k, (a, b) in enumerate(edges):
        arr[base + k] = 1 + (arr[a] if arr[a] > arr[b] else arr[b])
    D = max((arr[o] for o in outs), default=0)
    INF = D + 1
    req = [INF] * (base + G)
    for o in outs:
        if o < len(req): req[o] = D
    for k in range(G - 1, -1, -1):                      # gates are in topological order
        r = req[base + k]
        if r >= INF: continue
        a, b = edges[k]
        if r - 1 < req[a]: req[a] = r - 1
        if r - 1 < req[b]: req[b] = r - 1
    # A gate that reaches NO output has req == INF. Assigning it slack 0 files it as critical path,
    # which is exactly backwards — it is dead, not critical. On cpu_fwd that misreported 2,490 gates
    # and inflated the critical-path count from 4,374 to 6,864 (+57%). It never showed on the miner
    # circuits because those are DCE'd at fabrication and contain zero dead gates: the positive
    # control could not have caught it (§47B — a control that cannot fail has measured itself).
    slack = [0] * G; dead = [False] * G
    for k in range(G):
        r = req[base + k]
        if r >= INF: dead[k] = True
        else: slack[k] = r - arr[base + k]
    return D, arr, slack, dead


def slack_report(name, quiet=False):
    nl = read_netlist(name)
    if nl is None: return None
    n_in, n_wire, edges, outs = nl
    D, arr, slack, dead = slack_of(n_in, n_wire, edges, outs)
    G = len(edges)
    if G == 0 or D == 0: return None
    ndead = sum(1 for x in dead if x)
    live = G - ndead
    if live == 0: return None
    crit = sum(1 for k in range(G) if not dead[k] and slack[k] == 0)
    loose = live - crit
    # max(1, ...) because D//4 is 0 for any circuit shallower than 4, which made "slack >= 0" true of
    # EVERY gate and reported winner_only_max (DEPTH 2) as 100% deep headroom. A threshold that a
    # zero-slack gate can satisfy is not a threshold — caught by the sweep's own degenerate row.
    thr = max(1, D // 4)
    deep = sum(1 for k in range(G) if not dead[k] and slack[k] >= thr)
    weighted = sum(slack[k] for k in range(G) if not dead[k])
    if not quiet:
        print(f"=== {name} — SLACK ===")
        print(f"  gates {G:,} · DEPTH {D:,} gate-delays (THE MUHLNICKEL's critical path, not a host timing)")
        if ndead:
            print(f"  drive NO output (dead)         : {ndead:>9,}  ({100.0*ndead/G:5.1f}%)  excluded from the")
            print(f"     percentages below, which are over the {live:,} LIVE gates. Dead is not critical.")
        print(f"  on the critical path (slack 0) : {crit:>9,}  ({100.0*crit/live:5.1f}%)")
        print(f"  with headroom    (slack > 0)   : {loose:>9,}  ({100.0*loose/live:5.1f}%)")
        print(f"  with DEEP headroom (slack >= D/4): {deep:>9,}  ({100.0*deep/live:5.1f}%)  <- where a leaner,")
        print(f"     deeper implementation is most likely to cost 0 DEPTH, as measured in §57F/§57G")
        print(f"  mean slack per LIVE gate: {weighted/live:.1f} gate-delays")
        print(f"  NOT A SAVING. This is where to LOOK. Banking it means re-implementing the region and")
        print(f"  re-verifying byte-exact — §57F/§57G did that and got 24,978 + 12,960 gates.")
    return dict(name=name, G=G, D=D, crit=crit, loose=loose, deep=deep, dead=ndead,
                live=live, mean=weighted / live)


def slack_sweep(top=20):
    import json
    reg = json.load(open(TC.REG))
    rows = []
    for name, e in reg.items():
        if not isinstance(e, dict) or "offset" not in e: continue
        try: r = slack_report(name, quiet=True)
        except Exception: r = None
        if r: rows.append(r)
    rows.sort(key=lambda r: -r["deep"])
    print("SLACK SWEEP — every stored netlist. DEPTH/slack are THE MUHLNICKEL's (gate-delays);")
    print("no host timing is involved and none could change these numbers (§24).")
    print("Ranked by gates with DEEP headroom (slack >= DEPTH/4) — the ones most likely to yield a")
    print("gate discount at zero DEPTH cost, per §57F/§57G. NOT a saving until re-implemented+verified.\n")
    print("    %-26s %10s %8s %8s %9s %9s  %s"
          % ("circuit", "gates", "DEPTH", "dead", "slack>0", "deep", "mean slack"))
    for r in rows[:top]:
        print("    %-26s %10s %8s %7s%% %8s%% %8s%%  %.1f"
              % (r["name"], "{:,}".format(r["G"]), "{:,}".format(r["D"]),
                 "%4.1f" % (100.0 * r["dead"] / r["G"]),
                 "%5.1f" % (100.0 * r["loose"] / r["live"]),
                 "%5.1f" % (100.0 * r["deep"] / r["live"]), r["mean"]))
    print(f"\n  {len(rows)} netlists measured.")
    return 0


if __name__=="__main__":
    a=[x for x in sys.argv[1:] if not x.startswith("--")]
    if "--sweep" in sys.argv:
        raise SystemExit(slack_sweep())
    if "--slack" in sys.argv:
        raise SystemExit(0 if slack_report(a[0] if a else "muhl_lane") else 1)
    raise SystemExit(analyse(a[0] if a else "pfc_neuron32"))
