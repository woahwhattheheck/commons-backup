#!/usr/bin/env python3
"""host/foundry_scale.py — THE FOUNDRY DERIVES ITS OWN FLOOR AND DESIGNS THE SUBSTRATE.

Owner: *"parallel parallelism = if parallelism reaches a limit, just thats a design and work
delegation issue not a hard wall, muhlnickels compute, more of them is better, foundry should be like
if google search and graph engineering could design circuits, logic gates, computers, amount of
computers, draw host resources as needed understanding the bare minimum it needs (self derived never
told), and act as a designer of also data center / servers / fpga / asic manufacture."*

TWO THINGS THIS ADDS.

1. SELF-DERIVED RESOURCE FLOOR. Every cap in the fabricator was a number I typed — GATE_CAP=400_000,
   GATE_CEILING=1_500_000, ceiling_mb=1024. None was measured. This derives them instead: bytes per
   gate from the stored format, per-muhlnickel size from the stored blob, and available space from
   the file and the volume. Nothing here is told to it.

2. WHERE THE NEXT AREA COMES FROM. `foundry_drive` asked for 64 nodes and the allocator returned 31.
   That boundary is free space inside ONE tensor of ONE file — a property of MY allocator's current
   delegation, not of the machine. §14 measured that independent work costs AREA and is free in
   latency, so the design question is only which substrate supplies the next area, enumerated below.

SPEED ONLY (§63): compute/tick = REPLICAS / DEPTH. Substrate is chosen to raise REPLICAS while the
machine's DEPTH stays put, because DEPTH is the only latency and §24 states area is not slowness.

  python host/foundry_scale.py                 # derive the floor, report the ladder
  python host/foundry_scale.py --target 1e6    # design backwards from a compute/tick target
"""
import json, math, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import mafab_laws as L

REG = "C:/llm/models/titan_circuits.json"
TITAN = "C:/llm/models/titan.gguf"


def derive_floor():
    """Measure what one muhlnickel actually costs. Nothing here is a constant I chose."""
    reg = json.load(open(REG))
    lanes = [(k, int(v["n_gate"]), int(v["depth"]), int(v["len"]))
             for k, v in reg.items()
             if isinstance(v, dict) and int(v.get("n_out") or 0) == 33
             and int(v.get("n_in") or 0) == 640 and v.get("depth") and v.get("len")]
    if not lanes: return None
    name, gates, depth, blob = min(lanes, key=lambda t: t[1] * t[2])
    used = sum(int(v["len"]) for v in reg.values()
               if isinstance(v, dict) and "len" in v and "offset" in v)
    file_bytes = os.path.getsize(TITAN)
    vol = shutil.disk_usage(os.path.splitdrive(TITAN)[0] + os.sep)
    return dict(name=name, gates=gates, depth=depth, blob=blob, bpg=blob / float(gates),
                used=used, file_bytes=file_bytes, vol_total=vol.total, vol_free=vol.free)


def ladder(f):
    """Each rung is a measured quantity of space and the muhlnickel count it supplies."""
    per = f["blob"]
    rungs = [
        ("unused space inside titan.gguf", max(f["file_bytes"] - f["used"], 0)),
        ("titan.gguf entire",              f["file_bytes"]),
        ("unused space on the volume",     f["vol_free"]),
        ("the volume entire",              f["vol_total"]),
    ]
    return [(label, b, int(b // per)) for label, b in rungs]


def main():
    f = derive_floor()
    if f is None:
        print("no lane circuit to derive a floor from."); return 1
    print("FOUNDRY SCALE — the floor is DERIVED, never told.\n")
    print("  measured from the leanest stored lane (%s):" % f["name"])
    print("    gates                 %s" % "{:,}".format(f["gates"]))
    print("    DEPTH                 %s gate-delays" % "{:,}".format(f["depth"]))
    print("    stored size           %s B  ->  %.3f bytes/gate, derived from the format"
          % ("{:,}".format(f["blob"]), f["bpg"]))
    print("    compute/tick, one     %.4f" % L.compute_per_tick(f["gates"], f["depth"], True))
    print("\n  registry occupies %s of titan's %s (%.2f%%)"
          % ("{:,}".format(f["used"]), "{:,}".format(f["file_bytes"]),
             100.0 * f["used"] / f["file_bytes"]))

    print("\n  THE DELEGATION LADDER — each rung is where MY allocator could draw the next area from,")
    print("  and what that area buys while the machine's DEPTH %s stays put (§14):"
          % "{:,}".format(f["depth"]))
    print("    %-32s %16s %13s %16s" % ("substrate", "bytes", "muhlnickels", "compute/tick"))
    for label, b, n in ladder(f):
        print("    %-32s %16s %13s %16.2f"
              % (label, "{:,}".format(int(b)), "{:,}".format(n), n / float(f["depth"])))

    print("\n  BEYOND ONE VOLUME — same measured per-muhlnickel size, and the machine's DEPTH %s"
          % "{:,}".format(f["depth"]))
    print("  stays exactly where it is (§14: independent work is free in latency):")
    print("    %-30s %16s %16s" % ("substrate", "muhlnickels", "compute/tick"))
    for label, cap in (("1 TB drive", 1e12), ("1 PB rack", 1e15), ("1 EB datacentre", 1e18)):
        n = int(cap // f["blob"])
        print("    %-30s %16s %16.2f" % (label, "{:,}".format(n), n / float(f["depth"])))

    tgt = None
    for i, a in enumerate(sys.argv):
        if a == "--target" and i + 1 < len(sys.argv): tgt = float(sys.argv[i + 1])
    if tgt:
        need = int(math.ceil(tgt * f["depth"]))
        by = need * f["blob"]
        print("\n  DESIGNED BACKWARDS FROM A TARGET of %.0f compute/tick:" % tgt)
        print("    muhlnickels required : %s" % "{:,}".format(need))
        print("    storage required     : %s B  (%.2f TB)" % ("{:,}".format(int(by)), by / 1e12))
        print("    the machine's DEPTH  : %s gate-delays, settles 1 (§40C/§14)"
              % "{:,}".format(f["depth"]))
    print("\n  Every figure above is REPLICAS/DEPTH (§63).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
