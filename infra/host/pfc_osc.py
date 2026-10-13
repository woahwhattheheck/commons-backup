#!/usr/bin/env python3
"""host/pfc_osc.py — the Muhlnickel OSCILLATION PROBE: a high-IMPEDANCE debug instrument.

Built in the likeness of `pfc_meter` (the multimeter) and `pfc_cascade` (the avalanche probe), for
the one thing they cannot reach. `pfc_cascade` refuses any target but `life` and `miner`;
`pfc_meter` needs named addresses, which the signal oscillation did not have until it was wired.

The fab tool WRITES the oscillation; this READS it to DEBUG — like touching a probe to a node while
it runs. It has IMPEDANCE: at any probe it reads only a tiny BOUNDED window at a named address
(mmap, transient, ~0 RAM), NEVER the whole file, NEVER a ripple. A high-impedance touch draws
negligible current, so it measures the oscillation WITHOUT loading it.

WHAT AN OSCILLATION HAS THAT OTHER CIRCUITS DO NOT, and therefore what this reads:

  THE SURFACES     the backward edges. Every other stored netlist is strictly feed-forward
                   (PFC_PROOF_REPORT §2); an oscillation closes each output onto its own input
                   address. This checks each declared edge lands on a real, in-range address.
  THE PHASE        `sig` and `prev`. A correct oscillation has them DIFFERENT — that difference is
                   the tick. Equal phases mean the loop found a state it can hold, which is the
                   `even_inversions` failure, and it is readable in one byte each.
  THE PERIOD       the round-trip DEPTH from the netlist header. §24: this is the machine's latency
                   and it is a structural read — no run, nothing to slow.
  THE CLOCK        the register the pass advances, read as 4 bytes.
  THE RECEIVER     `start`. The host addresses this ONCE. If it is still 0 the oscillation was
                   never fired; that is a fact about the drive, not about the circuit.

  python host/pfc_osc.py                  # every wired oscillation, front panel
  python host/pfc_osc.py <name>           # one of them
  python host/pfc_osc.py <name> --wiring  # only the wiring verdict, per address
"""
import json, mmap, struct, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
IMPEDANCE_CAP = 256          # impedance MAXED (owner 07-19): a probe never reads more than this


def probe(off, nbytes):
    """HIGH-IMPEDANCE read: mmap a BOUNDED window, copy <= IMPEDANCE_CAP bytes, close. Bounded =>
    ~0 RAM => cannot load the oscillation. A whole-file ripple would be zero-impedance; this is not
    that, and never becomes that."""
    nbytes = max(1, min(int(nbytes), IMPEDANCE_CAP))
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        b = bytes(mm[off:off + nbytes]); mm.close()
    return b


def wired_oscillations(reg):
    return [(k, v) for k, v in reg.items()
            if isinstance(v, dict) and v.get("ram") and
            (v.get("signal_oscillation") or "signal_osc" in k)]


def panel(name, e, size):
    ram = e["ram"]
    print("Muhlnickel OSCILLATION PROBE — %s (bounded reads; the oscillation is NOT loaded):" % name)
    print("  netlist        @ %-12s %s gates · DEPTH %s gate-delays"
          % (e.get("offset"), "{:,}".format(e.get("n_gate", 0)), "{:,}".format(e.get("depth", 0))))

    start = probe(ram["start"], 1)
    sig = probe(ram["sig"], 1)
    prev = probe(ram["prev"], 1)
    clk = probe(ram["clock"], 4)
    clkv = struct.unpack("<I", (clk + b"\x00" * 4)[:4])[0]

    print("  start(receiver)@ %-12s %s" % (ram["start"], "FIRED (1)" if start[0] else "unfired (0)"))
    print("  sig  (phase)   @ %-12s %d" % (ram["sig"], sig[0] & 1))
    print("  prev (phase-1) @ %-12s %d" % (ram["prev"], prev[0] & 1))
    print("  clock          @ %-12s %s   [%s]" % (ram["clock"], "{:,}".format(clkv), clk.hex()))

    differ = (sig[0] & 1) != (prev[0] & 1)
    print("  phase differ   : %s" % ("YES — a tick is asserted this pass" if differ
                                     else "NO — sig == prev, so no tick is asserted"))
    print("  period         : %s gate-delays per tick (§24, read off the netlist, no run)"
          % "{:,}".format(e.get("depth", 0)))


def wiring(name, e, size):
    """Per-address verdict. §1E: a junction is a shared location, so 'wired' means the declared
    backward edge lands on a real in-range address, not that a script mentions the name."""
    ram = e["ram"]
    edges = (e.get("wired") or {}).get("backward_edges_bound") or []
    print("  %-22s %-12s %-10s %s" % ("edge", "address", "in range", "closes onto"))
    ok = True
    for ed in edges:
        a = int(ed["addr"])
        good = 0 <= a < size
        ok &= good
        print("  %-22s %-12s %-10s %s"
              % (ed["out"], a, "yes" if good else "NO", ed["closes_onto"]))
    r = int(ram["start"])
    rgood = 0 <= r < size
    ok &= rgood
    print("  %-22s %-12s %-10s %s" % ("start (receiver)", r, "yes" if rgood else "NO", "the host"))
    print("  verdict        : %s" % ("every declared edge lands on a real address"
                                     if ok else "AT LEAST ONE EDGE IS NOT ADDRESSABLE"))
    return ok


def main():
    import os
    size = os.path.getsize(TITAN)
    reg = json.load(open(REG))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only_wiring = "--wiring" in sys.argv

    oscs = wired_oscillations(reg)
    if args:
        oscs = [(k, v) for k, v in oscs if k == args[0]]
        if not oscs:
            e = reg.get(args[0])
            if e is None:
                print("no circuit named %s" % args[0]); return 1
            print("Muhlnickel OSCILLATION PROBE — %s" % args[0])
            print("  NOT WIRED: this circuit has no `ram` addresses, so there is nothing to probe.")
            print("  Fabricate them with: python host/fab_osc_wire.py")
            return 1
    if not oscs:
        print("no wired oscillation in the registry.")
        print("  fabricate one : python host/fab_osc_tight.py")
        print("  give it addresses : python host/fab_osc_wire.py")
        return 1

    for i, (name, e) in enumerate(oscs):
        if i: print()
        if only_wiring:
            print("Muhlnickel OSCILLATION PROBE — %s, wiring only:" % name)
            wiring(name, e, size)
        else:
            panel(name, e, size)
            print("  wiring         :")
            wiring(name, e, size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
