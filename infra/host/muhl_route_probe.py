#!/usr/bin/env python3
# host/muhl_route_probe.py
# Surface dests FROM five weather_v2 files (header mouths). Address those
# 1s/0s into axiom_probe.mno inject plane. Fire probe rings. Surface field.
# xorwalk SOURCE is leftover charged — READ only, do not re-OR that file.
# No 337. No titan write. No dc mmap.

import os, struct, sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

PKG = r"C:\Users\lucys\Desktop\WEATHER\axiom_probe.mno"
WEATHER = r"C:\Users\lucys\Desktop\WEATHER"
FILES = (
    "weather_v2.mno",
    "weather_v2_avg4full.mno",
    "weather_v2_xorwalk.mno",
    "weather_v2_field.mno",
    "weather_v2_coupled.mno",
)


def weather_dests(path):
    with open(path, "rb") as f:
        raw = f.read(96)
    assert raw[:8] == b"WEATHER1", path
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0, clock = struct.unpack_from("<QQ", raw, 76)
    carry = ring0 + 2 * cells
    pub = carry + 1
    with open(path, "rb") as f:
        def one(addr):
            f.seek(addr)
            return f.read(1)[0] & 1
        return [one(ring0), one(clock), one(carry), one(pub)]


def main():
    bits = []
    print("ROUTE_PROBE")
    for name in FILES:
        path = os.path.join(WEATHER, name)
        d = weather_dests(path)
        bits.extend(d)
        print("  %s ring0/clock/carry/pub %s" % (name, d))
        print("  (xorwalk read-only)" if "xorwalk" in name else "  (source not rewritten)")
    assert len(bits) == 20
    with open(PKG, "r+b") as f:
        raw = f.read(96)
        assert raw[:8] == b"PROBEMN2", raw[:8]
        n_in = struct.unpack_from("<I", raw, 8)[0]
        inj = struct.unpack_from("<Q", raw, 60)[0]
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        assert n_in == 20
        span = cells + cells + 2
        for i, bit in enumerate(bits):
            f.seek(inj + i)
            old = f.read(1)[0]
            new = old | bit
            f.seek(inj + i)
            f.write(bytes((new,)))
            print("  inj@%d %d->%d" % (inj + i, old, new))
        for ri in range(n_rings):
            fwd = ring0 + ri * span
            rev = fwd + cells
            for addr in (fwd, rev):
                f.seek(addr)
                old = f.read(1)[0]
                new = old | 0x01
                f.seek(addr)
                f.write(bytes((new,)))
        f.flush()
        os.fsync(f.fileno())
        field = struct.unpack_from("<Q", raw, 52)[0]
        f.seek(field)
        fld = f.read(n_in)
    print("  field_lsbs", " ".join(str(b & 1) for b in fld))
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
