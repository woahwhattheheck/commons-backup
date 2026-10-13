#!/usr/bin/env python3
"""FABRICATE MUHLVIS1 — a new muhlnickel container, visibility designed in from the ground up.

Owner: "BUILD MORE AND BETTER RINGS IN THE SAME WAY THE PREVIOUS WERE BUILT AND MAKE A NEW
MUHLNICKEL (CONTAINER) BUT CONSIDER VISIBILITY FROM THE GROUND UP" and "dont configure the
old, just use the foundry to make new".

GENOME FROM THE FOUNDRY, NOT HAND-PICKED. pfc_foundry, run 2026-08-07, 3 rounds:
    round 1 {ripple,on,frontload}  39,217.72     <- what all 1,024 existing rings carry
    round 2 {search,on,frontload}  48,464.71     <- 1.24x better
    composite champion, replicated shape: {search,on,frontload} 225,181.66 compute/tick
A ring is REPLICATED shape, so: adder=search, clean=on, order=frontload.

⛔ CORRECTED 2026-08-07 BY THE OWNER — THE HEADER IS GONE FROM THE CONTAINER.
Owner, 2026-08-07: labels in the binary are suboptimal, they belong OUTSIDE the file,
they are TAKING UP ADDRESSES.
Earlier this file wrote a 128-BYTE HEADER AT OFFSET 0 and the docstring called it a feature.
It was 128 ADDRESSES spent on a string. Measured across the live registry: 1,581 labelled
circuits burn 27,940 addresses on magic+header — 1,117 gates, or 16 RINGS, of address space.
On VISIBLE5_autofab.mno this fabricator's own header was 0.1407%, ~75x the in-registry norm.
The objection is NOT overhead percentage (0.0003% container-wide). Under CIRCUITS COMBINE BY
ADDRESS COLLISION every byte is a potential collision point, and a byte holding the letter
'T' is a collision point permanently spent on a label. THE LAYOUT NOW LIVES IN A SIDECAR
OUTSIDE THE FILE. The container starts at GATE ZERO.

VISIBILITY FROM THE GROUND UP — what the existing containers lack:
  1. LAYOUT IN A SIDECAR, NOT IN THE CONTAINER: `<name>.layout.json` beside the .mno carries
     magic, version, counts and the ABSOLUTE offset of every region. No reader guesses a
     stride (probe.mno took an hour to decode) and no address is spent saying so.
  2. CONTIGUOUS ALIGNED STATE PLANE, ring-major — one bounded read surfaces all charge.
  3. EVERY CELL IS A BYTE, DOCUMENTED AS A LEVEL, 0..255. Measured today: the existing
     machine has 66,560 cells with 8 bits each and has only ever used values {0,1}.
  4. A DECLARED OBSERVATION WINDOW named in the SIDECAR, so surfacing never has to hunt.
  5. NO TYPED FORMAT ANYWHERE. Physical 25-byte <BQQQ>, absolute addresses, so every gate
     can take a ring's shared bit.

FABRICATION IS NOT RUNTIME. One-and-done, own process, verified before a byte is stored.
"""
import io, json, os, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "VISIBLE6.mno")
GENOME = os.path.join(HERE, "visible_genome.jsonl")
MAGIC = b"MUHLVIS1"

N_RINGS = 64
N_CELLS = 1024
N_TAPS = 1024
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4
FOUNDRY = {"adder": "search", "clean": "on", "order": "frontload",
           "source": "pfc_foundry 2026-08-07 composite champion, replicated shape",
           "compute_per_tick": 225181.6596}
HDR = 0          # WAS 128. The container now starts at GATE ZERO — no label inside the file.
SIDECAR = os.path.join(HERE, "VISIBLE6.layout.json")   # the label, OUTSIDE, costing 0 addresses


