#!/usr/bin/env python3
# host/muhl_fire_nring.py
# Fire both-sense cell 0 on every ring a nring pkg published. new=old|0x01. Die.
# Dest FROM FILE header. Not WEATHER1-only.
#   python host/muhl_fire_nring.py C:\path\to\file.mno

import os, struct, sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask.")
    raise SystemExit(2)
argv = [a for a in sys.argv[1:] if a != "--inject"]
if not argv:
    print("NEED_BRYCE — name a nring .mno")
    raise SystemExit(1)
PKG = os.path.normpath(argv[0])
base = os.path.basename(PKG).lower()
if base in ("titan.gguf", "muhlnickel_dc.mno", "dc.mno"):
    print("REFUSE — not titan, not dc")
    raise SystemExit(2)

with open(PKG, "r+b") as f:
    raw = f.read(96)
    magic = raw[:8]
    n_in = struct.unpack_from("<I", raw, 8)[0]
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0 = struct.unpack_from("<Q", raw, 76)[0]
    clock = struct.unpack_from("<Q", raw, 84)[0]
    span = cells + cells + 2
    fired = []
    for ri in range(n_rings):
        fwd = ring0 + ri * span
        rev = fwd + cells
        pair = []
        for addr in (fwd, rev):
            f.seek(addr)
            old = f.read(1)[0]
            new = old | 0x01
            f.seek(addr)
            f.write(bytes((new,)))
            pair.append((addr, old, new))
        fired.append((ri, pair[0], pair[1]))
    f.flush()
    os.fsync(f.fileno())

print("FIRE", PKG)
print("  magic", magic, "n_in", n_in, "n_rings", n_rings, "cells", cells)
print("  ring0", ring0, "clock", clock)
print("  law new=old|0x01 both senses cell 0")
for ri, (fa, fo, fn), (ra, ro, rn) in fired:
    print("  r%d fwd@%d %d->%d  rev@%d %d->%d" % (ri, fa, fo, fn, ra, ro, rn))
print("DIE")
