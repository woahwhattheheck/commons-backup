#!/usr/bin/env python3
# WEATHER\muhl_fire_weather_v2.py
# ONE start into weather_v2.mno. Dest mouths FROM THIS FILE's header.
# new = old | 0x01 on BOTH senses of EACH of the six rings, cell 0.
# fsync. Die. No settle. No host nxt. No 337. No titan. Not --inject WIPE.

import os
import struct
import sys

PKG = r"C:\Users\lucys\Desktop\WEATHER\weather_v2.mno"
NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask.")
    raise SystemExit(2)

with open(PKG, "r+b") as f:
    raw = f.read(96)
    assert raw[:8] == b"WEATHER1", "magic %r" % (raw[:8],)
    n_in = struct.unpack_from("<I", raw, 8)[0]
    assert n_in == 2048, "n_in %d (HIS slot, not Cairn swap)" % n_in
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0 = struct.unpack_from("<Q", raw, 76)[0]
    assert n_rings == 6 and cells == 32, "n_rings=%d cells=%d" % (n_rings, cells)
    span = cells + cells + 2
    fired = []
    for ri, name in enumerate(NAMES):
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
        fired.append((name, pair[0], pair[1]))
    f.flush()
    os.fsync(f.fileno())

print("FIRE", PKG)
print("  n_in", n_in, "n_rings", n_rings, "cells", cells, "ring0", ring0)
print("  law new=old|0x01 both senses cell 0  (start, not wipe)")
for name, (fa, fo, fn), (ra, ro, rn) in fired:
    print("  %s fwd@%d %d->%d  rev@%d %d->%d" % (name, fa, fo, fn, ra, ro, rn))
print("DIE")
