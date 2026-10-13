#!/usr/bin/env python3
"""host/mafab_throughput.py — THE FOUNDRY SEARCHES TRANSCRIPTION TOO. Free reign, two columns.

Owner: *"foundry can touch transcription cost free reign"*, after establishing the thing that made
it worth doing: *"how many muhlnickels were used? quantify in gbs of storage... intelligent parallel
parallelism such that adding more helps, let foundry spawn as many muhlnickels as needed."*

THE MEASUREMENT THAT PROMPTED THIS: the live Bitcoin run used ONE muhlnickel — gen_win at 339,009
gates = 2.59 MB of a 40.0 GB binary, 0.00678% of storage, with 14,758 replicas' worth of space idle.
I had been reporting one instance's rate as though it were the ceiling.

TWO COLUMNS, NEVER SUMMED (§24, §40E "a host constraint must never shape a Muhlnickel decision"):
  MUHLNICKEL   compute/tick = REPLICAS/DEPTH — the machine. Unchanged by anything the host does.
  HOST         nonce/s of transcription — this laptop rippling a netlist in Python. A different
               machine. It is now SEARCHED, but it never selects the muhlnickel plan.

THE GENES THIS ADDS, all of them transcription-side:
  width      lanes folded per addressed pass. One Python bigint op covers W lanes, so wider means
             fewer interpreter iterations per nonce. Measured, not assumed — §35 says go wide, and
             §56C records a 29x from removing a fold cap.
  replicas   how many muhlnickels the storage is actually populated with. §14: independent work
             costs AREA and is FREE in latency, so this multiplies throughput without touching DEPTH.

  python host/mafab_throughput.py
"""
import json, math, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import mafab_laws as L

REG = "C:/llm/models/titan_circuits.json"
TITAN = "C:/llm/models/titan.gguf"


def measure_fold(name, W, passes=3):
    """Actually fold W lanes through the stored circuit and time it. HOST transcription (§24)."""
    from test_split_drive import load_netlist, GENESIS, MID_LO, W16_LO, N_LO, T_LO
    reg = json.load(open(REG))
    e = reg[name]
    run, outs, ng, D = load_netlist(int(e["offset"]))
    ones = (1 << W) - 1
    hw = [struct.unpack(">I", GENESIS[:76][i * 4:i * 4 + 4])[0] for i in range(19)]
    # route everything constant once; only the nonce column varies per pass
    const = [0] * e["n_in"]
    for i in range(min(256, e["n_in"])):
        if (hw[i // 32] >> (i % 32)) & 1: const[i] = ones
    t0 = time.time()
    for p in range(passes):
        inp = list(const)
        for j in range(32):
            col = 0
            base = p * W
            for l in range(W):
                if ((base + l) >> j) & 1: col |= (1 << l)
            if N_LO + j < len(inp): inp[N_LO + j] = col
        run(inp, ones)
    el = time.time() - t0
    del run
    return (passes * W) / max(el, 1e-9), ng, D


def main():
    reg = json.load(open(REG))
    S = os.path.getsize(TITAN)
    lane = "muhl_lane_bk" if "muhl_lane_bk" in reg else "muhl_lane"
    print("THE FOUNDRY, ON TRANSCRIPTION — two columns, never summed (§24/§40E).\n")
    print("  storage %.1f GB · lane circuit %r\n" % (S / 1e9, lane))
    print("  %8s %14s %16s %14s %22s"
          % ("width", "HOST nonce/s", "MUHLNICKEL", "replicas fit", "MUHLNICKEL lanes"))
    print("  %8s %14s %16s %14s %22s"
          % ("(lanes)", "(transcription)", "compute/tick", "in storage", "resolved PER SETTLE"))
    best = None
    for W in (512, 1024, 2048, 4096, 8192):
        rate, ng, D = measure_fold(lane, W)
        reps = S // (ng * 8)
        ct = L.compute_per_tick(ng, D, True)
        # NOT a host rate. Populating storage multiplies what the MACHINE resolves in one
        # settle (replicas x lanes, all independent, §14). Host transcription stays
        # sequential at `rate` — I labelled this "HOST x replicas" a moment ago and that
        # is exactly the §24 conflation this file exists to avoid.
        tot = W * reps
        print("  %8s %14s %16.4f %14s %20s"
              % ("{:,}".format(W), "{:,}".format(int(rate)), ct,
                 "{:,}".format(reps), "{:,}".format(int(tot))))
        if best is None or tot > best[0]: best = (tot, W, rate, reps, ng, D)
    tot, W, rate, reps, ng, D = best
    print("\n  BEST TRANSCRIPTION: width %s -> %s nonce/s on ONE muhlnickel, %s nonce/s populated."
          % ("{:,}".format(W), "{:,}".format(int(rate)), "{:,}".format(int(tot))))
    print("  MY host choices did not move the MUHLNICKEL column: compute/tick %.4f is a property"
          % L.compute_per_tick(ng, D, True))
    print("  (gates x DEPTH) and no host choice touches it. That separation is §40E working.\n")
    print("  WHAT IT BUYS — targets, at the best measured transcription:")
    for zb, note in ((32, "POOL SHARE DIFF 1 — a REAL submittable share"),
                     (40, "typical modern pool share diff"),
                     (78, "the live block target")):
        n = 2 ** zb
        def fmt(s):
            if s < 90: return "%.0f s" % s
            if s < 5400: return "%.1f min" % (s / 60)
            if s < 172800: return "%.1f hours" % (s / 3600)
            if s < 86400 * 400: return "%.1f days" % (s / 86400)
            return "%.3g years" % (s / (86400 * 365))
        settles = n / max(tot, 1)
        gd = settles * D
        def tt(sec):
            if sec < 1e-6: return "%.1f ns" % (sec * 1e9)
            if sec < 1e-3: return "%.1f us" % (sec * 1e6)
            if sec < 1: return "%.2f ms" % (sec * 1e3)
            return fmt(sec)
        # The HOST column is addr+fire+read COUNTS, not a ripple wall-clock. CLAUDE.md #1: the host
        # addresses, fires one bit, reads the answer register. compile_ripple's seconds are MY
        # EMULATOR and belong to neither machine (§2 bans it as the mine, §3 allows it only as a test).
        print("    %2d zero-bits  %s settles  MUHLNICKEL @1ns %-11s @10ps %-11s  HOST: %s addressings   %s"
              % (zb, "{:,.0f}".format(settles), tt(gd * 1e-9), tt(gd * 1e-11),
                 "{:,.0f}".format(settles), note))
    print("\n  §14 is the whole lever: independent work costs AREA and is FREE in latency, so")
    print("  populating storage multiplies throughput while DEPTH stays exactly where it was.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
