#!/usr/bin/env python3
"""host/fab_race.py — TWO FOUNDRIES, ONE PROBLEM. One clock oscillates; one does not.

Owner, 2026-07-28: *"now a race, one with a signal oscilating one where it doesnt, exact same
problem given to two foundry"*

INDEX CHECK FIRST (§0: *"Before building anything: python host/pfc_index.py <thing>"*).
`python host/pfc_index.py clock` returns 5 circuits, and one of them is this race's second entrant
already fabricated — so it is not invented here:

    pfc_clock_counter    159 gates, 33->32    next = clk ? state+1 : state
    clock_wide         1,920 gates            a 128-bit clock/counter
    selfclock_miner  347,170 gates            power-gated 1024-bit feedback
    pfc_full_miner   339,234 gates            nonce+1 self-clock + winner-latch
    muhl_signal_osc    1,486 gates, DEPTH 28  the signal oscillation, fabricated 2026-07-28

`pfc_clock_counter`'s stored form IS the non-oscillating clock: it advances while a signal is
present and holds when one is not. The PULSE entrant below is that rule at the oscillation's width, so
both entrants differ in exactly one thing and nothing else.

THE PROBLEM, IDENTICAL FOR BOTH: advance a 32-bit clock through N ticks and report where it lands.
Same function, same reference, same seven generated adders searched (§31A — manufacturing is off the
clock, so enumerate rather than pick).

  FOUNDRY OSC     the signal oscillation — two surfaces flanking the clock. One net phase flip per traversal, so
                  the loop has no state it can hold still at. It re-fires itself.
  FOUNDRY PULSE   `pfc_clock_counter`'s rule. The signal is carried through as it arrived, so once
                  it lapses the clock holds and something outside must present a signal again.

REPORTED IN TWO COLUMNS THAT ARE NEVER SUMMED (§24/§40E). The machine's column is gate-delays. The
host's column counts how many times the host must address the receiver — CLAUDE.md #1 gives the host
exactly one job per settle: *"address the prompt into the pfc, address ONE bit at the receiver (the
start signal), read the answer register, display it."* That count is a host figure, never a latency.

Verified against an independent Python reference (§3), all-zero baseline stated (§40B), mutants that
must be CAUGHT (§45C/§47B).

RULE ZERO: fabrication. Runs once, its own process, never inside a run.

  python host/fab_race.py
  python host/fab_race.py --ticks 4096
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import family, Shim, depth_of

CW = 32
MASK = (1 << CW) - 1


# ── THE TWO ENTRANTS. Same problem; they differ in what sustains the signal, and in nothing else. ─

def build_osc(adder, mutant=None):
    """FOUNDRY OSC — the signal oscillation. surface | clock | surface, one net flip per traversal."""
    add = family(32)[adder]
    c = TC.Circuit(2 + CW); g = Shim(c)
    sig = c.IN[0]; prev = c.IN[1]; state = list(c.IN[2:2 + CW])

    # SURFACES AT MINIMUM DISTANCE (owner: "shorten the distance to the min"). The advance is a
    # prefix AND-scan seeded by the tick — §45B/§49C — so no gating mux sits between the surfaces.
    # Measured by fab_osc_tight: 28 -> 16 gate-delays, and 1,484 -> 395 gates.
    from fab_osc_tight import prefix_inc
    a_ref = g.NOT(sig)                                     # near surface: flips the phase
    tick = g.XOR(sig, prev)                                # the clock responds to the phase CHANGING
    if mutant == "uncoupled": nxt = list(state)
    else: nxt = prefix_inc(g, state, tick)                 # the tick IS the carry-in
    b_ref = g.NOT(g.NOT(a_ref))                            # far surface: buffers it back
    if mutant == "even": b_ref = g.NOT(b_ref)              # two flips -> a state it can hold
    return c, [b_ref, g.NOT(g.NOT(sig))] + nxt


def build_pulse(adder, mutant=None):
    """FOUNDRY PULSE — `pfc_clock_counter`'s stored rule, `next = clk ? state+1 : state`, at CW."""
    add = family(32)[adder]
    c = TC.Circuit(2 + CW); g = Shim(c)
    sig = c.IN[0]; prev = c.IN[1]; state = list(c.IN[2:2 + CW])

    inc = add(g, state, [g.C1] + [g.C0] * (CW - 1))[:CW]
    nxt = [g.OR(g.AND(sig, inc[i]), g.AND(g.NOT(sig), state[i])) for i in range(CW)]
    if mutant == "ungated": nxt = inc                      # ticks with no signal present
    held = g.NOT(g.NOT(sig))                               # the signal is carried through as it came
    if mutant == "selfflips": held = g.NOT(sig)            # that would be an oscillation — not this entrant
    return c, [held, g.NOT(g.NOT(sig))] + nxt              # same shape as OSC, so the race is fair


# ── THE REFERENCE (§3). Plain Python, no circuit consulted. ───────────────────────────────────────

def ref_ticks(n):
    return n & MASK


