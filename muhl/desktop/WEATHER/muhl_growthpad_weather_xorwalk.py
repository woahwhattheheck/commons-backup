#!/usr/bin/env python3
# WEATHER/muhl_growthpad_weather_xorwalk.py
# Address growth dest FROM FILE +92 on xorwalk NEW LAND. Die.
# Do not invent dests inside gate-record region. Do not smash vaults.
# No 337. No titan. No --inject.

import hashlib
import os
import struct
import sys

HERE = r"C:\Users\lucys\Desktop\WEATHER"
PKG = os.path.join(HERE, "weather_v2_xorwalk.mno")
AVG4FULL = os.path.join(HERE, "weather_v2_avg4full.mno")
AVG4FULL_SHA = "a9b8c5d9bcda93c797326ab71cfbcc6046610df5940c61d4e346b464f07b6072"
NAND, AND, OR, XOR = 0, 1, 2, 3
OPN = ("NAND", "AND", "OR", "XOR")

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE.")
    raise SystemExit(2)


def organ_bit(op, va, vb):
    if op == NAND:
        return 1 - (va & vb)
    if op == AND:
        return va & vb
    if op == OR:
        return va | vb
    if op == XOR:
        return va ^ vb
    raise SystemExit("bad op %d" % op)


def sha_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    raw0 = open(PKG, "rb").read()
    assert raw0[:8] == b"WEATHER1"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw0, 8)
    stride = struct.unpack_from("<I", raw0, 40)[0]
    wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw0, 44)
    n_rings, cells = struct.unpack_from("<II", raw0, 68)
    ring0, clock = struct.unpack_from("<QQ", raw0, 76)
    growth_base = struct.unpack_from("<I", raw0, 92)[0]
    gate_base = wire_base + n_wire
    gate_hi = gate_base + n_gate * stride
    print("FILE", PKG, "size", len(raw0))
    print("  dests FROM THIS FILE clock@%d growth_base@%d gate_base=%d gate_hi=%d" % (
        clock, growth_base, gate_base, gate_hi))
    print("  BEFORE growth@%d=%d clock0@%d=%d field_ones=%d" % (
        growth_base, raw0[growth_base] & 1, clock, raw0[clock] & 1,
        sum(1 for i in range(n_in) if raw0[cell_base + i] & 1)))

    snap = bytes(raw0)
    img = bytearray(raw0)
    hits = []
    into_gates = 0
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", snap, gate_base + k * stride)
        if gate_base <= out < gate_hi:
            into_gates += 1
        if out != growth_base:
            continue
        r = organ_bit(op, snap[a] & 1, snap[b] & 1)
        old = img[out]
        new = (old & ~1) | r
        img[out] = new
        hits.append((k, OPN[op], a, b, out, snap[a] & 1, snap[b] & 1, r, old & 1, new & 1))

    with open(PKG, "r+b") as f:
        f.write(img)
        f.flush()
        os.fsync(f.fileno())

    raw1 = open(PKG, "rb").read()
    print("ADDRESS organs OUT == growth_base FROM FILE")
    print("  n", len(hits), "growth_OUTs_into_gate_records", into_gates)
    for rec, op, a, b, out, va, vb, r, oldb, newb in hits:
        print("  rec%d %s(%d,%d)->%d in=%d/%d organ=%d %d->%d" % (
            rec, op, a, b, out, va, vb, r, oldb, newb))
    print("  AFTER growth@%d=%d field_ones=%d" % (
        growth_base, raw1[growth_base] & 1,
        sum(1 for i in range(n_in) if raw1[cell_base + i] & 1)))
    print("  xorwalk sha", hashlib.sha256(raw1).hexdigest())
    avg = sha_of(AVG4FULL)
    print("  avg4full", "MATCH" if avg == AVG4FULL_SHA else "SMASHED", avg[:16])
    print("  autofab0_growth_into_gate_records", "Y" if into_gates else "N")
    print("  337 NO  titan NO  wipe NO  invented_dest NO")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
