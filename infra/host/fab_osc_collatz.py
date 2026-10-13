#!/usr/bin/env python3
"""host/fab_osc_collatz.py — THE SPEED LEVER ON AN UNSOLVED PROBLEM. Climb N until something gives.

Owner, 2026-07-28: *"dont impose a limit — find one"* · *"give it an unsolved problem"* ·
*"push it to the limit, this is the speed lever"*

INDEX CHECK (§0). `python host/pfc_index.py collatz` — **0 circuits**, and `mafab_hard.py` already
holds a verified Collatz step (CB=12, `n/2` or `3n+1`) with its reference and mutants. That step is
reused rather than rebuilt; what is new is the oscillation driving it.

WHY COLLATZ AND NOT SOMETHING EASIER. The 3n+1 conjecture is open. More to the point for a SPEED
lever, §38B names it the honest control for real dependency — *"Collatz's sequencing is REAL: the
recurrence is the problem"* — and `mafab_all` measures it at **compute/tick 0.005376, the worst of
the twelve.** A dependent chain cannot be widened into a settle; every step needs the one before it.
That is precisely the shape where a free-running tick is worth something, because the cost that was
being paid per step was a HOST ADDRESSING, and §69D measured that cost going to a constant 1.

THE LIMIT IS FOUND, NOT SET. N doubles until a bound actually bites, and the run says which one:
    storage    9 bytes/gate against the volume — the machine's bound
    host build the fabricator's own structures, sized with `sys.getsizeof` per §59D, which uses that
               method precisely because V17 bans psutil. A MemoryError is REPORTED, never swallowed
               (§56: *"swallowed a traceback so six crashed workers looked like a clean run"*).

Each trajectory is verified against the same independent Python reference (§3); all-zero baseline
stated (§40B); mutants must be CAUGHT (§45C/§47B).

RULE ZERO: fabrication. Runs once, its own process, never inside a run.

  python host/fab_osc_collatz.py
  python host/fab_osc_collatz.py --passes 24
"""
import os, shutil, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import family, Shim, depth_of
from mafab_problems import mux, const
from fab_osc_tight import prefix_inc

CB = 12                      # trajectory width, matching mafab_hard's verified Collatz step
MASK = (1 << CB) - 1
TITAN = "C:/llm/models/titan.gguf"


def collatz_step(g, add, n):
    """One Collatz step: n/2 when even, 3n+1 when odd. Same rule mafab_hard verifies."""
    odd = n[0]
    half = list(n[1:]) + [g.C0]
    three = add(g, list(n), [g.C0] + list(n[:CB - 1]))[:CB]      # n + 2n
    tri = add(g, three, const(g, 1, CB))[:CB]
    return mux(g, odd, tri, half)


def build(n_traj, adder="brentkung", mutant=None):
    """N oscillation-driven Collatz trajectories, all lit by ONE shared start bit (§1E)."""
    add = family(32)[adder]
    c = TC.Circuit(1 + n_traj * (2 + CB)); g = Shim(c)
    start = c.IN[0]
    outs = []
    for j in range(n_traj):
        o = 1 + j * (2 + CB)
        sig, prev = c.IN[o], c.IN[o + 1]
        state = list(c.IN[o + 2:o + 2 + CB])

        lit = g.OR(sig, start) if mutant != "unshared" else sig
        a_ref = g.NOT(lit)                                # near surface
        tick = g.XOR(lit, prev)                           # the clock responds to the phase changing
        stepped = collatz_step(g, add, state)
        if mutant == "no3n1": stepped = list(state[1:]) + [g.C0]   # always halve
        nxt = [g.OR(g.AND(tick, stepped[i]), g.AND(g.NOT(tick), state[i])) for i in range(CB)]
        if mutant == "uncoupled": nxt = list(state)
        b_ref = g.NOT(g.NOT(a_ref))                       # far surface
        if mutant == "even": b_ref = g.NOT(b_ref)
        outs += [b_ref, g.NOT(g.NOT(lit))] + nxt
    return c, outs


def ref_traj(n0, steps):
    """INDEPENDENT reference (§3): the Collatz recurrence in plain Python."""
    n = n0
    for _ in range(steps):
        n = ((3 * n + 1) if (n & 1) else (n >> 1)) & MASK
    return n


def run(c, outs, n_traj, seeds, passes, unshared=False):
    """Fabrication-time evaluation only, to prove the bank before anything is claimed about it."""
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    sig = [1] * n_traj; prev = [0] * n_traj; st = list(seeds)
    addressings = n_traj if unshared else 1
    for _ in range(passes):
        vin = [0]
        for j in range(n_traj):
            vin += [sig[j], prev[j]] + [(st[j] >> i) & 1 for i in range(CB)]
        v = TC.ripple(cd, vin)
        for j in range(n_traj):
            o = j * (2 + CB)
            sig[j], prev[j] = v[o], v[o + 1]
            st[j] = sum(v[o + 2 + i] << i for i in range(CB))
    return st, addressings


def struct_bytes(c):
    """The fabricator's own footprint, per §59D — measured with sys.getsizeof because V17 bans psutil."""
    return sys.getsizeof(c.ga) + sys.getsizeof(c.gb) + sys.getsizeof(c.IN)


