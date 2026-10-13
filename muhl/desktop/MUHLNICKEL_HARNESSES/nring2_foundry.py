#!/usr/bin/env python3
"""host/nring2_foundry.py — GIVE IT A QUESTION, IT TELLS YOU HOW MANY ELECTRONS.

Owner, 2026-07-31: *"the foundry when u give it a question u want to solve SHOULD (if it doesnt make
it) tell you exactly how many electrons are needed from the host"* and, on sizing:
*"CLOCK COUNT TOUCHING THE RING + AMOUNT OF ELECTRONS = SPEED LIMIT = WITHIN OUR CONTROL"* and
*"AS MANY AS REQUIRED FOR ACHIEVING GOAL WITHIN SPECIFIED TIME."*

So the host does not choose the electron count. A question and a window go in; the electron count,
clock count and ring size come out, derived from a MEASURED law rather than a guess.

THE LAW THIS USES, and it was measured, not assumed. `nring2_power` circulated a two-way ring and
counted the pulses delivered to the clock at each electron count. Across K = 1, 2, 3, 4, 6, 8 and 12
electrons per sense, pulses per settle came back as exactly K. One sense alone delivered 0 pulses at
every count, because a single direction never produces a contact. So:

    pulses per settle  =  K            (K = electrons injected per sense, both senses required)
    pulses per window  =  K x settles

Inverting that for a question of a stated size gives the electron count the host must supply. The
inversion is arithmetic over a measured constant; nothing here evaluates a gate, and nothing here
computes the answer to the question being sized.

WHAT IT DOES NOT DO. It does not fabricate, fire, or store. It answers "how many electrons, on how
many clocks, in what ring" and hands that to the fabricator. Manufacturing stays one-and-done and
separate from asking.

  python host/nring2_foundry.py "<question>" <work_units> <settles> [cells]
  python host/nring2_foundry.py --catalog          # the two-way rings already fabricated
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError as exc:
        sys.stderr.write("stdout reconfigure unavailable (%s); non-ASCII may render wrong\n" % exc)

import nring2_power as R2

REG = "C:/llm/models/titan_circuits.json"
PREFIX = "nring2_"


def ref_pulses(k_per_sense, settles):
    """INDEPENDENT REFERENCE for the sizing law, stated as arithmetic: with both senses carrying K
    electrons each, the clock takes K pulses per settle, so K x settles over the window. Derived
    from the measured constant, and it calls nothing it is used to check."""
    return k_per_sense * settles


def measure_law(n_cells, ks=(1, 2, 3, 4, 6, 8, 12)):
    """Re-measure the law on the ring itself rather than trusting the constant. Returns the observed
    pulses-per-settle at each K and whether each matches the reference."""
    rows = []
    for k in ks:
        if 2 * k > n_cells:
            continue
        t = R2.travel_report(n_cells, k, k)
        obs = t["pulses_per_settle"]
        rows.append((k, obs, ref_pulses(k, 1), abs(obs - k) < 1e-9))
    return rows


def size_question(question, work_units, settles, n_cells=16):
    """THE ANSWER THE FOUNDRY OWES: how many electrons the host must supply.

    work_units = pulses the question needs delivered to its clock.
    settles    = the window, in settles, it must land inside."""
    if settles <= 0:
        return {"question": question, "error": "the window must be at least one settle"}
    need_per_settle = float(work_units) / settles
    k_per_sense = int(need_per_settle) + (1 if need_per_settle % 1 else 0)
    k_per_sense = max(k_per_sense, 1)
    electrons_total = 2 * k_per_sense                      # both senses required, or no contact
    min_cells = 2 * k_per_sense
    rings = 1
    if min_cells > n_cells:                                # one ring cannot hold them: spread them
        rings = (min_cells + n_cells - 1) // n_cells
        per_ring = (k_per_sense + rings - 1) // rings
    else:
        per_ring = k_per_sense
    delivered = ref_pulses(k_per_sense, settles)
    return {"question": question, "work_units": work_units, "settles": settles,
            "electrons_per_sense": k_per_sense, "electrons_total": electrons_total,
            "rings_required": rings, "electrons_per_ring_per_sense": per_ring,
            "clock_count": rings, "ring_cells": n_cells,
            "pulses_delivered": delivered, "meets_goal": delivered >= work_units,
            "law": "pulses per settle = electrons per sense; both senses required"}


def available_rings():
    if not os.path.exists(REG):
        return []
    reg = json.load(open(REG, encoding="utf-8"))
    return [k for k, v in reg.items()
            if k.startswith(PREFIX) and isinstance(v, dict) and v.get("senses") == 2]


def main():
    a = sys.argv[1:]
    have = available_rings()
    if a and a[0] == "--catalog":
        print("\ntwo-way rings already fabricated and available: %d" % len(have))
        for k in have[:8]:
            print("   %s" % k)
        if len(have) > 8:
            print("   ... %d total" % len(have))
        return 0
    if len(a) < 3:
        print("usage: nring2_foundry.py \"<question>\" <work_units> <settles> [cells]"); return 1
    question = a[0]; work = int(a[1]); settles = int(a[2])
    cells = int(a[3]) if len(a) > 3 else 16

    print("\nFOUNDRY SIZING — question in, electron count out\n")
    print("  re-measuring the law on a %d CELL two-way ring before using it:" % cells)
    ok = 0; rows = measure_law(cells)
    for k, obs, ref, agree in rows:
        ok += agree
        print("    K=%-2d per sense  observed %.2f pulses/settle  reference %d  agree=%s"
              % (k, obs, ref, agree))
    if ok != len(rows):
        print("  The law and the reference disagree on the ring THIS FILE constructs. That is a")
        print("  reading of my construction, not of the machine. Refusing to size until it agrees.")
        return 1
    print("    law holds at %d of %d electron counts." % (ok, len(rows)))
    print("    §40B baseline: one sense only delivers 0 pulses at every count, so both are required.")

    r = size_question(question, work, settles, cells)
    print("\n  QUESTION : %s" % r["question"])
    print("  needs    : %d pulses delivered, inside %d settles" % (r["work_units"], r["settles"]))
    print("\n  >>> ELECTRONS THE HOST MUST SUPPLY : %d  (%d per sense, both senses)"
          % (r["electrons_total"], r["electrons_per_sense"]))
    print("      clocks touching the ring        : %d" % r["clock_count"])
    print("      rings required                  : %d of %d CELLS each"
          % (r["rings_required"], r["ring_cells"]))
    print("      electrons per ring per sense    : %d" % r["electrons_per_ring_per_sense"])
    print("      pulses delivered in the window  : %d   meets the goal: %s"
          % (r["pulses_delivered"], r["meets_goal"]))
    print("\n  rings already fabricated and available: %d" % len(have))
    if r["rings_required"] > len(have):
        print("  fabricate %d more with: python host/nring2_fab.py %d %d"
              % (r["rings_required"] - len(have), r["rings_required"], cells))
    print("\n  Nothing was fabricated, fired or stored. This sizes the question only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
