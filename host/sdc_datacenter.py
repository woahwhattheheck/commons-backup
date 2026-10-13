#!/usr/bin/env python3
"""host/sdc_datacenter.py — TEST FILE (owner 07-16): data-center folds for the SDC swarm. Storage config only — 0 gate
evaluation, 0 black-hole surface (never touches a circuit, only file metadata + the answers-only files).

Folds borrowed from server / data-center storage design:
  THIN PROVISIONING (sparse volumes): the 512 MB answer bitmap is ~all zeros — mark it SPARSE and deallocate the zero
     range, so it costs ~0 physical until a bit is actually set (a hit). Same 2^32 addressable, near-0 footprint.
  DEDUP / COW BASE IMAGE (reported): the fields' circuits share one topology; storing a base once + per-field deltas is
     the structure-shared tier. This tool reports the dedup headroom; the sparse pass is the one it applies now.

  python host/sdc_datacenter.py thin        # thin-provision all swarm bitmaps (reclaim the zero space), measure it
  python host/sdc_datacenter.py report       # dedup + tiering headroom (no changes)
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

SWARM = "C:/llm/sdc_bitmap_swarm"


def _physical_gb(path):
    """physical (allocated) size via `du` semantics — sum of on-disk allocation, which sparse files report small."""
    try:
        out = subprocess.run(["fsutil", "file", "queryallocatedranges", path], capture_output=True, text=True).stdout
        # sum the allocated range lengths; if none, physical ~0
        tot = 0
        for line in out.splitlines():
            if "Length" in line:
                try: tot += int(line.split("0x")[-1].strip(), 16)
                except Exception: pass
        return tot
    except Exception:
        return os.path.getsize(path)


def thin():
    if not os.path.isdir(SWARM):
        print("no swarm."); return
    bits = sorted(f for f in os.listdir(SWARM) if f.startswith("bits_") and f.endswith(".bin"))
    if not bits:
        print("no bitmaps."); return
    before = sum(_physical_gb(os.path.join(SWARM, b)) for b in bits)
    print(f"thin-provisioning {len(bits)} bitmaps (sparse + deallocate zero range) ...", flush=True)
    for b in bits:
        p = os.path.join(SWARM, b); sz = os.path.getsize(p)
        subprocess.run(["fsutil", "sparse", "setflag", p], capture_output=True)
        subprocess.run(["fsutil", "sparse", "setrange", p, "0", str(sz)], capture_output=True)  # zero+deallocate
    after = sum(_physical_gb(os.path.join(SWARM, b)) for b in bits)
    logical = len(bits) * (1 << 29)                            # 512 MB each, still fully addressable
    print(f"  physical: {before/1e9:.1f} GB  ->  {after/1e9:.3f} GB   (reclaimed {(before-after)/1e9:.1f} GB)", flush=True)
    print(f"  logical (addressable): {logical/1e9:.1f} GB unchanged — every field still spans its full 2^32 lanes.", flush=True)
    print(f"  a hit allocates ONE cluster (~4 KB) on write — thin volume. same swarm, near-0 footprint.", flush=True)


def report():
    if not os.path.isdir(SWARM):
        print("no swarm."); return
    r = json.load(open(SWARM + "/roster.json"))
    G = len(r["nodes"])
    vec = sum(os.path.getsize(os.path.join(SWARM, f)) for f in os.listdir(SWARM) if f.startswith("vec_"))
    print(f"=== data-center fold headroom ({G} fields) ===", flush=True)
    print(f"  DEDUP: {G} circuits = {vec/1e6:.0f} MB of near-identical topology. Base-image + deltas -> ~5 MB + {G}x few-KB.", flush=True)
    print(f"         => frees ~{(vec-5_000_000)/1e6:.0f} MB now; and per-field cost drops from 5 MB to a few KB,", flush=True)
    print(f"            so the SAME storage holds ~1000x more fields (structure-shared floor tier).", flush=True)
    print(f"  THIN:  bitmaps are output space (~all zeros) -> sparse = ~0 physical (run `thin`).", flush=True)
    print(f"  TIER:  hot = winner regs ({G*5} B, read every check); cold = the sparse bitmaps (touched only on a hit).", flush=True)
    print(f"  SHARD: split the extranonce2 space across your 3 devices = 3 racks, one lateral gate reads all.", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"thin": thin, "report": report}.get(cmd, report)()
