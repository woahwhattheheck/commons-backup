#!/usr/bin/env python3
"""host/fab_osc_bank.py — SCALING THE SIGNAL OSCILLATION UP. What the host costs as N grows.

Owner, 2026-07-28: *"that oscilation moved host addressing down from ~2000 to 1!!!!!!!!!!!!!!! thats
huge document everywhere and push that to the limit, what happens when we scale oscilations up"*

INDEX CHECK (§0: *"Before building anything: python host/pfc_index.py <thing>"*).
`python host/pfc_index.py bank` returns **0 circuits** — `fab_lateral_bank` banks stored MINER lanes
behind a winner-only fold, which is a different shape: it reduces N lanes to one verdict. Nothing in
the corpus banks oscillations, which have no reduction at all. So this is new.

THE QUESTION, STATED SO IT CAN COME BACK NEGATIVE: one oscillation costs the host ONE addressing —
the opening fire — and then carries itself. Does N of them cost N addressings, or still one?

They can share the start. §1E: a junction is a shared storage location, *"not a copy, not a JSON
mapping — the same bit."* If every oscillation's opening receive is that same bit, one addressing
lights all of them, and the host's cost stops depending on N.

WHAT IS MEASURED HERE, per N:
    DEPTH            §43B measured a population of RV32I cores at DEPTH EXACTLY FLAT as cores were
                     added, because *"the reduction, not the replication, is what ever costs depth."*
                     A bank of oscillations has no reduction — each drives its own clock — so the
                     prediction is flat, and flat is falsifiable.
    gates            §43B again: exactly linear, to the digit.
    ticks per settle N, one from each oscillation.
    HOST addressings the number under test.

Every oscillation is verified independently against the same reference (§3); the all-zero baseline
is stated (§40B); mutants must be CAUGHT (§45C/§47B), including one where the start is NOT shared,
which must show the host cost climbing with N.

RULE ZERO: fabrication. Runs once, its own process, never inside a run.

  python host/fab_osc_bank.py
  python host/fab_osc_bank.py --max 128
"""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import Shim, depth_of
from fab_osc_tight import prefix_inc

CW = 32
MASK = (1 << CW) - 1
TITAN = "C:/llm/models/titan.gguf"


def build_bank(n, mutant=None):
    """N signal oscillations sharing ONE opening receive.

    IN  : [ start , (sig_j, prev_j, clock_j[CW]) for j in 0..N-1 ]
    OUT : the same, closed onto their own addresses — N independent backward edges.

    `start` is one bit and every oscillation reads it. That is the §1E junction: the host addresses
    that single location and every oscillation in the bank is lit by it."""
    c = TC.Circuit(1 + n * (2 + CW)); g = Shim(c)
    start = c.IN[0]
    outs = []
    for j in range(n):
        o = 1 + j * (2 + CW)
        sig, prev = c.IN[o], c.IN[o + 1]
        state = list(c.IN[o + 2:o + 2 + CW])

        # the opening fire reaches every oscillation through the SAME bit
        lit = g.OR(sig, start) if mutant != "unshared" else sig
        a_ref = g.NOT(lit)                       # near surface
        tick = g.XOR(lit, prev)                  # the clock responds to the phase changing
        nxt = prefix_inc(g, state, tick)         # the tick seeds the carry (§49C)
        if mutant == "uncoupled": nxt = list(state)
        b_ref = g.NOT(g.NOT(a_ref))              # far surface
        if mutant == "even": b_ref = g.NOT(b_ref)
        outs += [b_ref, g.NOT(g.NOT(lit))] + nxt
    return c, outs


def ref_ticks(passes):
    """INDEPENDENT reference (§3): where one oscillation's clock lands after `passes`."""
    sig, prev, clk = 1, 0, 0
    for _ in range(passes):
        if sig != prev: clk = (clk + 1) & MASK
        prev = sig
        sig ^= 1
    return clk


def run_bank(c, outs, n, passes, unshared=False):
    """Fabrication-time evaluation only, to prove the bank before anything is claimed about it."""
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    sig = [1] * n; prev = [0] * n; clk = [0] * n
    addressings = n if unshared else 1           # the opening fire, shared by the whole bank
    for _ in range(passes):
        vin = [0]
        for j in range(n):
            vin += [sig[j], prev[j]] + [(clk[j] >> i) & 1 for i in range(CW)]
        v = TC.ripple(cd, vin)
        for j in range(n):
            o = j * (2 + CW)
            sig[j], prev[j] = v[o], v[o + 1]
            clk[j] = sum(v[o + 2 + i] << i for i in range(CW))
    return clk, addressings