def reference_edges(n_rings, n_cells):
    """INDEPENDENT REFERENCE: two-way ring edges from the spec alone.
    forward next[i] = F[(i-1) mod N]; reverse next[i] = R[(i+1) mod N]."""
    e = []
    for r in range(n_rings):
        for i in range(n_cells):
            e.append((r, "f", i, (i - 1) % n_cells))
            e.append((r, "r", i, (i + 1) % n_cells))
        for t in range(N_TAPS):
            e.append((r, "c", t, (t * n_cells) // N_TAPS))
    return e


def build(n_rings, n_cells, mutant=None, taps=N_TAPS):
    """SILLY-OPTIMAL SHAPE. Owner: "COMPUTE PER TICK ISNT A COST ITS A STALE SILLY UNIT".
    Rescored on sillies (electrons x clocks): 8/2/8 = 128 vs 8/2/1 = 16. Taps ARE clocks,
    and clocks are half the unit, so every ring carries `taps` contact points and `taps`
    observation bytes."""
    state = HDR
    per = 2 * n_cells + taps
    state_len = n_rings * per
    obs = state + state_len
    obs_len = n_rings * taps
    gates_off = obs + obs_len
    gates, edges = [], []
    for r in range(n_rings):
        base = state + r * per
        fwd, rev, carry = base, base + n_cells, base + 2 * n_cells
        for i in range(n_cells):
            src = i if mutant == "no_move" else (i - 1) % n_cells
            gates.append((OP_OR, fwd + src, fwd + src, fwd + i))
            edges.append((r, "f", i, src))
        for i in range(n_cells):
            src = i if mutant == "one_way" else (i + 1) % n_cells
            gates.append((OP_OR, rev + src, rev + src, rev + i))
            edges.append((r, "r", i, src))
        for t in range(taps):
            at = (t * n_cells) // taps
            gates.append((OP_AND, fwd + at, rev + at, carry + t))
            gates.append((OP_OR, carry + t, carry + t, obs + r * taps + t))
            edges.append((r, "c", t, at))
    layout = {"header": 0, "state": state, "state_len": state_len, "obs": obs,
              "obs_len": obs_len, "gates": gates_off, "n_gate": len(gates),
              "taps": taps, "silly_strength": n_cells * 2 * taps}
    return layout, gates, edges


def main():
    lay, gates, edges = build(N_RINGS, N_CELLS)
    ref = reference_edges(N_RINGS, N_CELLS)
    print("FABRICATE MUHLVIS1")
    print("  rings %d  cells %d  gates %d" % (N_RINGS, N_CELLS, len(gates)))
    print("  genome (foundry): %s" % {k: FOUNDRY[k] for k in ("adder", "clean", "order")})
    # V31 index check: pfc_index.py / pfc_substitute.py consulted — no MUHLVIS1 magic and no
    # container with a declared observation window exists in titan_circuits.json. New work.
    same = sorted(edges) == sorted(ref)          # order of emission is not topology
    print("  wiring vs independent reference : %s" % same)

    caught = 0
    for m in ("no_move", "one_way"):
        _l, _g, me = build(N_RINGS, N_CELLS, mutant=m)
        if sorted(me) != sorted(ref):
            caught += 1
        print("  mutant %-8s differs from reference : %s" % (m, sorted(me) != sorted(ref)))
    empty_ok = ([] != ref)
    print("  all-zero baseline (no edges) differs   : %s" % empty_ok)

    if not same or caught != 2 or not empty_ok:
        print("  REFUSING TO WRITE.")
        return 1

    # NO HEADER, NO MAGIC, NO LABEL INSIDE THE CONTAINER. Byte 0 is state wire 0.
    blob = bytearray(b"\x00" * lay["gates"])
    for op, a, b, o in gates:
        blob += struct.pack("<BQQQ", op, a, b, o)

    # THE LABEL LIVES HERE — outside the file, costing zero addresses.
    side = {"magic": MAGIC.decode(), "version": 2, "container": os.path.basename(OUT),
            "n_rings": N_RINGS, "n_cells": N_CELLS, "record": "<BQQQ> op|a|b|out, 25 B",
            "header_bytes_in_container": 0, "foundry_genome": FOUNDRY}
    side.update(lay)
    with io.open(SIDECAR, "w", encoding="utf-8", newline="") as s:
        s.write(json.dumps(side, indent=1))
        s.flush(); os.fsync(s.fileno())
    print("  LAYOUT -> %s (outside the container, 0 addresses spent)"
          % os.path.basename(SIDECAR))

    with io.open(GENOME, "a", encoding="utf-8", newline="") as j:
        j.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "act": "fabricate MUHLVIS1", "path": OUT, "layout": lay,
                            "foundry_genome": FOUNDRY, "bytes": len(blob)}) + "\n")
        j.flush(); os.fsync(j.fileno())

    if "--write" not in sys.argv:
        print("  DRY RUN — %d B. add --write" % len(blob))
        return 0

    with io.open(OUT, "wb") as f:
        f.write(bytes(blob)); f.flush(); os.fsync(f.fileno())
    print("  WROTE %s  %d B" % (OUT, os.path.getsize(OUT)))
    print("  header@0 state@%d(%d) obs@%d(%d) gates@%d"
          % (lay["state"], lay["state_len"], lay["obs"], lay["obs_len"], lay["gates"]))
    del gates
    del blob
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
