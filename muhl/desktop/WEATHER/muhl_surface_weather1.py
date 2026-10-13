#!/usr/bin/env python3
# Surface dests a WEATHER1 file already published. Ones, not hex. Die.
# No inject. No 337. No titan.

import os
import struct
import sys

if not sys.argv[1:]:
    print("NEED_BRYCE — name a WEATHER1 .mno")
    raise SystemExit(1)
PKG = os.path.normpath(sys.argv[1])
NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")

with open(PKG, "rb") as f:
    raw = f.read(96)
    assert raw[:8] == b"WEATHER1", "magic %r" % (raw[:8],)
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
    depth = struct.unpack_from("<I", raw, 24)[0]
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0, clock = struct.unpack_from("<QQ", raw, 76)
    span = cells + cells + 2
    f.seek(0)
    b0 = f.read(1)
    # mouths
    f.seek(clock)
    clock_b = f.read(1)[0]
    f.seek(ring0)
    ring0_b = f.read(1)[0]
    carry0 = ring0 + 2 * cells
    pub0 = carry0 + 1
    f.seek(carry0)
    carry_b = f.read(1)[0]
    f.seek(pub0)
    pub_b = f.read(1)[0]
    rows = []
    for ri, name in enumerate(NAMES):
        fwd = ring0 + ri * span
        rev = fwd + cells
        carry = fwd + 2 * cells
        pub = carry + 1
        f.seek(fwd)
        fb = f.read(1)[0]
        f.seek(rev)
        rb = f.read(1)[0]
        f.seek(carry)
        cb = f.read(1)[0]
        f.seek(pub)
        pb = f.read(1)[0]
        rows.append((name, fwd, fb, rev, rb, carry, cb, pub, pb))

cpt = (float(n_gate) / depth) if depth else 0.0
print("SURFACE", PKG)
print("  n_in", n_in, "n_wire", n_wire, "n_gate", n_gate, "n_out", n_out)
print("  DEPTH", depth, "cpt", "%.3f" % cpt)
print("  ring0@%d=%d clock@%d=%d carry@%d=%d pub@%d=%d" % (
    ring0, ring0_b, clock, clock_b, carry0, carry_b, pub0, pub_b))
for name, fwd, fb, rev, rb, carry, cb, pub, pb in rows:
    print("  %s fwd@%d=%d rev@%d=%d carry@%d=%d pub@%d=%d" % (
        name, fwd, fb, rev, rb, carry, cb, pub, pb))
print("DIE")
