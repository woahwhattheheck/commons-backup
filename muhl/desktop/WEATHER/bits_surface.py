#!/usr/bin/env python3
# bits_surface.py — READ the .mno. Print 1s and 0s as they lie. No invented AFTER.
# AFTER exists only if the file already holds it (after a real fire). This button does not settle.

import struct, os, sys, hashlib

HERE = r"C:\Users\lucys\Desktop\WEATHER"
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "weather_powered.mno")
if not os.path.isfile(PATH):
    PATH = os.path.join(HERE, "weather.mno")

raw = open(PATH, "rb").read()
assert raw[:8] == b"WEATHER1"
first = struct.unpack_from("<I", raw, 8)[0]
HIS = first == 2048

if HIS:
    n_in, n_wire, n_gate, n_out, depth = struct.unpack_from("<IIIII", raw, 8)
    W, H, CELL_BITS, STRIDE = struct.unpack_from("<IIII", raw, 28)
    wire_base, cell_base, ring_base, clock_base, growth_base = struct.unpack_from("<QQQQQ", raw, 44)
    n_rings, cells, senses = struct.unpack_from("<III", raw, 84)
else:
    n_gate, n_wire, n_in, n_out, depth = struct.unpack_from("<IIIII", raw, 8)
    W, H, CELL_BITS, STRIDE = struct.unpack_from("<IIII", raw, 28)
    wire_base, cell_base = struct.unpack_from("<QQ", raw, 44)
    ring_base = clock_base = growth_base = 0
    n_rings = cells = senses = 0

def file_order(bits):
    lines = []
    for r in range(H):
        row = bits[r * W * CELL_BITS:(r + 1) * W * CELL_BITS]
        lines.append(" ".join("".join(str(b & 1) for b in row[c * CELL_BITS:(c + 1) * CELL_BITS]) for c in range(W)))
    return lines

field = list(raw[cell_base: cell_base + W * H * CELL_BITS])
doc = []
doc.append("WEATHER — SURFACE — RAW BITS IN THE FILE (not invented)")
doc.append("path " + PATH)
doc.append("sha256 " + hashlib.sha256(raw).hexdigest())
doc.append("size %d  header %s  n_in=%d n_wire=%d n_gate=%d n_out=%d depth %d TICKS" % (
    len(raw), "HIS_+8_n_in_first" if HIS else "v1_n_gate_first_FOSSIL", n_in, n_wire, n_gate, n_out, depth))
doc.append("cell_base=%d gate_base=%d" % (cell_base, wire_base + n_wire))
if HIS:
    doc.append("ring_base=%d clock_base=%d growth_base=%d n_rings=%d cells=%d senses=%d" % (
        ring_base, clock_base, growth_base, n_rings, cells, senses))
    names = ["Q0", "Q1", "Q2", "Q3", "GROWTH", "WITNESS"]
    doc.append("== RINGS in file ==")
    for ri in range(n_rings):
        stride = 2 * cells + 2
        fwd = "".join(str(raw[ring_base + ri * stride + k] & 1) for k in range(min(32, cells)))
        rev = "".join(str(raw[ring_base + ri * stride + cells + k] & 1) for k in range(min(32, cells)))
        carry = raw[ring_base + ri * stride + 2 * cells] & 1
        pub = raw[ring_base + ri * stride + 2 * cells + 1] & 1
        recv = raw[clock_base + ri] & 1
        doc.append("%s fwd=%s rev=%s carry=%d pub=%d recv=%d  dest_fwd0=%d dest_rev0=%d" % (
            names[ri], fwd, rev, carry, pub, recv,
            ring_base + ri * stride, ring_base + ri * stride + cells))
    doc.append("== WITNESS/CLOCK BANK in file ==")
    doc.append("".join(str(raw[clock_base + i] & 1) for i in range(n_rings)))
    pad = raw[growth_base: growth_base + W * H]
    doc.append("== GROWTH PAD ones=%d / %d ==" % (sum(1 for b in pad if b & 1), len(pad)))
doc.append("== FIELD in file, 16x16x8 LSB first ==")
doc += file_order(field)

KITE = ["0110", "1111", "0110", "0010"]
kite_ones = True
for i, row in enumerate(KITE):
    for j, ch in enumerate(row):
        if ch != "1":
            continue
        r, c = 6 + i, 6 + j
        bits = "".join(str(field[(r * W + c) * CELL_BITS + b] & 1) for b in range(8))
        if bits != "11111111":
            kite_ones = False
doc.append("KITE_NINE_ONES_IN_FILE %s" % kite_ones)

outp = os.path.join(HERE, "SURFACE_POWERED_BITS.txt" if HIS else "SURFACE_TURN_001_BITS.txt")
open(outp, "w").write("\n".join(doc))
print("\n".join(doc[: 12 + (n_rings if HIS else 0)]))
print("...")
print("full render:", outp, "(%d lines)" % len(doc))
print("button dies")
