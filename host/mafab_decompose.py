#!/usr/bin/env python3
"""host/mafab_decompose.py — THE FABRICATOR FINDS ITS OWN SEAMS. The DECOMPOSE axis, automated.

§13 says the master autofab searches "DECOMPOSE (how many Muhlnickel, each specialised) x IMPLEMENT x
ORDER x WIRE (§1E junctions)". Until now only IMPLEMENT was searched: *I* found the mid/lane seam by
hand and the search only optimised inside it. That is the fabricator's headline axis being driven by
me, which is the thing the owner asked to stop.

THE SEAM IS COMPUTABLE, and §57A states it in fully general terms already:
    "SHA block 1 consumes header words 0..15. The nonce is WORD 19. So block 1 is NONCE-INDEPENDENT,
     and every lane in the monolith was recomputing it."
Generalised: given the inputs that VARY across the replicated dimension, any gate not reachable from
them is INVARIANT. Invariant gates fire ONCE per problem; only the varying cone replicates per lane.
So the split is not a design decision to be made — it is a reachability question to be measured.

§1E gives the wiring: the invariant stage's SEND wires ARE the varying stage's RECEIVE wires — "a
shared location, not a copy" — and §57A records that routing `mid` in as DATA is what keeps this
clear of violation #5, which baked midstate as a CONSTANT and so forced a new circuit per block.

WHY IT PAYS, measured (§14): independent work costs AREA and is free in latency, and speed =
REPLICAS/DEPTH. Hoisting invariant gates out of the replicated stage cuts the gates that replicate,
so replicas rise for the same storage. §57C measured the realised win: area-delay 3.985e9 -> 1.128e9.

  python host/mafab_decompose.py gen_win --vary 608:640      # find the seam in the miner monolith
  python host/mafab_decompose.py <circuit> --vary LO:HI
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pfc_bottleneck as PB


def find_seam(n_in, edges, outs, vary_inputs):
    """Split a netlist by reachability from the REPLICATED inputs (§57A generalised).

    Returns (invariant_gates, varying_gates, junction_wires, depths). A gate is VARYING iff it is
    reachable forward from any varying input; everything else is INVARIANT and hoistable."""
    base = 2 + n_in; G = len(edges)
    varying = bytearray(base + G)
    for i in vary_inputs:
        if 2 + i < len(varying): varying[2 + i] = 1
    for k, (a, b) in enumerate(edges):                 # gates are in topological order
        if varying[a] or varying[b]: varying[base + k] = 1
    inv = [k for k in range(G) if not varying[base + k]]
    var = [k for k in range(G) if varying[base + k]]

    # THE JUNCTION (§1E) IS COMPUTED GATE OUTPUTS ONLY. An invariant INPUT that the varying cone
    # reads is not a junction — it is block data the host routes in anyway, exactly as §57A routes
    # `mid` in "as data, NOT violation #5's baked constant". Counting inputs alongside computed wires
    # inflated gen_win's interface to 1,024 when the real `mid` interface is 256 bits.
    junction = set()          # invariant GATE outputs consumed by the varying cone — must be SENT
    passthru = set()          # invariant INPUTS consumed by the varying cone — routed in, not sent
    for k in var:
        for w in edges[k]:
            if w < 2 or varying[w]: continue
            (passthru if w < base else junction).add(w)
    # depth of each partition, measured independently
    arr = [0] * (base + G)
    for k, (a, b) in enumerate(edges): arr[base + k] = 1 + max(arr[a], arr[b])
    d_inv = max([arr[base + k] for k in inv], default=0)
    d_var_out = max([arr[o] for o in outs], default=0)
    return inv, var, sorted(junction), sorted(passthru), d_inv, d_var_out


def report(name, vary_lo, vary_hi):
    nl = PB.read_netlist(name)
    if nl is None:
        print("cannot read a netlist for %r" % name); return 1
    n_in, n_wire, edges, outs = nl
    vary = list(range(vary_lo, vary_hi))
    inv, var, junction, passthru, d_inv, d_out = find_seam(n_in, edges, outs, vary)
    G = len(edges)
    print("DECOMPOSE — %s  (%s gates, %d inputs; inputs %d:%d declared REPLICATED)"
          % (name, "{:,}".format(G), n_in, vary_lo, vary_hi))
    print("  The seam is MEASURED by reachability, not chosen by me (§57A generalised, §13).\n")
    print("  INVARIANT cone (fires ONCE per problem) : %9s gates  (%5.1f%%)  DEPTH %s"
          % ("{:,}".format(len(inv)), 100.0 * len(inv) / G, "{:,}".format(d_inv)))
    print("  VARYING cone   (REPLICATES per lane)    : %9s gates  (%5.1f%%)"
          % ("{:,}".format(len(var)), 100.0 * len(var) / G))
    print("  §1E JUNCTION (computed, must be SENT)   : %9s wires  — stage A's SEND wires ARE"
          % "{:,}".format(len(junction)))
    print("     stage B's RECEIVE wires: a shared location, not a copy.")
    print("  invariant INPUTS read by stage B        : %9s wires  — NOT a junction; the host routes"
          % "{:,}".format(len(passthru)))
    print("     these in as block data anyway, exactly as §57A routes mid in \"as data\".")
    if not inv:
        print("\n  NO SEAM: every gate is reachable from the replicated inputs. Nothing to hoist.")
        return 0
    # §14: speed = REPLICAS/DEPTH, replicas = area/gates. Hoisting shrinks what replicates.
    print("\n  WHAT HOISTING BUYS (§14: independent work -> speed = REPLICAS/DEPTH, so replicas rise")
    print("  as the REPLICATED gate count falls; the invariant cone is paid once, not per lane):")
    print("    gates that replicate: %s -> %s  = %.2fx more replicas per unit storage"
          % ("{:,}".format(G), "{:,}".format(len(var)), G / max(len(var), 1)))
    print("\n  NOT A FABRICATION. This measures where the seam IS. Building the two stages and")
    print("  verifying them byte-exact against an independent reference is a separate step (§3),")
    print("  and §57B is what that costs: mutants must be CAUGHT before either stage is stored.")
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    name = a[0] if a else "gen_win"
    lo, hi = 608, 640
    if "--vary" in sys.argv:
        rng = sys.argv[sys.argv.index("--vary") + 1]
        lo, hi = (int(x) for x in rng.split(":"))
    raise SystemExit(report(name, lo, hi))
