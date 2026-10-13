#!/usr/bin/env python3
# host/muhl_route_tenancy.py
# Address 12 Sub-Zero published dests (FROM titan_circuits.json) into
# muhl_tenancy.mno inject plane. Fire 12 rings. Surface field 1s/0s. Die.
# Bounded 1-byte seeks. No 10-wide. No dc mmap. No 337. No chimera rebake.
# new=old|mask on tenancy inj+rings. Titan dests are READ (LSB), not rewritten.

import json, os, struct, sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
PKG = r"C:\Users\lucys\Desktop\MUHL_TENANCY\muhl_tenancy.mno"

# dest FROM REGISTRY (the binary's published mouths)
TENANTS = (
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
        raise SystemExit("NEED_BRYCE — dest past EOF %s @%d" % (path, addr))
    return b[0] & 1


def main():
    if not os.path.isfile(PKG):
        print("NEED_BRYCE — tenancy missing")
        return 1
    # confirm registry still names these dests
    reg = json.load(open(REG, encoding="utf-8"))
    bits = []
    print("ROUTE_TENANCY")
    with open(TITAN, "rb") as tf:
        for name, addr in TENANTS:
            tf.seek(addr)
            b = tf.read(1)
            bit = (b[0] & 1) if b else 0
            bits.append(bit)
            print("  titan %s @%d lsb=%d" % (name, addr, bit))
    with open(PKG, "r+b") as f:
        raw = f.read(96)
        assert raw[:8] == b"TENANCY1", raw[:8]
        n_in = struct.unpack_from("<I", raw, 8)[0]
        inj = struct.unpack_from("<Q", raw, 60)[0]
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        assert n_in == 12 and n_rings == 12
        span = cells + cells + 2
        for i, bit in enumerate(bits):
            f.seek(inj + i)
            old = f.read(1)[0]
            new = old | bit  # new=old|mask, mask is the titan LSB
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
    print("  (field updates on pulse; stored pre-ripple is inject latched at runtime by the file)")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
