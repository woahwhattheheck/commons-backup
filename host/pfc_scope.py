#!/usr/bin/env python3
"""host/pfc_scope.py — the Muhlnickel OSCILLOSCOPE: trace a probe point over TIME (owner 07-19).

The multimeter (pfc_meter.py) reads one value; the oscilloscope traces the WAVEFORM — it samples a bounded probe point
repeatedly over a short window and shows how it changes, so we can watch a signal propagate (e.g. the nonce register
advancing as the self-routing loop runs) or see exactly where it goes flat. Same HIGH IMPEDANCE as the meter: each sample
is a tiny bounded mmap read (~0 RAM), never the whole file, never a ripple — it cannot load or blackhole the pfc.

  python host/pfc_scope.py <name|offset> [seconds] [nbytes]   # trace a register/address over time (default 3s)
"""
import json, mmap, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
CAP = 256                                             # impedance MAXED (owner 07-19): never sample more than this per read


def sample(off, nb):
    nb = max(1, min(int(nb), CAP))
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); b = bytes(mm[off:off + nb]); mm.close()
    return b


def main():
    if len(sys.argv) < 2:
        print("usage: python host/pfc_scope.py <name|offset> [seconds] [nbytes]"); return 1
    reg = json.load(open(REG)); arg = sys.argv[1]
    if arg in reg and isinstance(reg[arg], dict) and "offset" in reg[arg]:
        off = int(reg[arg]["offset"]); nb = int(sys.argv[3]) if len(sys.argv) > 3 else int(reg[arg].get("len", 4))
    else:
        off = int(arg); nb = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    nsamp = max(4, min(int(secs * 4), 40))            # slow 4/s sampling = max impedance, light on the CPU
    print(f"Muhlnickel SCOPE — tracing {arg} @ {off} [{nb}B] for {secs:.1f}s, {nsamp} samples (high-impedance, no load):", flush=True)
    prev = None; changes = 0
    for i in range(nsamp):
        b = sample(off, nb); ones = sum(bin(x).count("1") for x in b)
        val = struct.unpack("<I", (b + b"\x00" * 4)[:4])[0] if nb <= 4 else ones
        mark = ""
        if prev is not None and b != prev:
            changes += 1; mark = "  <-- CHANGED"
        print(f"  t={i * secs / nsamp:5.2f}s  ones={ones:<5d} val={val}{mark}", flush=True)
        prev = b
        time.sleep(secs / nsamp)
    print(f"  => {changes} change(s) over the window ({'signal is moving' if changes else 'FLAT — no motion here'}).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
