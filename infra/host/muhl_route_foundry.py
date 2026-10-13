#!/usr/bin/env python3
# host/muhl_route_foundry.py
# Pack 65-bit prompt FROM published weather dests (20 bits) + zeros.
# Address into foundry_acre.mno inject plane AND titan phys input_addrs
# 93711094958..93711095022 (FROM registry). Fire acre rings. Fire
# muhl_reservoir.input_wire @40022599232 if still 0 (already 1: OR holds).
# new=old|mask. No 10-wide. No dc mmap. No 337. No 78. No --inject WIPE.

import os, struct, sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

TITAN = r"C:\llm\models\titan.gguf"
ACRE = r"C:\Users\lucys\Desktop\MUHL_FOUNDRY\foundry_acre.mno"
WEATHER = r"C:\Users\lucys\Desktop\WEATHER"
FILES = (
    "weather_v2.mno",
    "weather_v2_avg4full.mno",
    "weather_v2_xorwalk.mno",
    "weather_v2_field.mno",
    "weather_v2_coupled.mno",
)
PHYS0 = 93711094958
PHYS_N = 65
RESERVOIR = 40022599232


def weather_dests(path):
    with open(path, "rb") as f:
        raw = f.read(96)
    assert raw[:8] == b"WEATHER1", path
    cells = struct.unpack_from("<I", raw, 72)[0]
    ring0, clock = struct.unpack_from("<QQ", raw, 76)
    carry = ring0 + 2 * cells
    pub = carry + 1
    with open(path, "rb") as f:
        def one(addr):
            f.seek(addr)
            return f.read(1)[0] & 1
        return [one(ring0), one(clock), one(carry), one(pub)]


def or_bit(f, addr, bit):
    f.seek(addr)
    old = f.read(1)[0]
    new = old | (1 if bit else 0)
    f.seek(addr)
    f.write(bytes((new,)))
    return old, new


def main():
    bits = []
    print("ROUTE_FOUNDRY")
    for name in FILES:
        path = os.path.join(WEATHER, name)
        d = weather_dests(path)
        bits.extend(d)
        print("  %s dests %s (xorwalk READ only)" % (name, d))
    bits = bits + [0] * (PHYS_N - len(bits))
    assert len(bits) == PHYS_N
    print("  prompt65", "".join(str(b) for b in bits))

    with open(ACRE, "r+b") as f:
        raw = f.read(96)
        assert raw[:8] == b"FNDRYAC1", raw[:8]
        n_in = struct.unpack_from("<I", raw, 8)[0]
        inj = struct.unpack_from("<Q", raw, 60)[0]
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        assert n_in == 65
        span = cells + cells + 2
        for i, bit in enumerate(bits):
            old, new = or_bit(f, inj + i, bit)
            if i < 24 or bit:
                print("  acre inj@%d %d->%d" % (inj + i, old, new))
        for ri in range(n_rings):
            fwd = ring0 + ri * span
            rev = fwd + cells
            for addr in (fwd, rev):
                or_bit(f, addr, 1)
        f.flush()
        os.fsync(f.fileno())

    with open(TITAN, "r+b") as f:
        for i, bit in enumerate(bits):
            old, new = or_bit(f, PHYS0 + i, bit)
            if i < 8 or bit:
                print("  phys @%d %d->%d" % (PHYS0 + i, old, new))
        old, new = or_bit(f, RESERVOIR, 1)
        print("  reservoir @%d %d->%d" % (RESERVOIR, old, new))
        f.flush()
        os.fsync(f.fileno())
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
