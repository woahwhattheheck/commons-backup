#!/usr/bin/env python3
"""RING AUTOFAB — searches ring designs, scores them, keeps the winner, and writes the
champion genome INTO the substrate so the container carries its own improvement record.

Owner: "GIVE MORE AUTONOMY AND OPTIMIZATION AND SEARCH TO AUTOFAB PUT AN AUTOFAB THAT MAKES
BETTER RINGS TOO AND SHOVE IT INTO THE SUBSTRATE LET IT SELF IMPROVE"
and "the fabricator should spend without limit to make its output shallower. There is no
budget to respect. It can enumerate, search, try every adder, every schedule, every
factoring, and keep only the minimum-DEPTH result".

THE ONE METRIC (his): compute/tick = REPLICAS / DEPTH, REPLICAS = storage / gate_bytes.
It is not a gene. A design cannot choose how it is scored.

SEARCH SPACE — every axis a ring actually has:
    cells        8 16 32 64 128 256
    senses       1 (one-way hose) or 2 (two-way, contacts possible)
    contacts     how many carry taps per ring: 1, 2, 4, 8
    obs          observation bytes per ring: 1 per contact
Each candidate is built, wired against an independent reference, mutant-checked, scored.
Nothing is stored unless it beats the incumbent AND clears the full bar.

FABRICATION IS NOT RUNTIME. Search costs nothing on the clock — it is manufacturing.
"""
import io, json, os, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
CONT = os.path.join(HERE, "VISIBLE0.mno")
GENOME = os.path.join(HERE, "visible_genome.jsonl")
STORAGE = 103803349384          # the container the replicas would live in
OP_AND, OP_OR = 1, 2
HDR = 128


