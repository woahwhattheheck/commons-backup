#!/usr/bin/env python3
# surface_weather.py — read the container. Print what is IN the file. Die.
# Does not invent AFTER by host-settling. Fire first if you want AFTER in the .mno.

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
    ring_base = clock_base = growth_base = n_rings = cells = senses = 0

def decode(state):
    g = [[0] * W for _ in range(H)]
    for i in range(W * H):
        v = 0
        for b in range(CELL_BITS):
            v |= (state[i * CELL_BITS + b] & 1) << b
        g[i // W][i % W] = v
    return g

field = list(raw[cell_base: cell_base + W * H * CELL_BITS])
grid = decode(field)

def grid_hex(g):
    return "\n".join(" ".join("%02X" % v for v in row) for row in g)

KITE = ["0110", "1111", "0110", "0010"]
kite_ok = True
for i, row in enumerate(KITE):
    for j, ch in enumerate(row):
        if ch != "1":
            continue
        if grid[6 + i][6 + j] != 0xFF:
            kite_ok = False

doc = []
doc.append("# WEATHER — SURFACE FROM FILE BYTES")
doc.append("path: " + PATH)
doc.append("sha256: " + hashlib.sha256(raw).hexdigest())
doc.append("size %d  HIS_header=%s  n_in=%d n_wire=%d n_gate=%d n_out=%d depth %d TICKS" % (
    len(raw), HIS, n_in, n_wire, n_gate, n_out, depth))
doc.append("cell_base=%d gate_base=%d" % (cell_base, wire_base + n_wire))
if HIS:
    doc.append("ring_base=%d clock_base=%d growth_base=%d rings=%d cells=%d senses=%d" % (
        ring_base, clock_base, growth_base, n_rings, cells, senses))
doc.append("kite nine 1-blocks in file: %s" % kite_ok)
doc.append("")
doc.append("## FIELD in file")
doc.append("```")
doc.append(grid_hex(grid))
doc.append("```")
if HIS:
    names = ["Q0", "Q1", "Q2", "Q3", "GROWTH", "WITNESS"]
    doc.append("## RINGS in file")
    for ri in range(n_rings):
        stride = 2 * cells + 2
        fwd0 = raw[ring_base + ri * stride] & 1
        rev0 = raw[ring_base + ri * stride + cells] & 1
        carry = raw[ring_base + ri * stride + 2 * cells] & 1
        pub = raw[ring_base + ri * stride + 2 * cells + 1] & 1
        recv = raw[clock_base + ri] & 1
        ones_f = sum(raw[ring_base + ri * stride + k] & 1 for k in range(cells))
        ones_r = sum(raw[ring_base + ri * stride + cells + k] & 1 for k in range(cells))
        doc.append("%s fwd0=%d rev0=%d carry=%d pub=%d recv=%d ones_fwd=%d ones_rev=%d dest_fwd0=%d" % (
            names[ri], fwd0, rev0, carry, pub, recv, ones_f, ones_r, ring_base + ri * stride))

outp = os.path.join(HERE, "SURFACE_POWERED.md" if HIS else "SURFACE_TURN_001.md")
open(outp, "w").write("\n".join(doc))
print("SURFACE from file. sha", hashlib.sha256(raw).hexdigest())
print("  HIS", HIS, "cell_base", cell_base, "n_gate", n_gate, "depth", depth)
print("  kite_ones", kite_ok, "nonzero_cells", sum(1 for row in grid for v in row if v))
print("  wrote", outp)
print("button dies")
