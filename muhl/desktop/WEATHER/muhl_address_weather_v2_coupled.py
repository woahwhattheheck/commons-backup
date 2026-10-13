#!/usr/bin/env python3
# WEATHER/muhl_address_weather_v2_coupled.py
# Address stored <BQQQ> outs of weather_v2_coupled.mno. One pass. Die.
# Published dests FROM THIS FILE. No titan/dc. No 337. No wipe. No host nxt.

import hashlib
import mmap
import os
import struct
import sys

PKG = r"C:\Users\lucys\Desktop\WEATHER\weather_v2_coupled.mno"
NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")
NAND, AND, OR, XOR = 0, 1, 2, 3

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE.")
    raise SystemExit(2)


def main():
    with open(PKG, "r+b") as f:
        mm = mmap.mmap(f.fileno(), 0)
        assert mm[:8] == b"WEATHER1", "magic %r" % (mm[:8],)
        n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", mm, 8)
        assert n_in == 2048, "n_in %d" % n_in
        stride = struct.unpack_from("<I", mm, 40)[0]
        wire_base, cell_base, next_base = struct.unpack_from("<QQQ", mm, 44)
        n_rings, cells = struct.unpack_from("<II", mm, 68)
        ring0, clock = struct.unpack_from("<QQ", mm, 76)
        gate_base = wire_base + n_wire
        span = cells + cells + 2

        before = []
        for ri in range(n_rings):
            fwd = ring0 + ri * span
            carry = fwd + 2 * cells
            pub = carry + 1
            before.append((mm[fwd] & 1, mm[fwd + cells] & 1, mm[carry] & 1, mm[pub] & 1))
        field_ones_before = sum(1 for i in range(n_in) if mm[cell_base + i] & 1)
        next_ones_before = sum(1 for i in range(n_in) if mm[next_base + i] & 1)
        clock_before = "".join(str(mm[clock + i] & 1) for i in range(n_rings))

        for k in range(n_gate):
            op, a, b, out = struct.unpack_from("<BQQQ", mm, gate_base + k * stride)
            va, vb = mm[a] & 1, mm[b] & 1
            if op == NAND:
                r = 1 - (va & vb)
            elif op == AND:
                r = va & vb
            elif op == OR:
                r = va | vb
            elif op == XOR:
                r = va ^ vb
            else:
                raise SystemExit("bad op %d rec %d" % (op, k))
            mm[out] = r

        mm.flush()
        os.fsync(f.fileno())

        print("ADDRESS", PKG)
        print("  n_gate", n_gate, "gate_base", gate_base, "one pass stored outs")
        print("  BEFORE field_ones", field_ones_before, "next_ones", next_ones_before, "clock", clock_before)
        carries = []
        pubs = []
        for ri, name in enumerate(NAMES):
            fwd = ring0 + ri * span
            rev = fwd + cells
            carry = fwd + 2 * cells
            pub = carry + 1
            cb, pb = mm[carry] & 1, mm[pub] & 1
            carries.append(cb)
            pubs.append(pb)
            bf, br, bc, bp = before[ri]
            print("  %s fwd0@%d=%d rev0@%d=%d carry@%d=%d pub@%d=%d  was %d/%d/%d/%d" % (
                name, fwd, mm[fwd] & 1, rev, mm[rev] & 1, carry, cb, pub, pb,
                bf, br, bc, bp))
        clock_bits = "".join(str(mm[clock + i] & 1) for i in range(n_rings))
        field_ones = sum(1 for i in range(n_in) if mm[cell_base + i] & 1)
        next_ones = sum(1 for i in range(n_in) if mm[next_base + i] & 1)
        print("  clock_bank", clock_bits)
        print("  field_ones_after", field_ones, "next_ones_after", next_ones)
        mm.close()

    raw = open(PKG, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    print("  sha_after", sha)
    if field_ones != field_ones_before:
        verdict = "FIELD_MOVED"
    elif all(c == 0 for c in carries) and all(p == 0 for p in pubs):
        verdict = "STILL_RAILS_ONLY"
    else:
        verdict = "MISS"
    print("  VERDICT", verdict)
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
