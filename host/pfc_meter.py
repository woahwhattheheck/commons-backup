#!/usr/bin/env python3
"""host/pfc_meter.py — the Muhlnickel DIGITAL MULTIMETER: a high-IMPEDANCE debug probe (owner 07-19).

The fab tool WRITES the pfc; this tool READS it to DEBUG — like touching a multimeter probe to a node. Normally touching
the running pfc blackholes it (the RIPPLE executor fuses the whole compute into a host wire-vector = OOM). This meter has
IMPEDANCE: at any probe it reads only a tiny BOUNDED window at a named address (mmap, transient, ~0 RAM — 40 GB mmap costs
+0.86 MB, so a few bytes cost nothing), NEVER the whole file, NEVER a ripple. A high-impedance touch draws negligible
"current," so it measures the Muhlnickel WITHOUT loading it / blackholing. That is what lets us actually step through and debug.

  python host/pfc_meter.py mine                      # probe the miner front panel: power, input window, nonce, loop bit
  python host/pfc_meter.py <name|offset> [nbytes]    # probe any register/address (nbytes capped by the impedance)
"""
import json, mmap, struct, sys
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
IMPEDANCE_CAP = 256                                   # impedance MAXED (owner 07-19): a probe never reads more than this
#                                                       (smallest feather touch; cannot stress the CPU or blackhole)


def probe(off, nbytes):
    """HIGH-IMPEDANCE read: mmap a BOUNDED window, copy <= IMPEDANCE_CAP bytes, close. Bounded => ~0 RAM => cannot load or
    blackhole the Muhlnickel. (A ripple/whole-file load would be zero-impedance = the short that blackholes; this never does that.)"""
    nbytes = max(1, min(int(nbytes), IMPEDANCE_CAP))
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        b = bytes(mm[off:off + nbytes]); mm.close()
    return b


def show(label, off, nbytes, interp=None):
    b = probe(off, nbytes)
    ones = sum(bin(x).count("1") for x in b)
    hexs = b[:24].hex() + ("…" if len(b) > 24 else "")
    line = f"  {label:16s} @ {off}  [{len(b)}B]  ones={ones:<4d}  {hexs}"
    if interp:
        try: line += f"   -> {interp(b)}"
        except Exception: pass
    print(line, flush=True)


def main():
    if len(sys.argv) < 2:
        print("usage: python host/pfc_meter.py <mine|name|offset> [nbytes]"); return 1
    reg = json.load(open(REG)); arg = sys.argv[1]

    if arg == "mine":
        print("Muhlnickel MULTIMETER — miner front panel (high-impedance bounded reads; the Muhlnickel is NOT loaded or rippled):", flush=True)
        probes = [("pfc_on(power)", "pfc_on", 1, lambda b: "ON (1)" if b and b[0] else "standby (0)"),
                  ("input window", "pfc_exec_input", 116, lambda b: "block present" if any(b) else "empty"),
                  ("nonce_reg", "nonce_reg", 4, lambda b: "nonce=%d" % struct.unpack("<I", (b + b"\x00" * 4)[:4])[0]),
                  ("loop_bit", "loop_bit", 1, lambda b: str(b[0]) if b else "?")]
        for label, name, nb, interp in probes:
            if name in reg and "offset" in reg[name]:
                show(label, int(reg[name]["offset"]), nb, interp)
            else:
                print(f"  {label:16s} — not fabricated", flush=True)
        return 0

    if arg in reg and isinstance(reg[arg], dict) and "offset" in reg[arg]:
        off = int(reg[arg]["offset"]); nb = int(sys.argv[2]) if len(sys.argv) > 2 else int(reg[arg].get("len", 16))
    else:
        off = int(arg); nb = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    print("Muhlnickel MULTIMETER — high-impedance probe (bounded read, Muhlnickel not loaded):", flush=True)
    show(arg, off, nb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
