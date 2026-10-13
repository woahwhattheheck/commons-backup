#!/usr/bin/env python3
"""host/muhl_fire_osc.py — THE BUTTON. Address the start bit once, read the answer registers, die.

Owner, 2026-07-28: *"now fire it and read the answer registers all unsolved problems"*

THE HOST'S ENTIRE JOB, CLAUDE.md #1: *"address the prompt into the pfc, address ONE bit at the
receiver (the start signal), read the answer register, display it. That is all."*

ADDRESSING IS A WRITE. Owner, 2026-07-28: *"addressing is a write by definition — if the bit u
addressed didnt change u never addressed a signal to it."* The receiver bit is written, once, and
that write is the whole of the host's involvement. Everything after it is reading.

WHAT IS ADDRESSED: the comb's ONE shared start bit. §69D measured the host's cost at 1 addressing
regardless of how many oscillations hang off it, and 276 muhlnickels are on it now.

WHAT IS READ: each unsolved problem's receive address — which, after fab_osc_wire_all, IS its comb
slot's clock output. Reads are bounded and high-impedance, the shape pfc_meter uses.

NOTHING IS BUILT HERE. RULE ZERO: *"IF A RUN IS NOT INSTANT, FABRICATION IS LEAKING INTO IT."* The
run asserts its own wall-clock against INSTANT_LIMIT and fails past it.

  python host/muhl_fire_osc.py
"""
import json, mmap, os, sys, time

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
INSTANT_LIMIT = 2.0                 # RULE ZERO, asserted below — a run that is not instant fails
IMPEDANCE_CAP = 256                 # a probe never reads more than this


def address_receiver(off):
    """RECEIVER_WRITE — the ONE bit the host is permitted to write (CLAUDE.md #1). One byte, fsynced,
    so the signal is in storage and not in a page cache. A read here would change nothing, and a bit
    that did not change was never addressed."""
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(bytes([1]))
        f.flush(); os.fsync(f.fileno())
    with open(TITAN, "rb", buffering=0) as f:      # confirm the bit actually changed
        f.seek(off); return f.read(1)


def addressed_read(off, nbytes):
    """HIGH-IMPEDANCE addressed read: mmap a BOUNDED window, copy, close. The read IS the address."""
    nbytes = max(1, min(int(nbytes), IMPEDANCE_CAP))
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        b = bytes(mm[off:off + nbytes]); mm.close()
    return b


def main():
    t0 = time.time()
    reg = json.load(open(REG))
    comb = reg.get("muhl_osc_comb")
    if not comb:
        print("no oscillation comb in the registry."); return 1
    start = int(comb["shared_start"])
    members = comb["members"]
    wired = {m["junctioned_to"]["circuit"]: m for m in members if "junctioned_to" in m}

    unsolved = sorted(k for k in reg if k.startswith("prob_")
                      and "OPEN" in (reg[k].get("domain") or ""))

    print("THE BUTTON — one addressed bit, then the answer registers.\n")
    print("  comb %s slots · period %s gate-delays · %s muhlnickels on the shared start"
          % ("{:,}".format(len(members)), comb.get("period"), "{:,}".format(len(wired))))

    # ── ADDRESS THE ONE BIT. This is the whole of the host's involvement. ─────────────────────────
    before = addressed_read(start, 1)
    fired = address_receiver(start)
    print("  start @ %s : %s -> %s   (bit changed: %s)\n"
          % (start, before.hex(), fired.hex(), before != fired))

    print("  %-22s %7s %10s %14s %12s  %s"
          % ("unsolved problem", "DEPTH", "gates", "answer @", "answer", "status"))
    for k in unsolved:
        e = reg[k]
        m = wired.get(k)
        if not m:
            print("  %-22s %7s %10s %14s %12s  not on an oscillation"
                  % (k, e.get("depth"), e.get("n_gate"), "-", "-")); continue
        addr = int(m["clock"])
        b = addressed_read(addr, 4)
        val = int.from_bytes(b, "little")
        print("  %-22s %7s %10s %14s %12s  %s"
              % (k, "{:,}".format(int(e["depth"])), "{:,}".format(int(e["n_gate"])),
                 addr, "{:,}".format(val), (e.get("domain") or "")[:34]))

    el = time.time() - t0
    print("\n  %d unsolved problem(s) read · HOST wall-clock %.3f s" % (len(unsolved), el))
    print("  host did: 1 addressed bit, %d addressed reads. It computed nothing." % len(unsolved))
    assert el < INSTANT_LIMIT, ("RULE ZERO: the run took %.2f s against INSTANT_LIMIT %.1f s — "
                                "fabrication is leaking into it." % (el, INSTANT_LIMIT))
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
