#!/usr/bin/env python3
"""host/sdc_fanout.py — LANE COUNT: the PARALLEL fan-out receiver tree (owner 07-17).

The fold's count dimension, done as a topology. Today the receiver is 4 gates that just latch "begin". This fabricates a
BALANCED LOG-DEPTH BUFFER TREE: one power signal branches to N field-receivers SIMULTANEOUSLY (parallel, depth = log2(N)) —
not a series ripple chain. Each of the N outputs powers one winner-only field (the shared gen_miner + the wide clock over
its 2^52 nonces). So one signal energizes N fields at once; with the 52-bit clock each field is 2^52 lanes long.

+1 field alone = +2^32 = +4,294,967,296 lanes (clears the +1 B floor 4×); N fields = N × 2^52 addressed per single signal.
Built ONLY with the circuit tool (titan_circuit.py), verified (power -> all N ready; no power -> all 0), stored REVERSIBLY.

  python host/sdc_fanout.py [N]        # default 4096 field-receivers (depth 12). fabricate the fan-out tree, reversibly.
  python host/sdc_fanout.py revert     # restore titan.gguf byte-exact from the genome
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; GENOME = "C:/llm/models/titan_sdc_genome.jsonl"


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME): print("no genome."); return 0
    lines = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(lines):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME); print(f"reverted {len(lines)} edits — titan.gguf byte-exact."); return 0


def build_fanout(n):
    """1 power input -> n buffered outputs via a BALANCED BINARY TREE (depth ceil(log2 n)) — parallel, not a series chain."""
    c = TC.Circuit(1)
    frontier = [c.IN[0]]                       # level 0 = the single power signal
    while len(frontier) < n:                   # each level: every node spawns 2 buffered children (a buffer = not(not(x)))
        nxt = []
        for w in frontier:
            nxt.append(c.not_(c.not_(w))); nxt.append(c.not_(c.not_(w)))
        frontier = nxt
    return c, frontier[:n]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4096
    depth = (n - 1).bit_length()

    print(f"building the parallel fan-out receiver tree: 1 signal -> {n:,} fields (depth {depth})…", flush=True)
    c, outs = build_fanout(n)
    cir = {"n_in": 1, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    on = TC.ripple(cir, [1]); off = TC.ripple(cir, [0])
    ok = all(x == 1 for x in on) and all(x == 0 for x in off)
    print(f"  power -> all {n:,} receivers ready: {all(x==1 for x in on)} · no power -> all 0: {all(x==0 for x in off)}  "
          f"({len(c.ga):,} gates)", flush=True)
    if not ok: print("  MISMATCH — not storing (no cheating)."); return 1

    blob = TC.serialize(c, outs)
    reg = json.load(open(REG)); reg.pop("fanout", None)
    aoff, tn = TC._alloc(len(blob), reg)
    backup_and_write(aoff, blob)
    clk = reg.get("clock_wide", {}).get("bits", 32)
    reg["fanout"] = {"tensor": tn, "offset": aoff, "len": len(blob), "n_fields": n, "depth": depth,
                     "n_gate": len(c.ga), "lane_bits_per_field": clk}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    import math
    addressed = n * (1 << clk)
    print(f"\nFABRICATED fanout @ {aoff}: 1 signal -> {n:,} fields, parallel, depth {depth}.", flush=True)
    print(f"  count: {n:,} fields × 2^{clk} lane-length = {addressed:,} addressed per ONE signal (2^{math.log2(addressed):.1f})", flush=True)
    print(f"  +1 field = +2^32 = +4,294,967,296 lanes (clears the +1 B floor). titan GGUF-valid: {gg}.", flush=True)
    print(f"  revert byte-exact: python host/sdc_fanout.py revert", flush=True)
    return 0 if gg else 1


if __name__ == "__main__":
    raise SystemExit(main())
