#!/usr/bin/env python3
# host/muhl_surface_tenancy.py
# SURFACE dests FROM FILE on muhl_tenancy.mno. Bounded 1-byte seeks. Die.
# Does not smash. Does not fire. Does not mmap dc. Does not fire 337.
#   python host/muhl_surface_tenancy.py
from __future__ import annotations

import os
import struct
import sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

PKG = r"C:\Users\lucys\Desktop\MUHL_TENANCY\muhl_tenancy.mno"
MAGIC = b"TENANCY1"
ORGANS = ("PALF", "NEFG", "ARDR", "VSCF", "KEGN", "NMPIS", "AWCG", "DMB", "CGAT", "EAL", "MHA", "HPC")
# titan dests FROM the route button / registry. Read LSB only if --titan.
TITAN = r"C:\llm\models\titan.gguf"
TITAN_DESTS = (
    ("PALF", 93709716416),
    ("NEFG", 93709716802),
    ("ARDR", 93709727616),
    ("VSCF", 93709728614),
    ("KEGN", 93709733222),
    ("NMPIS", 93709755230),
    ("AWCG", 93709781888),
    ("DMB", 93709782657),
    ("CGAT", 93709782976),
    ("EAL", 93709785846),
    ("MHA", 93709824030),
    ("HPC", 93709884814),
)


def _bit(path, addr):
    with open(path, "rb") as f:
        f.seek(addr)
        b = f.read(1)
    if not b:
        raise SystemExit("NEED — dest past EOF %s @%d" % (path, addr))
    return b[0] & 1, b[0]


def main():
    if not os.path.isfile(PKG):
        print("NEED_BRYCE — tenancy missing")
        return 1
    with open(PKG, "rb") as f:
        raw = f.read(96)
    if raw[:8] != MAGIC:
        print("NEED — magic", raw[:8])
        return 1
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
    depth = struct.unpack_from("<I", raw, 24)[0]
    _wb, cell_base, inj_base = struct.unpack_from("<QQQ", raw, 44)
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0, clock = struct.unpack_from("<QQ", raw, 76)
    size = os.path.getsize(PKG)
    print("SURFACE_TENANCY FROM FILE")
    print("  path", PKG)
    print("  size", size)
    print("  magic TENANCY1 n_in=%s n_wire=%s n_gate=%s n_out=%s DEPTH=%s" % (
        n_in, n_wire, n_gate, n_out, depth))
    print("  n_rings=%s cells=%s ring0@%s clock@%s inj@%s field@%s" % (
        n_rings, cells, ring0, clock, inj_base, cell_base))
    span = cells + cells + 2
    lines = []
    for i, name in enumerate(ORGANS[:n_rings]):
        fwd = ring0 + i * span
        rev = fwd + cells
        carry = fwd + 2 * cells
        pub = carry + 1
        inj = inj_base + i
        fld = cell_base + i
        ck = clock + i
        fb, _ = _bit(PKG, fwd)
        rb, _ = _bit(PKG, rev)
        cb, _ = _bit(PKG, carry)
        pb, _ = _bit(PKG, pub)
        ib, _ = _bit(PKG, inj)
        db, _ = _bit(PKG, fld)
        kb, _ = _bit(PKG, ck)
        row = (
            "%s inj@%s=%s field@%s=%s fwd@%s=%s rev@%s=%s carry@%s=%s pub@%s=%s clock@%s=%s"
            % (name, inj, ib, fld, db, fwd, fb, rev, rb, carry, cb, pub, pb, ck, kb)
        )
        print(" ", row)
        lines.append(row)
    print("  fire_337=NO titan_mmap=NO dc_mmap=NO rewrite=NO")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
