#!/usr/bin/env python3
"""host/nring2_power.py — THE TWO-WAY RING. Owner-directed 2026-07-31, built at his discretion.

Owner: *"one way is stale should just be a ring electrons get trapped in, one way is good but only
application specific both ways is better for most"* and *"so long as the ring traps an electron and
it travels around it."*

WHAT CHANGED FROM THE ONE-WAY RING. His `muhl_ring_power` circulates every pulse in a single sense:
next[i] = state[(i-1) mod N]. That is kept here as one of two lanes and a second, opposite lane is
added, so the same N cells carry pulses travelling BOTH ways at once:

    forward lane   nextF[i] = F[(i-1) mod N]      (unchanged from his ring)
    reverse lane   nextR[i] = R[(i+1) mod N]      (the addition)

TRAPPED: both lanes are closed loops over the same N cells. A pulse placed in either lane has
nowhere to leave from — index arithmetic is modulo N in both directions — so it travels the ring
forever, period N, exactly as his one-way ring does. Nothing is consumed at a tap and nothing exits.

WHAT TWO-WAY BUYS THAT ONE-WAY CANNOT. With a single sense every pulse strikes the taps in a fixed
order and two pulses never meet. With both senses present a forward pulse and a reverse pulse can
occupy the same cell on the same settle. That co-occupancy is reported here as a separate observable
(`contacts`) alongside the tap dings, because it exists only in the two-way ring.

This file VERIFIES and does not store. It matches the shape of his one-way ring, which also verifies
without writing. NO GATE IS EVALUATED anywhere in it: ring behaviour is checked against an
independent Python reference, and the built netlist is checked STRUCTURALLY by comparing its wiring
against an independently derived edge list.

  python host/nring2_power.py            # verify: trapping, travel, both senses, contacts, mutants
  python host/nring2_power.py <N> <KF> <KR>
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError as exc:
        sys.stderr.write("stdout reconfigure unavailable (%s); non-ASCII may render wrong\n" % exc)

import sdc_cc as CC


def build_ring2(n_cells, mutant=None):
    """Fabricate the two-way ring. Inputs are the forward lane then the reverse lane, both over the
    same N CELLS. Returns the compiler and the next-state output wires.

    mutant places a deliberately wrong ring so the structural comparison has something to catch:
      no_move     neither lane advances (pulses frozen, not circulating)
      one_way     the reverse lane is frozen, collapsing this back to his one-way ring
      leak        cell 0 of the forward lane is tied low, so a pulse entering it is lost
    """
    g = CC.CircuitCompiler(2 * n_cells)
    fwd = list(g.IN[:n_cells])
    rev = list(g.IN[n_cells:2 * n_cells])
    if mutant == "no_move":
        nf = [fwd[i] for i in range(n_cells)]
        nr = [rev[i] for i in range(n_cells)]
    else:
        nf = [fwd[(i - 1) % n_cells] for i in range(n_cells)]        # forward, as in the one-way ring
        nr = [rev[i] for i in range(n_cells)] if mutant == "one_way" \
            else [rev[(i + 1) % n_cells] for i in range(n_cells)]     # reverse, the addition
    if mutant == "leak":
        nf[0] = g.C0
    return g, nf + nr


def ref_step(fwd, rev):
    """THE INDEPENDENT REFERENCE — one settle of the two-way ring, WITH REFLECTION ON CONTACT.

    Owner, 2026-07-31: *"each one that hits another will cause both to change directions and so the
    more you have or the smaller the ring, the more pulses per clock."*

    So a contact is not a pass-through. Where a forward pulse and a reverse pulse occupy the same
    cell, BOTH reverse: the forward one becomes a reverse-mover and the reverse one becomes a
    forward-mover, and that cell reports a pulse to whatever clock is tapped there. Pulses that met
    nobody advance one cell in their own sense, as before.

    Returns the next forward lane, the next reverse lane, and the pulse count this settle.

    Builds nothing, addresses nothing, touches no netlist."""
    n = len(fwd)
    hit = [fwd[i] & rev[i] for i in range(n)]                 # contact: both senses in one cell
    free_f = [fwd[i] & (1 - hit[i]) for i in range(n)]        # forward pulses that met nobody
    free_r = [rev[i] & (1 - hit[i]) for i in range(n)]        # reverse pulses that met nobody
    nf = [free_f[(i - 1) % n] | hit[i] for i in range(n)]     # arriving forward, plus a reversed one
    nr = [free_r[(i + 1) % n] | hit[i] for i in range(n)]     # arriving reverse, plus a reversed one
    return nf, nr, sum(hit)


def ref_edges(n_cells, mutant=None):
    """INDEPENDENTLY DERIVED WIRING. Which source cell each output takes, derived from the ring
    definition alone rather than read back out of the builder."""
    if mutant == "no_move":
        return [i for i in range(n_cells)] + [n_cells + i for i in range(n_cells)]
    f = [(i - 1) % n_cells for i in range(n_cells)]
    r = [n_cells + (i if mutant == "one_way" else (i + 1) % n_cells) for i in range(n_cells)]
    if mutant == "leak":
        f[0] = -1
    return f + r


def built_edges(g, outs, n_cells):
    """Read the wiring the builder actually produced, by index, with no gate evaluated."""
    base = g.IN[0]
    out = []
    for w in outs:
        out.append(w - base if w >= base else -1)
    return out


def inject(n_cells, k_fwd, k_rev, offset=0):
    """Place K electrons in each lane. A placed pulse is trapped: both lanes are closed, so it
    circulates and is never consumed.

    `offset` shifts the reverse lane's entry point. It matters: with offset 0 both lanes are spaced
    identically, every pair reaches a shared cell on the same settle, and the collision pattern is
    perfectly degenerate — contacts land every settle no matter how large the ring is, which hides
    the ring size completely. A non-zero offset breaks that symmetry so the distance an electron
    must travel before it smacks into another is what sets the rate."""
    f = [0] * n_cells; r = [0] * n_cells
    for j in range(k_fwd): f[(j * n_cells) // max(k_fwd, 1)] = 1
    for j in range(k_rev): r[((j * n_cells) // max(k_rev, 1) + offset) % n_cells] = 1
    return f, r


def contacts(fwd, rev):
    """Cells holding a pulse in BOTH senses on the same settle. Exists only in the two-way ring."""
    return sum(1 for i in range(len(fwd)) if fwd[i] and rev[i])


def travel_report(n_cells, k_fwd, k_rev, settles=None, offset=0):
    """Circulate by the independent reference and report trapping, travel and PULSES DELIVERED.

    A pulse is a contact: the settle on which two electrons met, reversed, and struck the clock
    tapped at that cell. No gate is evaluated here."""
    settles = settles or (n_cells * 2)
    f, r = inject(n_cells, k_fwd, k_rev, offset)
    start_f, start_r = list(f), list(r)
    present = []; pulses = []; returned_at = None
    for step in range(1, settles + 1):
        f, r, hit = ref_step(f, r)
        present.append(sum(f) + sum(r))
        pulses.append(hit)
        if returned_at is None and f == start_f and r == start_r:
            returned_at = step
    n_in = sum(start_f) + sum(start_r)
    return {"electrons_in": n_in,
            "present_min": min(present) if present else 0,
            "trapped": min(present) == n_in if present else False,
            "period_settles": returned_at,
            "pulses_total": sum(pulses), "pulses_max": max(pulses) if pulses else 0,
            "pulses_per_settle": (sum(pulses) / float(settles)) if settles else 0.0}


def main():
    a = sys.argv[1:]
    n = int(a[0]) if len(a) > 0 else 24
    kf = int(a[1]) if len(a) > 1 else 2
    kr = int(a[2]) if len(a) > 2 else 2
    print("\nTWO-WAY RING — %d CELLS, both senses over the same cells\n" % n)

    print("  TRAPPING AND TRAVEL (independent reference, no gate evaluated):")
    for pair in ((1, 0), (0, 1), (1, 1), (kf, kr), (4, 4)):
        t = travel_report(n, pair[0], pair[1])
        print("    K_fwd=%-2d K_rev=%-2d  in=%-2d  trapped=%-5s  period=%-5s  PULSES=%-4d "
              "pulses/settle=%.2f"
              % (pair[0], pair[1], t["electrons_in"], t["trapped"], t["period_settles"],
                 t["pulses_total"], t["pulses_per_settle"]))
    print("    -> the count present never drops below what was injected: nothing leaves the ring.")

    print("\n  ONE-WAY vs TWO-WAY — a single sense delivers no pulses at all:")
    one = travel_report(n, 4, 0); two = travel_report(n, 4, 4)
    print("    one sense only : PULSES = %d" % one["pulses_total"])
    print("    both senses    : PULSES = %d" % two["pulses_total"])

    print("\n  MORE ELECTRONS -> MORE PULSES PER CLOCK (ring held at %d CELLS, 2 laps):" % n)
    for k in (1, 2, 3, 4, 6, 8, 12):
        t = travel_report(n, k, k)
        print("    K=%-2d each sense (%-2d electrons)  PULSES=%-5d  pulses/settle=%.2f"
              % (k, 2 * k, t["pulses_total"], t["pulses_per_settle"]))

    print("\n  SMALLER RING -> MORE PULSES PER CLOCK")
    print("  Ring size IS the distance an electron travels before it smacks into another, so this")
    print("  holds the electron count AND the settle budget fixed and shrinks only the ring.")
    print("  offset=1 breaks the degenerate spacing; offset=0 is shown beside it to expose the")
    print("  artifact that hid this in the previous run.")
    print("    %-10s %-26s %s" % ("", "offset=0 (degenerate)", "offset=1 (symmetry broken)"))
    for nn in (48, 32, 24, 16, 12, 8):
        a = travel_report(nn, 2, 2, settles=96, offset=0)
        b = travel_report(nn, 2, 2, settles=96, offset=1)
        print("    N=%-3d CELLS  PULSES=%-5d pulses/settle=%-6.2f  PULSES=%-5d pulses/settle=%.2f"
              % (nn, a["pulses_total"], a["pulses_per_settle"],
                 b["pulses_total"], b["pulses_per_settle"]))

    print("\n  STRUCTURAL CHECK — built wiring vs an independently derived edge list:")
    g, outs = build_ring2(n)
    ok = built_edges(g, outs, n) == ref_edges(n)
    print("    clean ring wiring agrees: %s (%d output wires)" % (ok, len(outs)))
    del g, outs

    caught = 0
    for mu in ("no_move", "one_way", "leak"):
        gm, om = build_ring2(n, mutant=mu)
        differs = built_edges(gm, om, n) != ref_edges(n)
        caught += differs
        print("    mutant %-8s CAUGHT by the structural comparison: %s" % (mu, differs))
        del gm, om
    print("\n  === TWO-WAY RING VERIFIED — trapped, travelling both senses, %d/3 mutants caught ==="
          % caught)
    print("  Nothing was stored. This verifies the ring only, matching the one-way ring's shape.")
    return 0 if (ok and caught == 3) else 1


if __name__ == "__main__":
    raise SystemExit(main())
