#!/usr/bin/env python3
"""host/pfc_logic.py — the Muhlnickel LOGIC ANALYZER: capture MANY probe lines at once over time (owner 07-19).

The multimeter reads one point; the scope traces one over time; the logic analyzer captures SEVERAL lines SIMULTANEOUSLY,
so we can see their timing relationship (did pfc_on go high, THEN nonce_reg advance, THEN the safezone fill?). IMPEDANCE
MAXED OUT: each line is the smallest possible bounded read (just its bytes, hard cap 256 B), sampled SLOWLY (4/s), so the
whole capture is a feather touch that cannot stress the CPU or brick the hardware. Never loads the file, never a ripple.

  python host/pfc_logic.py [name1 name2 ...] [seconds]   # default: miner lines (pfc_on,input,nonce_reg,loop_bit) over 3s
"""
import json, mmap, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
IMPEDANCE_CAP = 256                                   # max impedance: never read more than this per line


def read(off, nb):
    nb = max(1, min(int(nb), IMPEDANCE_CAP))
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); b = bytes(mm[off:off + nb]); mm.close()
    return b


def main():
    reg = json.load(open(REG)); args = sys.argv[1:]; secs = 3.0
    if args and args[-1].replace(".", "", 1).isdigit():
        secs = float(args.pop())
    names = args or ["pfc_on", "pfc_exec_input", "nonce_reg", "loop_bit"]
    lines = [(n, int(reg[n]["offset"]), min(int(reg[n].get("len", 4)), 8))
             for n in names if n in reg and isinstance(reg[n], dict) and "offset" in reg[n]]
    if not lines:
        print("no fabricated lines to capture (check the names against the registry)."); return 1
    nsamp = max(4, min(int(secs * 4), 40))            # slow 4/s sampling = max impedance, light on the CPU
    print("Muhlnickel LOGIC ANALYZER — max impedance, slow sample, feather touch (Muhlnickel not loaded / not rippled):", flush=True)
    print("  t(s)  " + " | ".join(f"{n[:12]:>12s}" for n, _, _ in lines), flush=True)
    prev = {}
    for i in range(nsamp):
        row = f"  {i * secs / nsamp:5.2f}"
        for n, off, nb in lines:
            b = read(off, nb)
            v = struct.unpack("<I", (b + b"\x00" * 4)[:4])[0] if nb <= 4 else sum(bin(x).count("1") for x in b)
            ch = "*" if n in prev and prev[n] != b else " "
            row += f" | {v:>11d}{ch}"; prev[n] = b
        print(row, flush=True)
        time.sleep(secs / nsamp)
    print("  (* = line changed since the previous sample)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
