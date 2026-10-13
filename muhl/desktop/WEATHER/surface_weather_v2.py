#!/usr/bin/env python3
# surface_weather_v2.py — bounded READ of weather_v2.mno named mouths. No settle. Die.
# AFTER is whatever the file holds. No host nxt. No for-g.

import struct, os, hashlib

HERE = r"C:\Users\lucys\Desktop\WEATHER"
PKG = os.path.join(HERE, "weather_v2.mno")
BITS = os.path.join(HERE, "SURFACE_V2_BITS.txt")
NAMES = ["NW", "NE", "SW", "SE", "GROWTH", "WITNESS"]

raw = open(PKG, "rb").read()
assert raw[:8] == b"WEATHER1"
n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
depth = struct.unpack_from("<I", raw, 24)[0]
W, H, CELL_BITS, STRIDE = struct.unpack_from("<IIII", raw, 28)
wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw, 44)
n_rings, cells = struct.unpack_from("<II", raw, 68)
ring0, clock = struct.unpack_from("<QQ", raw, 76)
span = cells + cells + 2

def bits8(off):
    return "".join(str(raw[off + b] & 1) for b in range(8))

doc = []
doc.append("WEATHER v2 SURFACE — 1s/0s FROM THE FILE (no host settle)")
doc.append("sha256 " + hashlib.sha256(raw).hexdigest())
doc.append("size %d  +8 n_in=%d n_wire=%d n_gate=%d n_out=%d  depth %d" % (
    len(raw), n_in, n_wire, n_gate, n_out, depth))
doc.append("cell_base=%d next_base=%d ring0=%d clock=%d" % (cell_base, next_base, ring0, clock))
doc.append("")
doc.append("== RINGS (file bytes) ==")
for ri, name in enumerate(NAMES):
    fwd = ring0 + ri * span
    rev = fwd + cells
    carry = fwd + 2 * cells
    pub = carry + 1
    fb = "".join(str(raw[fwd + k] & 1) for k in range(min(8, cells)))
    rb = "".join(str(raw[rev + k] & 1) for k in range(min(8, cells)))
    doc.append("%s fwd0@%d=%d rev0@%d=%d carry@%d=%d pub@%d=%d  fwd[0:8]=%s rev[0:8]=%s" % (
        name, fwd, raw[fwd] & 1, rev, raw[rev] & 1, carry, raw[carry] & 1, pub, raw[pub] & 1, fb, rb))
doc.append("clock_bank " + "".join(str(raw[clock + i] & 1) for i in range(n_rings)))
doc.append("")
doc.append("== FIELD 16x16x8 LSB first (file cell plane) ==")
for r in range(H):
    row = []
    for c in range(W):
        off = cell_base + (r * W + c) * CELL_BITS
        row.append(bits8(off))
    doc.append(" ".join(row))
doc.append("")
doc.append("== NEXT bank (file, not a host buffer) ==")
for r in range(H):
    row = []
    for c in range(W):
        off = next_base + (r * W + c) * CELL_BITS
        row.append(bits8(off))
    doc.append(" ".join(row))

KITE = ["0110", "1111", "0110", "0010"]
kite = []
for i, row in enumerate(KITE):
    for j, ch in enumerate(row):
        r, c = 6 + i, 6 + j
        off = cell_base + (r * W + c) * CELL_BITS
        bits = bits8(off)
        kite.append("r%dc%d %s" % (r, c, bits))

open(BITS, "w").write("\n".join(doc))
print("\n".join(doc[: 8 + n_rings + 4]))
print("...")
print("kite cells:", " ".join(kite))
print("field_ones", sum(1 for i in range(n_in) if raw[cell_base + i] & 1))
print("full", BITS)
print("button dies")
