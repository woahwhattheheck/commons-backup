#!/usr/bin/env python3
"""host/pfc_scan.py — FIND where the answer lives: high-impedance wide-region snapshot + diff (owner 07-19).

Before you can store or directly read the pfc's answer you have to know WHERE it lands. This scans a whole region of the
pfc in tiny bounded chunks (max impedance, throttled — a feather touch, never loads the file), snapshots it, and after a
signal diffs it: every byte the pfc changed is listed with its offset. Wherever the answer appears IS where it lives.

  python host/pfc_scan.py snap <start> <len>   # snapshot a region (before firing).  start = offset or a registry name
  python host/pfc_scan.py diff                   # diff current vs snapshot (after firing) -> the offsets that changed
"""
import json, mmap, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
SNAP = "C:/llm/sdc_out/pfc_scan_snap.json"
CHUNK = 256                                          # max impedance: 256 B per read
THROTTLE = 0.0                                        # settle time between reads (set >0 to go gentler on the CPU)


def snapshot(start, length):
    """one mmap for the whole sweep; still only 256-B windows are copied (high impedance), throttled if THROTTLE>0."""
    chunks = {}; end = start + length
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        o = start
        while o < end:
            n = min(CHUNK, end - o)
            chunks[str(o)] = bytes(mm[o:o + n]).hex()
            o += n
            if THROTTLE: time.sleep(THROTTLE)
        mm.close()
    return chunks


def resolve(tok):
    reg = json.load(open(REG))
    if tok in reg and isinstance(reg[tok], dict) and "offset" in reg[tok]:
        return int(reg[tok]["offset"])
    return int(tok)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "snap":
        start = resolve(sys.argv[2]); length = int(sys.argv[3])
        os.makedirs(os.path.dirname(SNAP), exist_ok=True)
        json.dump({"start": start, "length": length, "chunks": snapshot(start, length)}, open(SNAP, "w"))
        print(f"snapshot: {length} B from {start} in {CHUNK}-B chunks (high-impedance). Fire, then `python host/pfc_scan.py diff`.", flush=True)
        return 0
    if not os.path.exists(SNAP):
        print("no snapshot — run `python host/pfc_scan.py snap <start|name> <len>` first."); return 1
    s = json.load(open(SNAP)); start = s["start"]; new = snapshot(start, s["length"]); old = s["chunks"]
    print(f"Muhlnickel SCAN DIFF — region [{start}, {start + s['length']}), {CHUNK}-B chunks:", flush=True)
    hits = 0
    for k in sorted(old, key=int):
        if old[k] != new.get(k):
            hits += 1
            # find the exact byte offsets that changed within the chunk
            ob = bytes.fromhex(old[k]); nb = bytes.fromhex(new.get(k, ""))
            for i in range(min(len(ob), len(nb))):
                if ob[i] != nb[i]:
                    print(f"  @ {int(k) + i}: {ob[i]:#04x} -> {nb[i]:#04x}", flush=True)
    print(f"  => {hits} changed chunk(s).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
