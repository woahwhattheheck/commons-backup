#!/usr/bin/env python3
# muhl_surface_keyb.py
# Surface KEYB01 dests FROM FILE. Does not fire. Does not host-ripple.
#   python infra/host/muhl_surface_keyb.py

from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_fab_keyb01 as fab

PKG = fab.OUT
MAGIC = fab.MAGIC

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)


def main():
    if not os.path.isfile(PKG):
        print("NEED — live %s. Git copy does not run." % PKG)
        return 1
    with open(PKG, "rb") as f:
        raw = f.read(96)
        if raw[:8] != MAGIC:
            print("REFUSE — magic %r" % raw[:8])
            return 2
        n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
        depth = struct.unpack_from("<I", raw, 24)[0]
        field = struct.unpack_from("<Q", raw, 52)[0]
        inj = struct.unpack_from("<Q", raw, 60)[0]
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        clock = struct.unpack_from("<Q", raw, 84)[0]
        size = f.seek(0, os.SEEK_END)
        L = fab.layout_keyb()
        mouths = fab.mouth_addrs(L)
        bits = {}
        for name, addr in mouths.items():
            f.seek(addr)
            b = f.read(1)
            bits[name] = (b[0] & 1) if b else None
        f.seek(ring0)
        fwd = f.read(1)
        f.seek(ring0 + cells)
        rev = f.read(1)
    print("KEYB01 SURFACE")
    print("  path", PKG)
    print("  bytes", size)
    print("  magic", MAGIC.decode("ascii"))
    print("  n_in", n_in, "n_gate", n_gate, "depth", depth, "n_wire", n_wire)
    print("  n_pos", fab.N_POS, "width", fab.WIDTH)
    print("  char_base", inj)
    print("  field_base", field)
    print("  commit_fwd", ring0, "bit", (fwd[0] & 1) if fwd else None)
    print("  commit_rev", ring0 + cells, "bit", (rev[0] & 1) if rev else None)
    print("  clock", clock)
    print("  formula addr = char_base + position * alphabet_width + char_code")
    for name in fab.MOUTH_ORDER:
        print("  mouth_%s" % name, mouths[name], "bit", bits[name])
    print("  fire_occurred NO")
    print("  commons.mno UNTOUCHED")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
