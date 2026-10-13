#!/usr/bin/env python3
# WEATHER\muhl_fire_weather1.py
# ONE start into a named WEATHER1 .mno. Dest mouths FROM THAT FILE's header.
# new = old | 0x01 on BOTH senses of EACH of the six rings, cell 0.
# fsync. Die. No settle. No host nxt. No 337. No titan. Not --inject WIPE.
#
#   python muhl_fire_weather1.py C:\Users\lucys\Desktop\WEATHER\weather_v2_ks.mno

import os
import struct
import sys

NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask.")
    raise SystemExit(2)

argv = [a for a in sys.argv[1:] if a != "--inject"]
if not argv:
    print("NEED_BRYCE — name a WEATHER1 .mno")
    raise SystemExit(1)
PKG = os.path.normpath(argv[0])
base = os.path.basename(PKG).lower()
if base in ("titan.gguf", "muhlnickel_dc.mno", "dc.mno"):
    print("REFUSE — not titan, not dc")
    raise SystemExit(2)

with open(PKG, "r+b") as f:
    raw = f.read(96)
    assert raw[:8] == b"WEATHER1", "magic %r" % (raw[:8],)
    n_in = struct.unpack_from("<I", raw, 8)[0]
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0 = struct.unpack_from("<Q", raw, 76)[0]
    clock = struct.unpack_from("<Q", raw, 84)[0]
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
print("  n_in", n_in, "n_rings", n_rings, "cells", cells, "ring0", ring0, "clock", clock)
print("  law new=old|0x01 both senses cell 0  (start, not wipe)")
for name, (fa, fo, fn), (ra, ro, rn) in fired:
    print("  %s fwd@%d %d->%d  rev@%d %d->%d" % (name, fa, fo, fn, ra, ro, rn))
print("DIE")
