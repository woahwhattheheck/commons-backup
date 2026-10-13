#!/usr/bin/env python3
"""host/fab_osc_tight.py — THE SURFACES BROUGHT AS CLOSE AS THEY GO.

Owner, 2026-07-28: *"so make the oscilation faster, tighter, bring the reflecters closer to each
other shorten the distance to the min"*

INDEX CHECK (§0). `python host/pfc_index.py clock` — `muhl_signal_osc` is the standing oscillation
at DEPTH 28, and `pfc_clock_counter` is the non-oscillating clock. This searches for a shorter
distance between the surfaces and stores it ADDITIVELY; nothing already fabricated is disturbed
(CLAUDE.md #8).

WHAT SETS THE DISTANCE. The period is the round-trip DEPTH, and the round trip is dominated by the
one thing between the surfaces — the clock's advance. In `muhl_signal_osc` that advance ran through
a general adder from the searched family and then through a mux that gated it on the tick. Two
measured facts in the docs shorten both halves:

  §45B  *"for +1, the carry into bit i is AND(X[0..i-1]) — an associative scan, so it reduces as a
         prefix."*  A 64-bit increment measured 140 -> 17 gate-delays, 8.2x, for 8 more gates.
  §49C  *"that `+1` is a CARRY-IN — a Kogge-Stone prefix accepts one for free by seeding the
         generate term at bit 0."*

Seed the scan with the TICK rather than with a constant 1 and the gating mux leaves the path
altogether: the clock advances by the tick. So the distance becomes one prefix AND-scan plus one
XOR, and the surfaces close to that.

FIVE CONSTRUCTIONS ARE BUILT AND MEASURED, not chosen (§31A — manufacturing is off the clock, so
enumerate). The shallowest that verifies is what gets stored.

Verified against an independent Python reference (§3), all-zero baseline stated (§40B), mutants that
must be CAUGHT (§45C/§47B).

RULE ZERO: fabrication. Runs once, its own process, never inside a run.

  python host/fab_osc_tight.py --dry
  python host/fab_osc_tight.py
  python host/fab_osc_tight.py revert
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import family, Shim, depth_of

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_osctight_genome.jsonl"
MAGIC = b"TITANCIR"
NAME = "muhl_signal_osc_tight"

CW = 32
MASK = (1 << CW) - 1


def prefix_inc(g, x, cin):
    """x + cin, as a prefix AND-scan. §45B: the carry into bit i is AND(cin, x[0..i-1]).

    An associative scan reduces in log2(W) rounds instead of W, which is the whole reason this is
    shorter than routing the advance through a general adder."""
    W = len(x)
    terms = [cin] + list(x[:W - 1])          # carry[i] = AND over terms[0..i]
    lvl, d = list(terms), 1
    while d < len(lvl):
        nxt = list(lvl)
        for i in range(d, len(lvl)):
            nxt[i] = g.AND(lvl[i], lvl[i - d])
        lvl, d = nxt, d * 2
    return [g.XOR(x[i], lvl[i]) for i in range(W)]


def build(kind, adder="kogge", mutant=None, W=None):
    """The signal oscillation. surface | clock | surface, with the distance under search."""
    CW = W or globals()["CW"]
    c = TC.Circuit(2 + CW); g = Shim(c)
    sig, prev = c.IN[0], c.IN[1]
    state = list(c.IN[2:2 + CW])

    # ── near surface — one NAND with its inputs tied. This is as short as a reflector gets. ───────
    a_ref = g.NOT(sig)
    if mutant == "surface_a_open": a_ref = sig

    tick = g.XOR(sig, prev)                  # the clock responds to the phase changing

    # ── the clock — the only thing between the surfaces. Several ways to build the advance. ───────
    if kind == "prefix_seeded":
        nxt = prefix_inc(g, state, tick)                     # the tick IS the carry-in (§49C)
    elif kind == "prefix_muxed":
        inc = prefix_inc(g, state, g.C1)
        nxt = [g.OR(g.AND(tick, inc[i]), g.AND(g.NOT(tick), state[i])) for i in range(CW)]
    else:
        add = family(32)[adder]
        inc = add(g, state, [g.C1] + [g.C0] * (CW - 1))[:CW]
        nxt = [g.OR(g.AND(tick, inc[i]), g.AND(g.NOT(tick), state[i])) for i in range(CW)]
    if mutant == "clock_uncoupled": nxt = list(state)

    # ── far surface. A buffer, so ONE inversion survives a traversal and the loop cannot settle. ──
    b_ref = g.NOT(g.NOT(a_ref))
    if mutant == "even_inversions": b_ref = g.NOT(b_ref)
    if mutant == "surface_b_open": b_ref = g.C0

    return c, [b_ref, g.NOT(g.NOT(sig))] + nxt


def ref_osc(passes):
    """INDEPENDENT reference (§3): plain Python, no circuit consulted."""
    sig, prev, clk, seq = 1, 0, 0, []
    for _ in range(passes):
        if sig != prev: clk = (clk + 1) & MASK
        prev = sig
        sig ^= 1
        seq.append((sig, clk))
    return seq


def run_osc(c, outs, passes):
    """Fabrication-time evaluation only, to prove it oscillates before it is stored."""
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    sig, prev, clk, seq = 1, 0, 0, []
    for _ in range(passes):
        v = TC.ripple(cd, [sig, prev] + [(clk >> i) & 1 for i in range(CW)])
        sig, prev = v[0], v[1]
        clk = sum(v[2 + i] << i for i in range(CW))
        seq.append((sig, clk))
    return seq


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob); f.flush(); os.fsync(f.fileno())


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG)); reg.pop(NAME, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d entry(s); the file is byte-identical to before." % len(ent)); return 0


def sweep():
    """HOW LOW THE DISTANCE GOES, and what sets the floor. Measured, not derived.

    The path between the surfaces is: the tick detector, the prefix scan, the sum. Only the scan
    depends on the clock's width, and it depends on it as log2. So the floor is a CURVE, not a
    single number, and the honest answer to 'as low as possible' is where on that curve you want
    to sit — a narrower clock wraps sooner."""
    print("THE FLOOR — period against clock width, every row built and measured.\n")
    print("  %6s %10s %10s %14s" % ("width", "DEPTH", "gates", "wraps after"))
    prev_d = None
    for W in (4, 8, 16, 32, 64):
        c, outs = build("prefix_seeded", W=W)
        D, G = depth_of(c, outs), len(c.ga)
        step = "" if prev_d is None else "  (+%d)" % (D - prev_d)
        print("  %6d %10s %10s %14s%s"
              % (W, "{:,}".format(D), "{:,}".format(G), "2^%d ticks" % W, step))
        prev_d = D
        del c, outs
    print("\n  Doubling the width costs +2 gate-delays — the scan is log2, so the distance grows")
    print("  logarithmically while the clock's range grows exponentially. §40C measured the same")
    print("  +2-per-doubling shape on bank width; it is the same law appearing in the clock.")
    print("\n  The floor is not a single number. A 4-bit clock sits at the shortest distance and")
    print("  wraps after 16 ticks; a 64-bit clock costs 8 more gate-delays and wraps after 2^64.")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    if "--sweep" in sys.argv: return sweep()
    dry = "--dry" in sys.argv
    PASSES = 64
    want = ref_osc(PASSES)

    print("BRINGING THE SURFACES CLOSER — the distance is what sets the period (§24).\n")
    print("  The standing oscillation, muhl_signal_osc, holds them 28 gate-delays apart. What sits")
    print("  between them is the clock's advance, so shortening that is what closes the gap.\n")
    stuck = [(1, 0)] * PASSES
    print("  §40B BASELINE: a loop that never oscillates matches %d/%d passes.\n"
          % (sum(1 for i in range(PASSES) if stuck[i] == want[i]), PASSES))

    cands = [("prefix_seeded", "kogge", "tick seeds the carry — no gating mux in the path (§49C)"),
             ("prefix_muxed", "kogge", "prefix increment, tick gates it through a mux (§45B)")]
    for ad in ("kogge", "brentkung", "ripple"):
        cands.append(("family_" + ad, ad, "the searched adder family — what muhl_signal_osc used"))

    print("  %-16s %8s %9s  %-7s %s" % ("construction", "DEPTH", "gates", "verify", "why"))
    best = None
    for kind, ad, why in cands:
        c, outs = build(kind, ad)
        got = run_osc(c, outs, PASSES)
        ok = sum(1 for i in range(PASSES) if got[i] == want[i])
        D, G = depth_of(c, outs), len(c.ga)
        print("    %-16s %8s %9s  %d/%-5d %s"
              % (kind, "{:,}".format(D), "{:,}".format(G), ok, PASSES, why))
        if ok == PASSES and (best is None or D < best[2]):
            best = (kind, ad, D, G)
        del c, outs
    if best is None:
        print("\n  nothing oscillated — MY construction, not the machine (§7/§35D)."); return 1
    kind, ad, D, G = best

    print("\n  SHORTEST DISTANCE FOUND: %s" % kind)
    print("    surfaces %s gate-delays apart, %s gates" % ("{:,}".format(D), "{:,}".format(G)))
    print("    standing oscillation muhl_signal_osc was 28 apart -> %.2fx tighter" % (28.0 / D))
    print("    Attribution (§48E), and it is a measurement of MY construction rather than of the")
    print("    machine: the advance was re-implemented as a prefix AND-scan seeded by the tick, and")
    print("    the period fell with it. What got shorter is the clock I built.")

    print("\n  MUTANTS — each must be CAUGHT (§45C/§47B):")
    allc = True
    for m in ("even_inversions", "surface_a_open", "surface_b_open", "clock_uncoupled"):
        cm, om = build(kind, ad, mutant=m)
        gm = run_osc(cm, om, PASSES)
        okm = sum(1 for i in range(PASSES) if gm[i] == want[i])
        caught = okm != PASSES; allc &= caught
        print("    %-16s %2d/%-4d %s" % (m, okm, PASSES, "CAUGHT" if caught else "*** SURVIVED ***"))
        del cm, om
    if not allc:
        print("\n  a mutant survived — the suite is blind, storing nothing."); return 1

    if dry:
        print("\n  --dry: nothing written."); return 0
    reg = json.load(open(REG))
    if NAME in reg:
        print("\n  %s already stored @ %s. revert first." % (NAME, reg[NAME]["offset"])); return 0
    c, outs = build(kind, ad)
    G = len(c.ga)
    body = struct.pack("<%di" % G, *c.ga) + struct.pack("<%di" % G, *c.gb) + \
           struct.pack("<%di" % len(outs), *outs)
    blob = MAGIC + struct.pack("<IIII", c.n_in, c.n_wire(), G, len(outs)) + body
    off, tn = TC._alloc(len(blob), reg)
    t0 = time.time(); _journal(off, blob)
    reg = json.load(open(REG))
    reg[NAME] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": c.n_in,
                 "n_wire": c.n_wire(), "n_gate": G, "n_out": len(outs), "format": "nand2",
                 "depth": D, "gates_measured": G, "construction": kind,
                 "signal_oscillation": True, "clock_width": CW, "period_gate_delays": D,
                 "backward_edges": [{"out": 0, "in": 0, "what": "signal — surface to surface"},
                                    {"out": 1, "in": 1, "what": "previous phase — the tick detector"}] +
                                   [{"out": 2 + i, "in": 2 + i, "what": "clock bit %d" % i}
                                    for i in range(CW)],
                 "note": "THE SIGNAL OSCILLATION, SURFACES AT MINIMUM DISTANCE (owner 2026-07-28: "
                         "'bring the reflecters closer to each other shorten the distance to the "
                         "min'). The advance is a prefix AND-scan seeded by the tick, per S45B and "
                         "S49C, so no gating mux sits in the path. PERIOD %d gate-delays against "
                         "muhl_signal_osc's 28. Verified vs an independent reference over 64 "
                         "passes, 4 mutants CAUGHT. Additive — muhl_signal_osc untouched." % D}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  STORED '%s' @ %s (%s B) [%.2fs byte edit]  titan GGUF-valid: %s"
          % (NAME, off, "{:,}".format(len(blob)), time.time() - t0, valid))
    print("  revert: python host/fab_osc_tight.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
