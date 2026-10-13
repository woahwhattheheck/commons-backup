#!/usr/bin/env python3
# WEATHER/muhl_surface_weather_avg4full.py
# Bounded READ of weather_v2_avg4full.mno named mouths. No settle. No host nxt. Die.
# Dests FROM THIS FILE header. No 337. No titan. No wipe. No smash.

import hashlib
import os
import struct
import sys

PKG = r"C:\Users\lucys\Desktop\WEATHER\weather_v2_avg4full.mno"
CLAIM = "a9b8c5d9bcda93c797326ab71cfbcc6046610df5940c61d4e346b464f07b6072"
BITS = r"C:\Users\lucys\Desktop\WEATHER\SURFACE_AVG4FULL.txt"
NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")
NAND, AND, OR, XOR = 0, 1, 2, 3

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE.")
    raise SystemExit(2)

raw = open(PKG, "rb").read()
assert raw[:8] == b"WEATHER1", "magic %r" % (raw[:8],)
n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
depth = struct.unpack_from("<I", raw, 24)[0]
W, H, CELL_BITS, STRIDE = struct.unpack_from("<IIII", raw, 28)
wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw, 44)
n_rings, cells = struct.unpack_from("<II", raw, 68)
ring0, clock = struct.unpack_from("<QQ", raw, 76)
growth_pad = struct.unpack_from("<I", raw, 84)[0]
gate_base = wire_base + n_wire
span = cells + cells + 2
file_sha = hashlib.sha256(raw).hexdigest()
field = raw[cell_base:cell_base + n_in]
nxt = raw[next_base:next_base + n_in]
field_ones = sum(1 for b in field if b & 1)
next_ones = sum(1 for b in nxt if b & 1)
pad_bit = raw[growth_pad] & 1 if growth_pad < len(raw) else -1


def bits8(off):
    return "".join(str(raw[off + b] & 1) for b in range(8))


doc = []
doc.append("WEATHER AVG4FULL SURFACE — 1s/0s FROM THE FILE (no host settle)")
doc.append("sha256 " + file_sha + (" MATCH" if file_sha == CLAIM else " DRIFT"))
doc.append("size %d  +8 n_in=%d n_wire=%d n_gate=%d n_out=%d  depth %d" % (
    len(raw), n_in, n_wire, n_gate, n_out, depth))
doc.append("cell_base=%d next_base=%d ring0=%d clock=%d gate_base=%d growth_pad=%d" % (
    cell_base, next_base, ring0, clock, gate_base, growth_pad))
doc.append("")
doc.append("== RINGS (file bytes) ==")
ring_lo, ring_hi = ring0, ring0 + n_rings * span
for ri, name in enumerate(NAMES):
    fwd = ring0 + ri * span
    rev = fwd + cells
    carry = fwd + 2 * cells
    pub = carry + 1
    fb = "".join(str(raw[fwd + k] & 1) for k in range(cells))
    rb = "".join(str(raw[rev + k] & 1) for k in range(cells))
    doc.append("%s fwd0@%d=%d rev0@%d=%d carry@%d=%d pub@%d=%d  fwd[0:8]=%s rev[0:8]=%s" % (
        name, fwd, raw[fwd] & 1, rev, raw[rev] & 1, carry, raw[carry] & 1,
        pub, raw[pub] & 1, fb[:8], rb[:8]))
clock_bits = "".join(str(raw[clock + i] & 1) for i in range(n_rings))
doc.append("clock_bank " + clock_bits)
doc.append("growth_pad@%d=%d" % (growth_pad, pad_bit))
doc.append("")
doc.append("field_ones %d / %d" % (field_ones, n_in))
doc.append("next_ones %d / %d" % (next_ones, n_in))

ops = [0, 0, 0, 0, 0]
ring_xor = 0
growth_into_gates = 0
growth_into_pad = 0
gate_hi = gate_base + n_gate * STRIDE
for k in range(n_gate):
    op, a, b, out = struct.unpack_from("<BQQQ", raw, gate_base + k * STRIDE)
    if op <= 4:
        ops[op] += 1
    if op == XOR and ring_lo <= out < ring_hi:
        ring_xor += 1
    if gate_base <= out < gate_hi:
        growth_into_gates += 1
    if out == growth_pad:
        growth_into_pad += 1

doc.append("")
doc.append("== STORED OPS (records, not a ripple) ==")
doc.append("NAND %d AND %d OR %d XOR %d other %d" % (ops[0], ops[1], ops[2], ops[3], ops[4]))
doc.append("ring_XOR_outs %d  growth_OUTs_into_gate_records %d  growth_OUTs_into_pad %d" % (
    ring_xor, growth_into_gates, growth_into_pad))
xor_walked = any(
    "".join(str(raw[ring0 + ri * span + k] & 1) for k in range(8)) != "10000000"
    for ri in range(n_rings)
)
doc.append("xor_rotate_walked %s" % ("Y" if xor_walked else "N"))
doc.append("autofab0_growth_into_gate_records %s" % ("Y" if growth_into_gates else "N"))

open(BITS, "w", encoding="utf-8").write("\n".join(doc) + "\n")
print("\n".join(doc))
print("full", BITS)
print("DIE")