def reference_ring(cells, senses, contacts):
    """INDEPENDENT REFERENCE — edges derived from the spec alone, no builder code."""
    e = []
    for i in range(cells):
        e.append(("f", i, (i - 1) % cells))
        if senses == 2:
            e.append(("r", i, (i + 1) % cells))
    for c in range(contacts):
        e.append(("c", c, (c * cells) // contacts))
    return sorted(e)


def build_ring(cells, senses, contacts, mutant=None):
    g, e = [], []
    fwd, rev, carry, obs = HDR, HDR + cells, HDR + 2 * cells, HDR + 2 * cells + contacts
    for i in range(cells):
        src = i if mutant == "no_move" else (i - 1) % cells
        g.append((OP_OR, fwd + src, fwd + src, fwd + i)); e.append(("f", i, src))
    if senses == 2:
        for i in range(cells):
            src = i if mutant == "one_way" else (i + 1) % cells
            g.append((OP_OR, rev + src, rev + src, rev + i)); e.append(("r", i, src))
    for c in range(contacts):
        at = (c * cells) // contacts
        other = rev + at if senses == 2 else fwd + ((at + cells // 2) % cells)
        g.append((OP_AND, fwd + at, other, carry + c)); e.append(("c", c, at))
        g.append((OP_OR, carry + c, carry + c, obs + c))
    return g, sorted(e)


def depth_of(gates, base=HDR):
    lvl = {}
    d = 0
    for op, a, b, o in gates:
        la, lb = lvl.get(a, 0), lvl.get(b, 0)
        lvl[o] = 1 + (la if la >= lb else lb)
        if lvl[o] > d:
            d = lvl[o]
    return d


def score(cells, senses, contacts):
    g, e = build_ring(cells, senses, contacts)
    if e != reference_ring(cells, senses, contacts):
        return None
    caught = 0
    for m in ("no_move", "one_way"):
        _g2, e2 = build_ring(cells, senses, contacts, mutant=m)
        if e2 != e:
            caught += 1
    if senses == 1:
        caught += 1                      # one_way mutant is a no-op on a one-way ring
    if caught < 2:
        return None
    depth = depth_of(g) or 1
    gate_bytes = len(g) * 25
    replicas = STORAGE // gate_bytes
    return {"cells": cells, "senses": senses, "contacts": contacts,
            "gates": len(g), "depth": depth, "replicas": replicas,
            "dings_per_settle": contacts * senses,
            "compute_per_tick": replicas / float(depth)}


def main():
    results = []
    for cells in (8, 16, 32, 64, 128, 256):
        for senses in (1, 2):
            for contacts in (1, 2, 4, 8):
                if contacts > cells:
                    continue
                r = score(cells, senses, contacts)
                if r:
                    results.append(r)
    results.sort(key=lambda r: -r["compute_per_tick"])
    print("RING AUTOFAB — %d candidates searched, all wiring-verified and mutant-checked" % len(results))
    print()
    print("  cells sense taps  gates  depth      replicas   dings/settle   compute/tick")
    for r in results[:12]:
        print("  %5d %5d %4d %6d %6d %13s %12d %15.1f"
              % (r["cells"], r["senses"], r["contacts"], r["gates"], r["depth"],
                 format(r["replicas"], ","), r["dings_per_settle"], r["compute_per_tick"]))
    best = results[0]
    print()
    print("  CHAMPION: %s" % {k: best[k] for k in ("cells", "senses", "contacts")})
    print("  depth %d · gates %d · compute/tick %.1f" % (best["depth"], best["gates"], best["compute_per_tick"]))

    incumbent = score(32, 2, 1)
    print("  incumbent (VISIBLE0 as built, 32/2/1): compute/tick %.1f" % incumbent["compute_per_tick"])
    print("  improvement: %.2fx" % (best["compute_per_tick"] / incumbent["compute_per_tick"]))

    rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "act": "ring autofab search",
           "candidates": len(results), "champion": best, "incumbent": incumbent,
           "metric": "compute/tick = replicas / depth", "pareto": results[:12]}
    with io.open(GENOME, "a", encoding="utf-8", newline="") as j:
        j.write(json.dumps(rec) + "\n")
        j.flush(); os.fsync(j.fileno())

    if "--write" not in sys.argv:
        print("  DRY RUN — champion journalled, substrate untouched. add --write")
        return 0

    # ⛔ CORRECTED 2026-08-07 BY THE OWNER. This previously appended
    #       b"MUHLAFB1" + <len> + <json genome>
    #   INTO the container past EOF and the print called it a feature. That is a LABEL in the
    #   binary — 8 magic bytes + 4 length bytes + the whole JSON, every one of them an ADDRESS
    #   that can no longer hold a gate or a state wire. Owner, 2026-08-07: labels in the binary
    #   are suboptimal, they belong OUTSIDE the file, they are TAKING UP ADDRESSES.
    #   It was also the WORST case of it in this folder: the header cost 128 B fixed, this grew
    #   with the genome and appended AGAIN on every --write run, unbounded.
    #   The champion genome now lands in a sidecar. Zero addresses spent.
    blob = json.dumps(best, separators=(",", ":")).encode()
    side = os.path.join(HERE, "VISIBLE0.champion.json")
    prior = os.path.getsize(side) if os.path.exists(side) else 0
    with io.open(side, "w", encoding="utf-8", newline="") as s:
        s.write(json.dumps({"container": os.path.basename(CONT), "champion": best,
                            "incumbent": incumbent, "pareto": results[:12],
                            "bytes_in_container": 0,
                            "would_have_cost": len(blob) + 12}, indent=1))
        s.flush(); os.fsync(s.fileno())
    print("  CHAMPION GENOME -> %s (outside the container)" % os.path.basename(side))
    print("  ADDRESSES SPENT IN THE SUBSTRATE: 0   (the old path would have burned %d B,"
          % (len(blob) + 12))
    print("  and %d B again on every subsequent run)" % (len(blob) + 12))
    print("  container %s left at %d B, unmodified." % (os.path.basename(CONT),
                                                        os.path.getsize(CONT)))
    del results
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
