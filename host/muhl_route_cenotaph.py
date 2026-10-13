#!/usr/bin/env python3
# host/muhl_route_cenotaph.py
# Record genesis events on grave_cenotaph_v1.mno. new=old|mask. Die.
# Does not smash commons / table_mail / tenancy / weather / titan / dc.
#   python host/muhl_route_cenotaph.py --go --record-genesis
from __future__ import annotations

import os
import struct
import sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask.")
    raise SystemExit(2)

PKG = r"C:\Users\lucys\Desktop\MUHL_GRAVE\grave_cenotaph_v1.mno"
MAGIC = b"CENOTPH1"
RINGS = ("ROOK", "FAILO", "KSTRM", "INGST")


def main():
    if "--go" not in sys.argv or "--record-genesis" not in sys.argv:
        print("NEED — python host/muhl_route_cenotaph.py --go --record-genesis")
        return 1
    if not os.path.isfile(PKG):
        print("NEED — fab first")
        return 1
    with open(PKG, "r+b") as f:
        raw = f.read(96)
        if raw[:8] != MAGIC:
            print("NEED — magic", raw[:8])
            return 1
        n_in = struct.unpack_from("<I", raw, 8)[0]
        inj = struct.unpack_from("<Q", raw, 60)[0]
        field = struct.unpack_from("<Q", raw, 52)[0]
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        clock = struct.unpack_from("<Q", raw, 84)[0]
        assert n_in == 4 and n_rings == 4
        span = cells + cells + 2
        mask = 0x01
        for i, name in enumerate(RINGS):
            for tag, addr in (("inj", inj + i), ("fwd", ring0 + i * span), ("rev", ring0 + i * span + cells)):
                f.seek(addr)
                old = f.read(1)[0]
                new = old | mask
                f.seek(addr)
                f.write(bytes((new,)))
                print("  %s %s@%d %d->%d" % (name, tag, addr, old, new))
        f.flush()
        os.fsync(f.fileno())
        f.seek(field)
        fld = f.read(n_in)
        print("RECORD_GENESIS field_lsbs", " ".join("%s=%d" % (RINGS[i], fld[i] & 1) for i in range(n_in)))
        print("  dests FROM FILE ring0@%d inj@%d field@%d clock@%d" % (ring0, inj, field, clock))
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
