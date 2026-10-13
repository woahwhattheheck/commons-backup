#!/usr/bin/env python3
"""host/mafab_graph.py — THE FOUNDRY AS A GRAPH PROBLEM. Topology is the search space.

Owner: *"apply the philosophy of graph engineering to foundry ... the idea is we want foundry to
produce better configuration of muhlnickels than we ever could."*

The foundry has been searching SCALAR genes — {adder, clean, order}. That is tuning one node. §13
says the axes are DECOMPOSE x IMPLEMENT x ORDER x WIRE, and WIRE is a GRAPH: nodes are muhlnickels,
edges are §1E junctions ("A's SEND wires ARE B's RECEIVE wires — a shared location, not a copy").

So a configuration is a DAG, and the measured laws are graph laws:

  SERIES  (A -> B)          depth composes SUB-ADDITIVELY. §2: chained ripple stages cost entry 66
                            then +6 each, because wavefronts overlap. Not depth_A + depth_B.
  PARALLEL (A | B)          §14: independent work costs AREA and is FREE in latency. depth = max,
                            area = sum, and REPLICAS/DEPTH is what rises.
  FAN-IN TREE (k -> 1)      §40C, measured: a k-way winner-only fold costs 2*log2(k), never k.
  MIXED                     §2's ordering law: FRONT-LOAD the wide-front nodes; every M-first order
                            beat every A-first order, monotonically.

SCORED BY ONE METRIC (§63): compute/tick = REPLICAS / DEPTH. Topology changes both terms, which is
exactly why it is worth searching and why tuning a single node cannot find it.

  python host/mafab_graph.py            # enumerate topologies over the stored lane circuits
  python host/mafab_graph.py --wide     # include the larger fan-outs
"""
import itertools, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import mafab_laws as L

REG = "C:/llm/models/titan_circuits.json"

# §2, MEASURED: a chained stage costs +6 gate-delays, not its full depth, because the wavefronts
# overlap. This is the number that makes SERIES cheaper than intuition says.
SERIES_OVERLAP = 6


def compose(topology, nodes):
    """Return (depth, gates, replicas_factor) for a topology over `nodes` = [(name, gates, depth)].

    Every rule here is a measured law, cited where it is applied."""
    if not nodes: return 0, 0, 1
    ds = [d for _n, _g, d in nodes]
    gs = [g for _n, g, _d in nodes]
    k = len(nodes)
    if topology == "series":
        # §2 composition law: entry cost is the first stage; each further stage adds the overlap.
        return max(ds) + SERIES_OVERLAP * (k - 1), sum(gs), 1
    if topology == "parallel":
        # §14: independent -> depth is the max, area is the sum, and every node is a replica.
        return max(ds), sum(gs), k
    if topology == "fanin_tree":
        # §40C bank law: a k-way winner-only fold costs 2*log2(k).
        return max(ds) + 2 * max(1, int(math.ceil(math.log2(k)))), sum(gs), k
    if topology == "series_of_banks":
        # two stages, each a bank: §57's split shape. depth = stage depths composed, replicas = the
        # narrower bank (the whole assembly retires that many results per settle).
        half = max(1, k // 2)
        a, b = nodes[:half], nodes[half:] or nodes[:1]
        da = max(d for _n, _g, d in a) + 2 * max(1, int(math.ceil(math.log2(len(a)))))
        db = max(d for _n, _g, d in b) + 2 * max(1, int(math.ceil(math.log2(len(b)))))
        return da + SERIES_OVERLAP, sum(gs), min(len(a), len(b))
    raise KeyError(topology)


def main():
    wide = "--wide" in sys.argv
    reg = json.load(open(REG))
    lanes = sorted((k, int(v["n_gate"]), int(v["depth"])) for k, v in reg.items()
                   if isinstance(v, dict) and int(v.get("n_out") or 0) == 33
                   and int(v.get("n_in") or 0) == 640 and v.get("depth"))
    if not lanes:
        print("no lane circuits with the win|latch[32] interface."); return 1
    print("THE FOUNDRY AS A GRAPH — nodes are muhlnickels, edges are §1E junctions.")
    print("  %d lane nodes available. ONE METRIC (§63): compute/tick = REPLICAS/DEPTH.\n" % len(lanes))
    # counts were MY PRIOR (powers of two, capped, and clipped to what already exists).
    # A topology is worth scoring whether or not the nodes have been written yet.
    counts = [1, 2, 4, 8, 16, 32, 64, 128, 256] + ([1024, 4096] if wide else [])
    tops = ["series", "parallel", "fanin_tree", "series_of_banks"]
    print("  %-16s %5s %9s %14s %10s %16s"
          % ("topology", "nodes", "DEPTH", "gates", "replicas", "compute/tick"))
    rows = []
    for k in counts:
        sub = (lanes * ((k // max(len(lanes), 1)) + 1))[:k]
        for t in tops:
            if t == "series_of_banks" and k < 2: continue
            d, g, rep = compose(t, sub)
            # compute/tick with the topology's replica factor folded in: more replicas means the
            # storage holds proportionally fewer of each, so the metric stays honest.
            ct = L.compute_per_tick(max(g // max(rep, 1), 1), d, True) * rep
            rows.append((ct, t, k, d, g, rep))
            print("  %-16s %5d %9s %14s %10d %16.4f"
                  % (t, k, "{:,}".format(d), "{:,}".format(g), rep, ct))
    rows.sort(reverse=True)
    ct, t, k, d, g, rep = rows[0]
    print("\n  BEST TOPOLOGY: %s over %d nodes -> DEPTH %s, %s gates, %d replicas, compute/tick %.4f"
          % (t, k, "{:,}".format(d), "{:,}".format(g), rep, ct))
    base = [r for r in rows if r[2] == 1]
    if base:
        print("  vs a SINGLE node (%.4f): %.2fx" % (base[0][0], ct / max(base[0][0], 1e-9)))
    print("\n  The laws applied, each measured, not assumed:")
    print("    series      +%d gate-delays per extra stage (§2 wavefront overlap, not full depth)"
          % SERIES_OVERLAP)
    print("    parallel    DEPTH = max, area = sum (§14 independent work is free in latency)")
    print("    fanin_tree  +2*log2(k) for the winner-only fold (§40C, measured bank law)")
    print("\n  Nothing is stored. A topology becomes a circuit only through fab_lateral_bank, which")
    print("  verifies coverage and catches a dropped-slice mutant before it writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