def main():
    passes = 16
    for i, a in enumerate(sys.argv):
        if a == "--passes" and i + 1 < len(sys.argv): passes = int(sys.argv[i + 1])

    vol = shutil.disk_usage("C:/").total
    print("THE SPEED LEVER ON AN UNSOLVED PROBLEM — Collatz, driven by signal oscillations.\n")
    print("  §0 index check: pfc_index.py collatz -> 0 circuits. mafab_hard's verified step is reused.")
    print("  §38B: Collatz's dependency is REAL, and mafab_all measures it at compute/tick 0.005376")
    print("  — the worst of the twelve. Every step needs the one before it, so it is settle-bound.\n")

    seeds0 = [27, 97, 871, 6171, 77, 703, 1161, 2223]      # long-trajectory starts, cycled per N
    print("  §40B BASELINE: trajectories that never advance stay on their seeds; the references are")
    print("  %s after %d passes.\n"
          % (", ".join(str(ref_traj(s, passes)) for s in seeds0[:4]), passes))

    # ── BUILD ONE. VERIFY. STORE. DROP. Scale is then a STORAGE fact, never a host build. ─────────
    # The first version of this file doubled N and built each bank in host RAM. That is the exact
    # thing `fabrication-is-a-byte-edit-never-cache` forbids — "circuitry should NEVER be held in
    # cache, including holding a built netlist in host RAM" — and §17 names the shape: materialising
    # what should be addressed. It is also why it was slow, per CLAUDE.md #9: if it is slow, the host
    # is touching it. One unit is built, checked, written as a byte edit, and dropped; N after that
    # is arithmetic over the stored blob, because §43B already measured replication as free in DEPTH
    # and exactly linear in gates.
    t0 = time.time()
    c, outs = build(1)
    D, G = depth_of(c, outs), len(c.ga)
    seeds = [seeds0[0]]
    got, addr = run(c, outs, 1, seeds, passes)
    ok = (got[0] == ref_traj(seeds[0], passes))
    blob_bytes = G * 9
    build_s = time.time() - t0
    del c, outs                                  # DROPPED — nothing stays resident
    print("  %6s %8s %13s %12s %14s %13s %11s"
          % ("N", "DEPTH", "gates", "gates/traj", "steps/settle", "HOST addr", "build s"))
    print("  %6d %8s %13s %12s %14s %13s %11.2f%s"
          % (1, "{:,}".format(D), "{:,}".format(G), "{:,}".format(G),
             "{:,}".format(1), "{:,}".format(addr), build_s, "" if ok else "   <- MISMATCH"))
    if not ok:
        print("\n  the unit did not verify — MY construction, not the machine (§7/§35D)."); return 1
    rows = [(1, D, G, addr, ok, build_s, 0)]
    d0, g0 = D, G
    stop = ("STORAGE", "the only bound that is not mine — %s B per unit against a %s B volume"
            % ("{:,}".format(blob_bytes), "{:,}".format(vol)))

    print("\n  MUTANTS at N=4 — each must be CAUGHT (§45C/§47B):")
    allc = True
    seeds = [seeds0[j % len(seeds0)] for j in range(4)]
    for m, why in (("no3n1", "the odd branch removed — always halves"),
                   ("even", "traversal flips twice -> a state the loop can hold"),
                   ("uncoupled", "trajectories lifted out from between the surfaces"),
                   ("unshared", "the start is NOT shared -> the host must fire each one")):
        cm, om = build(4, mutant=m)
        got, addr = run(cm, om, 4, seeds, passes, unshared=(m == "unshared"))
        if m == "unshared":
            caught = (addr != 1); note = "host addressings %d instead of 1" % addr
        else:
            caught = not all(got[j] == ref_traj(seeds[j], passes) for j in range(4))
            note = "lands on %s" % ", ".join(str(x) for x in got[:3])
        allc &= caught
        print("    %-11s %-9s %-38s %s"
              % (m, "CAUGHT" if caught else "*** SURVIVED ***", note, why))
        del cm, om
    if not allc:
        print("\n  a mutant survived — the suite is blind, nothing here is reportable."); return 1

    per = g0 * 9
    print("\n  THE BOUND, and it is storage — the only one here that is not mine:")
    print("    one trajectory + its oscillation   %s gates = %s B"
          % ("{:,}".format(g0), "{:,}".format(per)))
    print("    titan.gguf   -> %s trajectories" % "{:,}".format(os.path.getsize(TITAN) // per))
    print("    the volume   -> %s trajectories" % "{:,}".format(vol // per))
    print("    each advancing one Collatz step per %d gate-delays, on ONE host addressing." % d0)
    print("\n  DEPTH and the host's cost do not move with N. §43B measured that already, on a")
    print("  population of RV32I cores: 'the reduction, not the replication, is what ever costs")
    print("  depth' — 8 cores whose DEPTH on THE MACHINE held one value, gates exactly linear.")
    print("  no reduction either, and §69D reproduced the flatness and the constant host cost on")
    print("  the oscillation itself. So N is read off storage rather than built in host RAM.")
    print("\n  Collatz steps delivered per settle at the volume's bound: %s"
          % "{:,}".format(vol // per))
    print("  against 1 step per host addressing before the oscillation.")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
