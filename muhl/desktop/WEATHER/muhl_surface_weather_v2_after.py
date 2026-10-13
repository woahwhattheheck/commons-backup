#!/usr/bin/env python3
# Bounded READ of weather_v2.mno named mouths AFTER fire. No settle. No host nxt. Die.

import hashlib
import os
import struct

PKG = r"C:\Users\lucys\Desktop\WEATHER\weather_v2.mno"
BITS = r"C:\Users\lucys\Desktop\WEATHER\SURFACE_V2_AFTER.txt"
NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")
NAND, AND, OR, XOR = 0, 1, 2, 3

raw = open(PKG, "rb").read()
assert raw[:8] == b"WEATHER1"
n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
depth = struct.unpack_from("<I", raw, 24)[0]
W, H, CELL_BITS, STRIDE = struct.unpack_from("<IIII", raw, 28)
wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw, 44)
n_rings, cells = struct.unpack_from("<II", raw, 68)
ring0, clock = struct.unpack_from("<QQ", raw, 76)
span = cells + cells + 2
gate_base = wire_base + n_wire
file_sha = hashlib.sha256(raw).hexdigest()
field = raw[cell_base:cell_base + n_in]
field_sha = hashlib.sha256(field).hexdigest()
field_ones = sum(1 for b in field if b & 1)


def bits8(off):
    return "".join(str(raw[off + b] & 1) for b in range(8))


rings = []
doc = []
doc.append("WEATHER v2 SURFACE AFTER FIRE — 1s/0s FROM THE FILE (no host settle)")
doc.append("sha256 " + file_sha)
doc.append("size %d  +8 n_in=%d n_wire=%d n_gate=%d n_out=%d  depth %d" % (
    len(raw), n_in, n_wire, n_gate, n_out, depth))
doc.append("cell_base=%d next_base=%d ring0=%d clock=%d gate_base=%d" % (
    cell_base, next_base, ring0, clock, gate_base))
doc.append("")
doc.append("== RINGS (file bytes) ==")
for ri, name in enumerate(NAMES):
    fwd = ring0 + ri * span
    rev = fwd + cells
    carry = fwd + 2 * cells
    pub = carry + 1
    fb = "".join(str(raw[fwd + k] & 1) for k in range(cells))
    rb = "".join(str(raw[rev + k] & 1) for k in range(cells))
    rec = {
        "name": name, "fwd": fwd, "rev": rev, "carry": carry, "pub": pub,
        "fwd0": raw[fwd] & 1, "rev0": raw[rev] & 1,
        "carry_b": raw[carry] & 1, "pub_b": raw[pub] & 1,
        "fwd32": fb, "rev32": rb,
    }
    rings.append(rec)
    doc.append("%s fwd0@%d=%d rev0@%d=%d carry@%d=%d pub@%d=%d  fwd[0:8]=%s rev[0:8]=%s" % (
        name, fwd, rec["fwd0"], rev, rec["rev0"], carry, rec["carry_b"],
        pub, rec["pub_b"], fb[:8], rb[:8]))
clock_bits = "".join(str(raw[clock + i] & 1) for i in range(n_rings))
doc.append("clock_bank " + clock_bits)
doc.append("")
doc.append("== FIELD 16x16x8 LSB first (file cell plane) ==")
rows = []
for r in range(H):
    row = []
    for c in range(W):
        off = cell_base + (r * W + c) * CELL_BITS
        row.append(bits8(off))
    rows.append(row)
    doc.append(" ".join(row))
doc.append("")
doc.append("field_ones %d / %d  field_sha %s" % (field_ones, n_in, field_sha))
doc.append("field_nonzero_not_01 %d" % sum(1 for b in field if b not in (0, 1)))

KITE = ["0110", "1111", "0110", "0010"]
kite = []
for i, pat in enumerate(KITE):
    for j, ch in enumerate(pat):
        r, c = 6 + i, 6 + j
        off = cell_base + (r * W + c) * CELL_BITS
        kite.append("r%dc%d %s want_%s" % (r, c, bits8(off), "11111111" if ch == "1" else "00000000"))
mark = cell_base + (5 * 16 + 5) * CELL_BITS
mark_bits = bits8(mark)
mark_val = sum((raw[mark + b] & 1) << b for b in range(8))
doc.append("kite " + " | ".join(kite))
doc.append("mark r5c5 %s 0x%02X" % (mark_bits, mark_val))

# ungated crutch: field writer AND(next[i], next[i]) -> field[i]
# gated: field writer AND(mux_temp, mux_temp) -> field[i]; enable AND(fwd,rev)
ops = [0, 0, 0, 0, 0]
ungated_field = 0
gated_field = 0
enable_and = 0
ring_xor = 0
ring_or_pub = 0
field_hi = cell_base + n_in
next_hi = next_base + n_in
ring_lo, ring_hi = ring0, ring0 + n_rings * span
for k in range(n_gate):
    op, a, b, out = struct.unpack_from("<BQQQ", raw, gate_base + k * STRIDE)
    if op <= 4:
        ops[op] += 1
    if cell_base <= out < field_hi:
        if a == b and next_base <= a < next_hi:
            ungated_field += 1
        else:
            gated_field += 1
    if op == AND and ring_lo <= a < ring_hi and ring_lo <= b < ring_hi and a != b:
        enable_and += 1
    if op == XOR and ring_lo <= out < ring_hi:
        ring_xor += 1
    if op == OR and ring_lo <= out < ring_hi:
        ring_or_pub += 1

doc.append("")
doc.append("== STORED OPS (records, not a ripple) ==")
doc.append("NAND %d AND %d OR %d XOR %d other %d" % (ops[0], ops[1], ops[2], ops[3], ops[4]))
doc.append("field_writers gated=%d ungated_next_identity=%d" % (gated_field, ungated_field))
doc.append("enable_AND_both_ring_rails %d  ring_XOR_outs %d  ring_OR_pubs %d" % (
    enable_and, ring_xor, ring_or_pub))
ungated_gone = ungated_field == 0 and gated_field == n_in and enable_and >= 6
doc.append("ungated_crutch_gone %s" % ("y" if ungated_gone else "n"))

open(BITS, "w", encoding="utf-8").write("\n".join(doc) + "\n")
print("\n".join(doc[: 8 + n_rings + 6]))
print("field_ones", field_ones, "field_sha", field_sha)
print("ungated_crutch_gone", "y" if ungated_gone else "n",
      "gated", gated_field, "ungated", ungated_field, "enable_and", enable_and)
print("full", BITS)
print("DIE")
