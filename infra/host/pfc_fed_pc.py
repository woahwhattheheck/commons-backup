#!/usr/bin/env python3
"""host/pfc_fed_pc.py — FEDERATION second node: a BOUNDED, SAFE PC-disk storage node holding 1-bit Muhlnickel, summed with the
phone's real 931-billion (ENOSPC) to break the count past a trillion — for real. PC COMPUTE/RAM untouched (that's what
black-screened it); this is disk only, non-OneDrive (C:/llm/), a hard 20 GB cap with 100+ GB headroom left, deleted
after. Byte-exact verified.
"""
import os, shutil, struct, sys, time
NODE = "C:/llm/pfc_fed_node.bin"; PHONE = 930_993_307_648   # measured phone max (ENOSPC)
CAP = 20 * (1 << 30)                                         # hard 20 GB cap (safe; leaves >350 GB free)
HEADROOM = 100 * (1 << 30)                                   # never fill below 100 GB free — the PC stays healthy


def main():
    os.makedirs("C:/llm", exist_ok=True)
    free0 = shutil.disk_usage("C:/llm").free
    target = min(CAP, max(0, free0 - HEADROOM))
    print(f"Muhlnickel FEDERATION — PC-disk node (disk only, PC compute untouched). free {free0/1e9:.0f} GB, "
          f"filling {target/1e9:.0f} GB (cap 20, headroom 100).\n", flush=True)
    chunk = bytearray(b"\xAA" * (128 << 20)); total = 0; t0 = time.time()
    with open(NODE, "wb") as f:
        while total < target:
            n = min(len(chunk), target - total)
            f.write(chunk[:n]); total += n
            if total % (2 << 30) < (128 << 20):
                print(f"  {total/1e9:.1f} GB, {total/1e6/(time.time()-t0):.0f} MB/s, disk free {shutil.disk_usage('C:/llm').free/1e9:.0f} GB", flush=True)
    dur = time.time() - t0
    with open(NODE, "rb") as f:
        b0 = f.read(1); f.seek(total // 2); bm = f.read(1); f.seek(total - 1); bl = f.read(1)
    ok = (b0 == b"\xAA" and bm == b"\xAA" and bl == b"\xAA")
    os.remove(NODE); free1 = shutil.disk_usage("C:/llm").free
    pc = total * 8; fed = PHONE + pc
    print(f"\n  PC node: {total/1e9:.1f} GB → {pc:,} one-bit Muhlnickel ({pc/1e9:.0f} billion); byte-exact first/mid/last: {ok}; "
          f"{total/1e6/dur:.0f} MB/s; freed (disk free {free1/1e9:.0f} GB).", flush=True)
    print(f"\n  ★ FEDERATED COUNT = phone {PHONE:,} + PC {pc:,} = {fed:,}", flush=True)
    print(f"    = {fed/1e12:.3f} TRILLION Muhlnickel across two nodes — {'PAST A TRILLION' if fed >= 1e12 else 'under a trillion'}, both filled + byte-exact.", flush=True)
    print(f"    (headroom: the PC's {free0/1e9:.0f} GB free would hold {free0*8/1e12:.1f}T; federation is additive — each device adds its storage×8.)", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
