#!/usr/bin/env python3
# surface_weather_bytes.py — address WEATHER .mno files, print 1s/0s, die.
# Host verbs: open + read named offsets + die. Not a settle. Not a ring loop.
# Dest is THIS FILE. No titan. No dc. No 337. No wipe.

import struct, hashlib, os, collections

HERE = r"C:\Users\lucys\Desktop\WEATHER"
NAMES = [
    "weather.mno",
    "weather_v1.mno",
    "weather_v0_badseed.mno",
    "weather_v2.mno",
    "weather_powered.mno",
]
OUT = os.path.join(HERE, "SURFACE_BYTES_NOW.txt")

def bits8(blk):
    return "".join(str(b & 1) for b in blk)

def cell_off(cell_base, r, c):
    return cell_base + (r * 16 + c) * 8

def surface_one(path):
    lines = []
    if not os.path.isfile(path):
        lines.append("ABSENT  %s" % path)
        return lines
    raw = open(path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    lines.append("PRESENT %s" % path)
    lines.append("  size %d  sha256 %s" % (len(raw), sha))
    lines.append("  magic %r" % raw[:8])
    if raw[:8] != b"WEATHER1" or len(raw) < 96:
        lines.append("  REFUSE parse — not WEATHER1 96")
        return lines
    n_gate, n_wire, n_in, n_out, depth = struct.unpack_from("<IIIII", raw, 8)
    W, H, CELL_BITS, STRIDE = struct.unpack_from("<IIII", raw, 28)
    wire_base, cell_base = struct.unpack_from("<QQ", raw, 44)
    pad = raw[60:96]
    lines.append("  header n_gate=%d n_wire=%d n_in=%d n_out=%d depth=%d TICKS" % (
        n_gate, n_wire, n_in, n_out, depth))
    lines.append("  W=%d H=%d CELL_BITS=%d STRIDE=%d wire_base=%d cell_base=%d" % (
        W, H, CELL_BITS, STRIDE, wire_base, cell_base))
    lines.append("  pad60_96 all_zero=%s  first8=%s" % (
        pad == b"\x00" * 36, pad[:8].hex()))
    # HIS inspect-class misparse of this layout
    fake_nin, fake_nwire, fake_ngate, fake_nout = struct.unpack_from("<IIII", raw, 8)
    lines.append("  HIS_<IIII>_at_8 would name n_in=%d n_wire=%d n_gate=%d n_out=%d" % (
        fake_nin, fake_nwire, fake_ngate, fake_nout))
    for mag in (b"NRING2M1", b"MUHLPLYR", b"MUHLPLAY", b"MUHLPKG1", b"LOOMPKG1"):
        lines.append("  find(%s)=%d" % (mag.decode("ascii"), raw.find(mag)))
    # ring_base claim: v1 pad is zero so Q at 60 is 0 — not a ring
    ring_q = struct.unpack_from("<Q", raw, 60)[0]
    lines.append("  Q_at_60 (would-be ring_base if v2 header)=%d" % ring_q)
    # cell plane as it lies
    state = raw[cell_base: cell_base + W * H * CELL_BITS]
    ones = sum(1 for b in state if b & 1)
    lines.append("  field @%d  bytes=%d  ones=%d  not_01=%d" % (
        cell_base, len(state), ones, sum(1 for b in state if b not in (0, 1))))
    KITE_ONES = [(6, 7), (6, 8), (7, 6), (7, 7), (7, 8), (7, 9), (8, 7), (8, 8), (9, 8)]
    kite_ok = True
    for r, c in KITE_ONES:
        b8 = bits8(raw[cell_off(cell_base, r, c): cell_off(cell_base, r, c) + 8])
        if b8 != "11111111":
            kite_ok = False
        lines.append("  kite1 r%dc%d %s" % (r, c, b8))
    mark = raw[cell_off(cell_base, 5, 5): cell_off(cell_base, 5, 5) + 8]
    mbits = bits8(mark)
    mval = 0
    for i, b in enumerate(mark):
        mval |= (b & 1) << i
    lines.append("  cairn r5c5 bits=%s decoded=0x%02X claim_C1=%s" % (mbits, mval, mval == 0xC1))
    lines.append("  kite_nine_ones_in_file=%s" % kite_ok)
    # field 1s/0s as they lie — 16 rows, LSB-first per cell
    lines.append("  FIELD 1s/0s (file order, 16x16x8 LSB first):")
    for r in range(H):
        row = state[r * W * CELL_BITS:(r + 1) * W * CELL_BITS]
        lines.append("    " + " ".join(
            "".join(str(b & 1) for b in row[c * CELL_BITS:(c + 1) * CELL_BITS])
            for c in range(W)))
    # op histogram of stored records — address the gate span, do not settle
    gate_base = 96 + n_wire
    ops = collections.Counter()
    state_writes = 0
    identity = 0
    or_srcsrc = 0
    and_to_state = 0
    state_lo, state_hi = cell_base, cell_base + W * H * CELL_BITS
    writers = collections.Counter()
    if gate_base + n_gate * STRIDE <= len(raw):
        for k in range(n_gate):
            op, a, b, out = struct.unpack_from("<BQQQ", raw, gate_base + k * STRIDE)
            ops[op] += 1
            writers[out] += 1
            if state_lo <= out < state_hi:
                state_writes += 1
                if a == out or b == out:
                    identity += 1
                if a == b and op == 2:
                    or_srcsrc += 1
                if op == 1:
                    and_to_state += 1
        lines.append("  gate_base=%d  OPS %s" % (gate_base, dict(sorted(ops.items()))))
        lines.append("  state_writes=%d  identity_out==a|b=%d  OR(src,src)->state=%d  AND->state=%d" % (
            state_writes, identity, or_srcsrc, and_to_state))
        lines.append("  one_writer=%s  multi=%d" % (
            max(writers.values()) == 1 and len(writers) == n_gate,
            sum(1 for n in writers.values() if n > 1)))
    else:
        lines.append("  gate span past EOF — REFUSE walk")
    lines.append("  RINGS_IN_BYTES = NO  (no ring magic, pad Q=0, 0 AND-writes onto field, 2048 ungated OR identity)")
    return lines

def main():
    doc = []
    doc.append("WEATHER SURFACE — BYTES AS THEY LIE. Host = open + read + die.")
    doc.append("No settle. No host executor as the computer. No titan. No dc. No 337.")
    doc.append("")
    for name in NAMES:
        doc += surface_one(os.path.join(HERE, name))
        doc.append("")
    text = "\n".join(doc)
    open(OUT, "w").write(text)
    print(text)
    print("wrote", OUT)
    print("button dies")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
