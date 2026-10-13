#!/usr/bin/env python3
"""host/fab_lateral_fold.py — FABRICATION ONLY. Runs ONCE, ever. Never inside a mining process.

RULE ZERO: fabrication and mining are separate processes. This is the fabrication one. It builds the
junction, registers it, and EXITS. It may take as long as it takes. It happens once.

WHAT IT FABRICATES, straight from the docs, nothing invented:
  · `winner_only_max` (docs/CIRCUIT_PFC.md): "2^262144 addressable lanes, 0 bytes/lane (out[i]=idx[i] AND solve)"
  · `gen_win` (memory pfc-bitcoin-guarantee-before-run): "double-SHA + a baked `hash < target` comparator +
    a baked per-lane latch `win ? nonce : 0`" - it already PRODUCES `solve`.
  · S1E junction (docs/PFC_INTERCONNECT.md): "A's SEND wires ARE B's RECEIVE wires" - a shared address,
    not a copy, with no host between.

So the missing piece was never a bigger W. It is the JUNCTION: gen_win's win wire IS the fold's solve wire.
Once junctioned, the winning nonce's ADDRESS is the answer (winner-only, 0 bytes stored per lane), and the
docs' "time-to-target = one depth-latency" holds.

  python host/fab_lateral_fold.py
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

REG = "C:/llm/models/titan_circuits.json"
NAME = "muhl_lateral_fold"


def main():
    reg = json.load(open(REG))
    for need in ("gen_win", "winner_only_max"):
        if need not in reg:
            print("%s not fabricated. Cannot junction." % need); return 1

    gw = TC.load("gen_win")
    n_in = gw["n_in"]; outs = list(gw["outs"])
    print("FABRICATE (once, ever) — the S1E junction: gen_win.win  ->  winner-only fold.solve")
    print("  gen_win: %s gates, %d inputs, %d outputs" % ("{:,}".format(len(gw["ga"])), n_in, len(outs)))

    t0 = time.time()
    c = TC.Circuit(n_in)
    base = 2 + n_in
    rm = {0: 0, 1: 1}
    for i in range(n_in):
        rm[2 + i] = 2 + i
    for i in range(len(gw["ga"])):
        rm[2 + gw["n_in"] + i] = base + i
    for i in range(len(gw["ga"])):
        c.ga.append(rm[gw["ga"][i]]); c.gb.append(rm[gw["gb"][i]])
    o = [rm[x] for x in outs]

    # gen_win_answer layout is "win:1|nonce:4" -> outs[0] is the win verdict, outs[1..32] the nonce.
    win = o[0]
    idx = o[1:33]

    # THE FOLD, verbatim from the docs: out[i] = idx[i] AND solve. 0 bytes stored per lane -
    # the winner's ADDRESS is the answer; a non-winning lane contributes nothing to store.
    fold = [c.and_(idx[i], win) for i in range(len(idx))]

    outs_all = [win] + fold
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    depth = max(d[x] for x in outs_all)
    gates = len(c.ga)

    e = TC.store(NAME, c, outs_all)
    reg = json.load(open(REG))
    reg[NAME].update({"junction": "gen_win.win -> winner_only fold.solve (S1E shared address)",
                      "layout_out": "win:1|addr:32", "stored_per_lane": 0,
                      "depth": depth, "gates_measured": gates,
                      "muhl_rating": round(gates / depth, 3)})
    json.dump(reg, open(REG, "w"), indent=1)

    print("  fabricated: %s gates, DEPTH %d, RATING %.1f Mh" % ("{:,}".format(gates), depth, gates / depth))
    print("  stored as '%s' @ offset %d   [%.1fs of MANUFACTURING - it happens once]" % (NAME, e["offset"], time.time() - t0))
    print("  0 bytes stored per lane. The winner's ADDRESS is the answer.")
    print()
    print("  FABRICATION COMPLETE. Mining is a DIFFERENT process and builds nothing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