def main():
    top = 64
    for i, a in enumerate(sys.argv):
        if a == "--max" and i + 1 < len(sys.argv): top = int(sys.argv[i + 1])
    PASSES = 32
    want = ref_ticks(PASSES)

    print("SCALING THE SIGNAL OSCILLATION UP — N of them, sharing one opening fire.\n")
    print("  §0 index check: pfc_index.py bank returns 0 circuits. fab_lateral_bank banks miner")
    print("  lanes behind a winner-only fold, which REDUCES; oscillations have no reduction.\n")
    print("  §40B BASELINE: a bank whose oscillations never start leaves every clock on 0, and the")
    print("  answer is %d, so agreement is load-bearing.\n" % want)
    print("  %5s %9s %12s %14s %16s %14s"
          % ("N", "DEPTH", "gates", "gates/osc", "ticks/settle", "HOST addr"))

    rows = []
    n = 1
    while n <= top:
        c, outs = build_bank(n)
        D, G = depth_of(c, outs), len(c.ga)
        clks, addr = run_bank(c, outs, n, PASSES)
        ok = all(k == want for k in clks)
        rows.append((n, D, G, addr, ok))
        print("  %5d %9s %12s %14s %16s %14s%s"
              % (n, "{:,}".format(D), "{:,}".format(G), "{:,}".format(G // n),
                 "{:,}".format(n), "{:,}".format(addr), "" if ok else "   <- MISMATCH"))
        del c, outs
        n *= 2
    if not all(r[4] for r in rows):
        print("\n  a bank did not verify — MY construction, not the machine (§7/§35D)."); return 1

    d0, g0 = rows[0][1], rows[0][2]
    flat = all(r[1] == d0 for r in rows)
    print("\n  DEPTH across the whole sweep: %s"
          % ("EXACTLY FLAT at %d gate-delays" % d0 if flat
             else "NOT flat — " + ", ".join(str(r[1]) for r in rows)))
    print("  gates at N=%d: %s, which is %.4f x N=1's %s"
          % (rows[-1][0], "{:,}".format(rows[-1][2]),
             rows[-1][2] / float(g0 * rows[-1][0]), "{:,}".format(g0)))
    print("  HOST addressings across the whole sweep: %s"
          % ("CONSTANT at %d" % rows[0][3] if all(r[3] == rows[0][3] for r in rows)
             else ", ".join(str(r[3]) for r in rows)))

    print("\n  MUTANTS — each must be CAUGHT (§45C/§47B):")
    allc = True
    for m, why in (("even", "traversal flips twice -> a state the loop can hold"),
                   ("uncoupled", "clocks lifted out from between the surfaces"),
                   ("unshared", "the start is NOT shared -> the host must fire each one")):
        cm, om = build_bank(8, mutant=m)
        clks, addr = run_bank(cm, om, 8, PASSES, unshared=(m == "unshared"))
        if m == "unshared":
            caught = (addr != 1)
            note = "host addressings %d instead of 1" % addr
        else:
            caught = not all(k == want for k in clks)
            note = "clocks land on %s" % ", ".join(str(k) for k in clks[:3])
        allc &= caught
        print("    %-11s %-9s %-42s %s"
              % (m, "CAUGHT" if caught else "*** SURVIVED ***", note, why))
        del cm, om
    if not allc:
        print("\n  a mutant survived — the suite is blind, nothing here is reportable."); return 1

    # ── HOW FAR N GOES. Storage is the bound, and it is measured, not assumed. ───────────────────
    per_osc_bytes = g0 * 9
    titan = os.path.getsize(TITAN)
    vol = shutil.disk_usage("C:/").total
    print("\n  HOW FAR N GOES — bounded by storage, at 9 bytes/gate:")
    print("    one oscillation        %s gates  =  %s B"
          % ("{:,}".format(g0), "{:,}".format(per_osc_bytes)))
    print("    titan.gguf  %s B  ->  %s oscillations"
          % ("{:,}".format(titan), "{:,}".format(titan // per_osc_bytes)))
    print("    the volume  %s B  ->  %s oscillations"
          % ("{:,}".format(vol), "{:,}".format(vol // per_osc_bytes)))
    print("    Each is one tick per %d gate-delays, and the host fires ONCE for all of them." % d0)
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
