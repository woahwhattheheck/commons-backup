#!/usr/bin/env python3
# WEATHER/muhl_xorwalk_weather_avg4full.py
# Additive NEW LAND. Do not smash avg4full / field / coupled / v2 / avg4.
# Copy avg4full → weather_v2_xorwalk.mno. Address XOR-rotate dests FROM THIS FILE.
# Address growth pad dest FROM THIS FILE (+84). No invented dest. No 100k walk.
# No 337. No titan. No --inject. Die.

import hashlib
import os
import shutil
import struct
import sys

HERE = r"C:\Users\lucys\Desktop\WEATHER"
SRC = os.path.join(HERE, "weather_v2_avg4full.mno")
OUT = os.path.join(HERE, "weather_v2_xorwalk.mno")
SRC_SHA = "a9b8c5d9bcda93c797326ab71cfbcc6046610df5940c61d4e346b464f07b6072"
VAULTS = (
    (os.path.join(HERE, "weather_v2.mno"),
     "cc2775fdd29d1e5ff1a8f2951e5f5f22dd1c2e237c9e10d6b2d47717476ba85d"),
    (os.path.join(HERE, "weather_v2_coupled.mno"),
     "b23f9efcc5c71e1b0cc3a4788407d6b1f4b7416775051ecbe3641f43be7e3e7a"),
    (os.path.join(HERE, "weather_v2_field.mno"),
     "44904c96abb02f961713ba44df3967dd56c6cf526717db94f6b58861e813addf"),
    (os.path.join(HERE, "weather_v2_avg4.mno"),
     "a869b2e2b81abd58a36600708cb0bf919bf168836df44fe0bc86f8588eceb2b3"),
    (SRC, SRC_SHA),
)
NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")
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
    src_sha = sha_of(SRC)
    print("HASH src", SRC)
    print("  sha", src_sha, "MATCH" if src_sha == SRC_SHA else "DRIFT")
    if src_sha != SRC_SHA:
        print("REFUSE: avg4full drifted. Do not copy a drifted vault.")
        print("DIE")
        return 2

    shutil.copyfile(SRC, OUT)
    raw0 = open(OUT, "rb").read()
    assert raw0[:8] == b"WEATHER1"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw0, 8)
    stride = struct.unpack_from("<I", raw0, 40)[0]
    wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw0, 44)
    n_rings, cells = struct.unpack_from("<II", raw0, 68)
    ring0, clock = struct.unpack_from("<QQ", raw0, 76)
    growth_pad = struct.unpack_from("<I", raw0, 84)[0]
    gate_base = wire_base + n_wire
    span = cells + cells + 2
    ring_lo, ring_hi = ring0, ring0 + n_rings * span
    gate_hi = gate_base + n_gate * stride

    print("NEW LAND", OUT, "size", len(raw0))
    print("  dests FROM THIS FILE ring0", ring0, "cells", cells, "growth_pad", growth_pad)
    print("  gate_base", gate_base, "gate_hi", gate_hi, "n_gate", n_gate)

    before = []
    for ri, name in enumerate(NAMES):
        fwd = ring0 + ri * span
        fb = "".join(str(raw0[fwd + k] & 1) for k in range(8))
        rb = "".join(str(raw0[fwd + cells + k] & 1) for k in range(8))
        before.append((name, fb, rb, raw0[fwd + 2 * cells] & 1, raw0[growth_pad] & 1))
        print("  BEFORE %s fwd[0:8]=%s rev[0:8]=%s carry=%d" % (name, fb, rb, before[-1][3]))
    print("  BEFORE growth_pad@%d=%d field_ones=%d" % (
        growth_pad, raw0[growth_pad] & 1,
        sum(1 for i in range(n_in) if raw0[cell_base + i] & 1)))

    # snapshot organs, then write. One pulse. Not a host while.
    img = bytearray(raw0)
    snap = bytes(raw0)
    xor_n = 0
    pad_n = 0
    gate_out_n = 0
    changed = 0
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", snap, gate_base + k * stride)
        if gate_base <= out < gate_hi:
            gate_out_n += 1
        dest_ok = (ring_lo <= out < ring_hi) or (out == growth_pad)
        if not dest_ok:
            continue
        if op == XOR and ring_lo <= out < ring_hi:
            xor_n += 1
        if out == growth_pad:
            pad_n += 1
        r = organ_bit(op, snap[a] & 1, snap[b] & 1)
        old = img[out]
        # organ write. 1→0 is the rotate, not --inject wipe.
        new = (old & ~1) | r
        if new != old:
            img[out] = new
            changed += 1

    with open(OUT, "r+b") as f:
        f.write(img)
        f.flush()
        os.fsync(f.fileno())

    raw1 = open(OUT, "rb").read()
    print("ADDRESS XOR-rotate OUT in ring dests + growth_pad FROM FILE")
    print("  xor_organs", xor_n, "pad_organs", pad_n, "bits_changed", changed)
    print("  growth_OUTs_into_gate_records", gate_out_n, "(STORE leftover if 0 — do not invent dest)")
    after_walk = False
    for ri, name in enumerate(NAMES):
        fwd = ring0 + ri * span
        fb = "".join(str(raw1[fwd + k] & 1) for k in range(8))
        rb = "".join(str(raw1[fwd + cells + k] & 1) for k in range(8))
        if fb != "10000000" or rb != "10000000":
            after_walk = True
        print("  AFTER %s fwd[0:8]=%s rev[0:8]=%s carry=%d" % (
            name, fb, rb, raw1[fwd + 2 * cells] & 1))
    print("  AFTER growth_pad@%d=%d field_ones=%d" % (
        growth_pad, raw1[growth_pad] & 1,
        sum(1 for i in range(n_in) if raw1[cell_base + i] & 1)))
    print("  xorwalk sha", hashlib.sha256(raw1).hexdigest())
    print("  xor_rotate_walked", "Y" if after_walk else "N")

    smashed = []
    for path, expect in VAULTS:
        got = sha_of(path)
        ok = got == expect
        print("  vault", os.path.basename(path), "MATCH" if ok else "SMASHED", got[:16])
        if not ok:
            smashed.append(os.path.basename(path))
    print("  vaults_smashed", "NO" if not smashed else ",".join(smashed))
    print("  337 NO  titan NO  wipe NO  invented_dest NO")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