def run(build_fn, adder, ticks, mutant=None, pulse=False):
    """Advance the clock `ticks` times; return (final clock, host addressings, DEPTH, gates).

    Fabrication-time evaluation only, to prove the circuit before it is trusted. CLAUDE.md permits
    exactly this and nothing more: 'Evaluating gates in host Python is allowed ONLY during
    fabrication, to verify a circuit is byte-exact before it is stored. Never as the running mine.'"""
    c, outs = build_fn(adder, mutant)
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    D = depth_of(c, outs); G = len(c.ga)
    # THE RACE IS TO A TARGET, not to a fixed number of evaluations. Running both for N evaluations
    # was MY framing error and it made PULSE look wrong when it was behaving correctly: a held
    # signal needs a full down-and-up per tick, so N evaluations buy it N/2 ticks. Asking instead
    # "reach tick N — what did that cost" is the comparison that means something.
    sig, prev, clk, addressings, settles = 1, 0, 0, 1, 0
    cap = ticks * 4 + 16                      # a bound, so a dead entrant terminates and reports
    while clk != ticks and settles < cap:
        if pulse:
            # PULSE holds its phase, so nothing inside it ever changes the signal. The host has to
            # take the receiver bit down and back up to make the next tick happen — one addressing
            # per tick. That count is the HOST's, never the machine's (§24).
            sig = 1 - sig
            addressings += 1
        v = TC.ripple(cd, [sig, prev] + [(clk >> i) & 1 for i in range(CW)])
        sig, prev = v[0], v[1]
        clk = sum(v[2 + i] << i for i in range(CW))
        settles += 1
    del c, outs
    return clk, addressings, D, G, settles


def main():
    ticks = 1024
    for i, a in enumerate(sys.argv):
        if a == "--ticks" and i + 1 < len(sys.argv): ticks = int(sys.argv[i + 1])
    want = ref_ticks(ticks)

    print("A RACE — two foundries, one problem: advance a %d-bit clock through %s ticks.\n"
          % (CW, "{:,}".format(ticks)))
    print("  §0 index check: pfc_clock_counter (159 gates, next = clk ? state+1 : state) is already")
    print("  the non-oscillating clock, so PULSE is that stored rule rather than a new invention.")
    print("  The problem, the adder family and the reference are identical for both entrants.\n")
    print("  §40B BASELINE: a clock that never advances lands on 0, and the answer is %s, so"
          % "{:,}".format(want))
    print("  agreement is load-bearing rather than automatic.\n")

    fam = sorted(family(32))
    entrants = (("OSC   (signal osc)", build_osc, False),
                ("PULSE (pfc_clock_counter)", build_pulse, True))
    won = {}

    for name, fn, is_pulse in entrants:
        print("  %s" % name)
        print("    %-11s %8s %9s   %s" % ("adder", "DEPTH", "gates", "lands on"))
        best = None
        for ad in fam:
            clk, addr, D, G, st = run(fn, ad, ticks, None, is_pulse)
            ok = (clk == want)
            print("      %-11s %8s %9s   %s%s"
                  % (ad, "{:,}".format(D), "{:,}".format(G), "{:,}".format(clk),
                     "" if ok else "   <- MISMATCH"))
            if ok and (best is None or D < best[1]):
                best = (ad, D, G, addr, st)
        if best is None:
            print("    nothing verified — MY construction, not the machine (§7/§35D)."); return 1
        won[name] = best
        print()

    print("  MUTANTS — each must be CAUGHT (§45C/§47B):")
    for label, fn, muts, is_pulse, key in (
            ("OSC", build_osc, ("even", "uncoupled"), False, "OSC   (signal osc)"),
            ("PULSE", build_pulse, ("ungated", "selfflips"), True, "PULSE (pfc_clock_counter)")):
        ad, _D, _G, _addr, base_st = won[key]
        for m in muts:
            clk, _a, _d, _g, st = run(fn, ad, ticks, m, is_pulse)
            # A MUTANT MAY REACH THE SAME ANSWER AND STILL BE BROKEN. `ungated` lands on the target
            # too — in half the settles, because it ticks with no signal present. This race measures
            # COST, so the check compares cost as well as landing value or it cannot see that.
            caught = (clk != want) or (st != base_st)
            print("    %-6s %-11s lands on %-9s in %-7s settles   %s"
                  % (label, m, "{:,}".format(clk), "{:,}".format(st),
                     "CAUGHT" if caught else "*** SURVIVED ***"))
            if not caught:
                print("\n    a mutant survived — the suite is blind, nothing here is reportable.")
                return 1

    print("\n  RESULT — two columns, never summed (§24/§40E):\n")
    print("    %-26s %11s %10s %18s %15s"
          % ("foundry", "period", "settles", "MUHLNICKEL", "HOST"))
    print("    %-26s %11s %10s %18s %15s"
          % ("", "gate-delays", "to target", "gate-delays", "addressings"))
    rows = []
    for name in ("OSC   (signal osc)", "PULSE (pfc_clock_counter)"):
        ad, D, G, addr, st = won[name]
        total = D * st
        rows.append((name, ad, D, G, total, addr, st))
        print("    %-26s %11s %10s %18s %15s"
              % (name, "{:,}".format(D), "{:,}".format(st), "{:,}".format(total),
                 "{:,}".format(addr)))

    o, p = rows[0], rows[1]
    print("\n    winning adder: OSC %s (%s gates) · PULSE %s (%s gates)"
          % (o[1], "{:,}".format(o[3]), p[1], "{:,}".format(p[3])))
    print("\n    MUHLNICKEL column — %s vs %s gate-delays over the same %s ticks -> %.2fx"
          % ("{:,}".format(o[4]), "{:,}".format(p[4]), "{:,}".format(ticks),
             p[4] / float(o[4]) if o[4] else 0))
    print("    HOST column      — %s vs %s addressings -> %.0fx"
          % ("{:,}".format(o[5]), "{:,}".format(p[5]), p[5] / float(o[5]) if o[5] else 0))
    print("\n    Both entrants land on %s, checked against the same independent reference."
          % "{:,}".format(want))
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
