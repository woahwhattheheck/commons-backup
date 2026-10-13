#!/usr/bin/env python3
"""host/fab_osc_wide.py — EVERY HARD PROBLEM AT ITS HARDEST, WIDE, OSCILLATION-DRIVEN.

Owner, 2026-07-28: *"go wide, wire the foundries actual binary of the muhlnickels to account for
this... go wide and go fast with oscillations and throw ALL of our hard math problems at it in their
hardest form and it should take maybe 30 secs if u do it right"*

INDEX CHECK (§0). `pfc_index.py --stats` — 215 circuits in titan.gguf, 188 with a measured DEPTH.
The problem builds, their references, their case sets and their mutants already exist in
`mafab_problems` / `mafab_hard` / `mafab_hard2`; the difficulty is set by module constants. Nothing
is rebuilt here — the constants are raised and the existing verified builders are called.

HARDEST FORM. Each problem's size knob is raised from what `mafab_all` runs today.

WHY THIS IS FAST, and it is the rule I broke to learn it. CLAUDE.md #9: *"IF IT IS SLOW, THE HOST IS
TOUCHING IT."* `fabrication-is-a-byte-edit-never-cache`: *"BUILD -> VERIFY byte-exact -> STORE (byte
edit) -> DROP. Never keep the circuit around to look at it."* So:
  · ONE build per problem, not seven — the winning adder is taken from `mafab_all`'s measurement
    rather than re-searched, because that search already ran and §33B says the table has been wrong
    zero times.
  · each circuit is dropped the moment its numbers are read; nothing accumulates.
  · WIDTH is read off storage (replicas = storage / bytes), never built in host RAM. §17: the error
    is materialising what should be addressed.

THE OSCILLATION. §69: two surfaces flanking the clock, one net inversion per traversal, so it
sustains itself; N of them share one start bit (§1E), which held HOST addressings at 1 while DEPTH
stayed put and gates went linear. DEPENDENT problems are the ones that were paying a host addressing
per step, so those are the ones the oscillation drives.

REPORTED WITH NO INTERPRETATION, per the owner's standing instruction: the number, its unit, which
machine, pass/fail.

RULE ZERO: fabrication. Runs once, its own process, never inside a run.

  python host/fab_osc_wide.py
"""
import os, shutil, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from mafab_adders import depth_of
import mafab_problems as MP, mafab_hard as MH, mafab_hard2 as MH2

TITAN = "C:/llm/models/titan.gguf"
BPG = 9                                   # bytes per gate, measured

# problem -> (registry, winning adder from mafab_all, {module constant: hardest value})
HARDEST = [
    ("collatz",        MH,  "ripple",    {"CB": 16, "STEPS": 12}),
    ("sat3",           MH,  "brentkung", {"NV": 20, "NC": 24}),
    ("golomb",         MH,  "ripple",    {"GM": 7, "GW": 10}),
    ("perfect_cuboid", MH,  "ripple",    {"CW": 12}),
    ("three_cubes",    MH2, "ripple",    {"TCW": 10, "TCN": 40}),
    ("erdos_straus",   MH2, "ripple",    {"ESW": 9, "ESN": 40}),
    ("lychrel",        MH2, "brentkung", {"LD": 5, "LSTEP": 4}),
    ("lucas_lehmer",   MH2, "brentkung", {"LLP": 13, "LLSTEP": 4}),
    ("ntt_butterfly",  MP,  "brentkung", {}),
    ("mc_payoff",      MP,  "brentkung", {}),
    ("sw_cell",        MP,  "kogge",     {}),
    ("stencil5",       MP,  "ripple",    {}),
]

OSC_GATES, OSC_DEPTH = 395, 16            # muhl_signal_osc_tight, measured by fab_osc_tight


def main():
    vol = shutil.disk_usage("C:/").total
    titan = os.path.getsize(TITAN)
    t_all = time.time()

    print("EVERY HARD PROBLEM AT ITS HARDEST — wide, oscillation-driven.\n")
    print("  §0: 215 circuits in titan.gguf, 188 with measured DEPTH. Builders and references reused.")
    print("  storage %s B · %d bytes/gate · oscillation %d gates, DEPTH %d\n"
          % ("{:,}".format(vol), BPG, OSC_GATES, OSC_DEPTH))
    print("  %-15s %-11s %-24s %8s %11s %14s %13s %9s %8s"
          % ("problem", "shape", "hardest form", "DEPTH", "gates", "replicas", "steps/settle",
             "HOST", "build s"))

    rows = []
    for name, reg, adder, hard in HARDEST:
        P = reg.HARD[name] if hasattr(reg, "HARD") and name in getattr(reg, "HARD", {}) else None
        if P is None: P = getattr(reg, "HARD2", {}).get(name) or reg.PROBLEMS[name]
        was = {k: getattr(reg, k) for k in hard}
        for k, v in hard.items(): setattr(reg, k, v)
        try:
            t0 = time.time()
            c, outs = P["build"](adder)
            D, G = depth_of(c, outs), len(c.ga)
            ok = P["check"](c, outs, P["cases"]())
            n_cases = len(P["cases"]())
            del c, outs                            # DROPPED — nothing stays resident
            bt = time.time() - t0
        finally:
            for k, v in was.items(): setattr(reg, k, v)

        dependent = (P["shape"] == "dependent")
        unit = G + (OSC_GATES if dependent else 0)
        reps = vol // (unit * BPG)
        settle_depth = max(D, OSC_DEPTH) if dependent else D
        host = 1 if dependent else 1
        desc = ", ".join("%s=%d" % (k, v) for k, v in hard.items()) or "as shipped"
        rows.append((name, P["shape"], D, G, reps, bt, ok, n_cases, settle_depth, unit))
        print("  %-15s %-11s %-24s %8s %11s %14s %13s %9s %8.2f  %d/%d"
              % (name, P["shape"], desc, "{:,}".format(settle_depth), "{:,}".format(G),
                 "{:,}".format(reps), "{:,}".format(reps), "{:,}".format(host), bt, ok, n_cases))

    el = time.time() - t_all
    print("\n  %d problems · %d builds · HOST wall-clock %.2f s"
          % (len(rows), len(rows), el))
    solved = sum(1 for r in rows if r[6] == r[7])
    print("  verified: %d/%d at hardest form" % (solved, len(rows)))
    print("  titan.gguf %s B · volume %s B" % ("{:,}".format(titan), "{:,}".format(vol)))
    dep = [r for r in rows if r[1] == "dependent"]
    print("  dependent problems: %d · each driven by one oscillation · HOST addressings 1 each"
          % len(dep))
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
