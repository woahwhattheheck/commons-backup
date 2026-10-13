#!/usr/bin/env python3
"""host/pfc_sweep.py — WIDE full-region sweep of the Muhlnickel (owner 07-19). Collect data; no conclusions.

Covers the ENTIRE fabricated span (min..max offset of every registry circuit/register) by hashing bounded windows, so a
change ANYWHERE in the pfc is caught cheaply. High impedance (one mmap, windowed reads, hashes not copies). Snapshot,
route/signal externally, then diff -> the exact windows that changed, which you can then fine-scan with pfc_scan.

  python host/pfc_sweep.py snap        # hash-snapshot the whole fabricated region
  python host/pfc_sweep.py diff        # re-hash + report changed windows (offset ranges)
"""
import hashlib, json, mmap, os, sys
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
SNAP = "C:/llm/sdc_out/pfc_sweep_snap.json"; CHUNK = 65536


def region():
    reg = json.load(open(REG))
    spans = [(int(e["offset"]), int(e["offset"]) + int(e.get("len", 1)))
             for e in reg.values() if isinstance(e, dict) and "offset" in e]
    return min(s[0] for s in spans), max(s[1] for s in spans)


def hashes(start, end):
    h = {}
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        o = start
        while o < end:
            n = min(CHUNK, end - o)
            h[str(o)] = hashlib.blake2b(bytes(mm[o:o + n]), digest_size=8).hexdigest()
            o += n
        mm.close()
    return h


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "diff"
    start, end = region()
    if cmd == "snap":
        os.makedirs(os.path.dirname(SNAP), exist_ok=True)
        json.dump({"start": start, "end": end, "h": hashes(start, end)}, open(SNAP, "w"))
        print(f"sweep snapshot: region [{start}, {end}) = {(end - start) / 1e6:.1f} MB in {CHUNK // 1024} KB windows.", flush=True)
        return 0
    if not os.path.exists(SNAP):
        print("no sweep snapshot — run `python host/pfc_sweep.py snap` first."); return 1
    s = json.load(open(SNAP)); new = hashes(s["start"], s["end"]); old = s["h"]; hits = []
    for k in sorted(old, key=int):
        if old[k] != new.get(k):
            hits.append(int(k))
    print(f"Muhlnickel SWEEP DIFF — region [{s['start']}, {s['end']}), {CHUNK // 1024} KB windows:", flush=True)
    for o in hits:
        print(f"  CHANGED window @ [{o}, {o + CHUNK})", flush=True)
    print(f"  => {len(hits)} changed window(s) of {len(old)} total.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
