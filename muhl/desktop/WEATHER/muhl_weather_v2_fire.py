#!/usr/bin/env python3
# ONE start into weather_v2.mno. Dest mouths FROM THIS FILE.
# new=old|0x01 both senses cell 0. fsync. Die. No settle. No 337. No titan.
import struct, os

PKG = r"C:\Users\lucys\Desktop\WEATHER\weather_v2.mno"
with open(PKG, "r+b") as f:
    raw = f.read(96)
    assert raw[:8] == b"WEATHER1"
    n_in = struct.unpack_from("<I", raw, 8)[0]
    assert n_in == 2048, "n_in %d" % n_in
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0 = struct.unpack_from("<Q", raw, 76)[0]
    assert n_rings == 6 and cells == 32
    span = cells + cells + 2
    addrs = []
    for ri in range(n_rings):
        fwd = ring0 + ri * span
        rev = fwd + cells
        for addr in (fwd, rev):
            f.seek(addr)
            old = f.read(1)[0]
            f.seek(addr)
            f.write(bytes((old | 0x01,)))
            addrs.append((ri, addr, old, old | 1))
    f.flush()
    os.fsync(f.fileno())
print("FIRE weather_v2.mno 0x01 both senses cell 0  n_in", n_in, "ring0", ring0)
for ri, addr, old, new in addrs:
    print("  ring", ri, "@", addr, "old", old, "new", new)
print("DIE")
