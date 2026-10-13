#!/usr/bin/env python3
# host/muhl_route_probe_pop.py
# Surface dests FROM five weather_v2 files into axiom_probe_pop.mno inj.
# Fire rings. Address stored records (read the answer register). Print pop bits.
# xorwalk SOURCE leftover charged — READ dests only, do not re-OR that file.
# No 337. No titan write. No dc mmap. Does not smash axiom_probe.mno.

import os, struct, sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

PKG = r"C:\Users\lucys\Desktop\WEATHER\axiom_probe_pop.mno"
WEATHER = r"C:\Users\lucys\Desktop\WEATHER"
FILES = (
    "weather_v2.mno",
    "weather_v2_avg4full.mno",
    "weather_v2_xorwalk.mno",
    "weather_v2_field.mno",
    "weather_v2_coupled.mno",
)
NAND, AND, OR, XOR = 0, 1, 2, 3
HDR = 96
STRIDE = 25
POP_BITS = 5


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


def address_stored(img):
    n_wire = struct.unpack_from("<I", img, 12)[0]
    n_gate = struct.unpack_from("<I", img, 16)[0]
    gate_base = HDR + n_wire
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", img, gate_base + k * STRIDE)
        va, vb = img[a] & 1, img[b] & 1
        if op == NAND:
            r = 1 - (va & vb)
        elif op == AND:
            r = va & vb
        elif op == OR:
            r = va | vb
        elif op == XOR:
            r = va ^ vb
        else:
            raise ValueError(op)
        img[out] = r
    return img


def main():
    bits = []
    print("ROUTE_PROBE_POP")
    for name in FILES:
        path = os.path.join(WEATHER, name)
        d = weather_dests(path)
        bits.extend(d)
        print("  %s ring0/clock/carry/pub %s" % (name, d))
        print("  (xorwalk read-only)" if "xorwalk" in name else "  (source not rewritten)")
    assert len(bits) == 20
    with open(PKG, "r+b") as f:
        raw = f.read(96)
        assert raw[:8] == b"PROBEPOP", raw[:8]
        n_in = struct.unpack_from("<I", raw, 8)[0]
        inj = struct.unpack_from("<Q", raw, 60)[0]
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        growth = struct.unpack_from("<I", raw, 92)[0]
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
        f.seek(0)
        img = bytearray(f.read())
    img = address_stored(img)
    with open(PKG, "wb") as f:
        f.write(img)
        f.flush()
        os.fsync(f.fileno())
    pop = [img[growth + 1 + i] & 1 for i in range(POP_BITS)]
    count = sum(pop[i] << i for i in range(POP_BITS))
    field = struct.unpack_from("<Q", raw, 52)[0]
    fld = [img[field + i] & 1 for i in range(20)]
    print("  pop dests", [growth + 1 + i for i in range(POP_BITS)])
    print("  pop bits", pop, "count", count, "sum_inj", sum(bits))
    print("  field_lsbs", " ".join(str(b) for b in fld))
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
