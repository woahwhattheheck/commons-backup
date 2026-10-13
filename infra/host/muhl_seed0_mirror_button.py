#!/usr/bin/env python3
"""host/muhl_seed0_mirror_button.py — SEED0 mirror routing button.

Host jobs, then die:
  (a) copy the file (copy the computer)
  (b) if organ latched, re-fab a VIRGIN 8192 seed (same path as seed builder)
  (c) inject BOTH senses as old|mask + one bit at recv@353
  (d) surface ans@5378+select on BOTH
  (e) die

No gate-ripple. No dc.mno. No titan. No numpy. Sealed DISTRO is READ only.
--inject 0x01 wipe is refused. Ones only go up.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import struct
import sys

DISTRO = os.path.normpath("C:/Users/lucys/Desktop/MUHLNICKEL_DISTRO")
SEED = os.path.join(DISTRO, "SEED0.mno")
MIRROR = os.path.join(DISTRO, "SEED0_MIRROR.mno")
VIRGIN = os.path.join(DISTRO, "SEED0_VIRGIN.mno")
SEALED = os.path.join(DISTRO, "muhlnickel.mno")

FWD, REV, PUB, OPND, SEL = 288, 320, 353, 354, 370
ANS, CELLS, TOTAL = 5378, 32, 8192
LANE = 1284
PUBP = ANS + LANE
A, B = 3, 5
ADDR = A + 256 * B

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def bits(b):
    return " ".join(format(x, "08b") for x in b)


def surface(path):
    buf = open(path, "rb").read()
    sel = buf[SEL:SEL + 2]
    at = sel[0] + 256 * sel[1]
    return {
        "size": len(buf),
        "magic": buf[0:8],
        "recv": buf[PUB],
        "sel": list(sel),
        "at": at,
        "ans": buf[ANS + at],
        "pubp": buf[PUBP + at],
        "o2": buf[7951],
        "fwd16": buf[FWD:FWD + 16],
        "rev16": buf[REV:REV + 16],
    }


def fab_virgin(dst):
    """Same fabrication path as the seed builder. Offline. One-and-done. READ sealed DISTRO."""
    src = open(SEALED, "rb").read()
    if src[0:8] != b"MUHLPKG1":
        raise SystemExit("REFUSE: sealed DISTRO magic")
    if len(src) != 136450:
        raise SystemExit("REFUSE: sealed DISTRO size %d (do not smash)" % len(src))

    HDR, BODY = 224, 5378
    ANS_SRC, PUB_SRC = 5378, 70914
    O2_FWD, O2_REV, O2_CARRY, O2_PUB = 7946, 7948, 7950, 7951
    OCC, O2_RING, O2_NG = 7952, 7960, 6
    COL, COL_N = 8110, 3
    XOR, AND, OR_ = 0, 1, 3

    buf = bytearray(TOTAL)
    buf[0:BODY] = src[0:BODY]
    buf[ANS:ANS + LANE] = src[ANS_SRC:ANS_SRC + LANE]
    buf[PUBP:PUBP + LANE] = src[PUB_SRC:PUB_SRC + LANE]
    struct.pack_into("<Q", buf, 112, PUBP)
    struct.pack_into("<Q", buf, 120, LANE)
    struct.pack_into("<Q", buf, 184, TOTAL)

    ring2 = [
        (XOR, O2_FWD + 1, O2_CARRY, O2_FWD + 0),
        (XOR, O2_FWD + 0, O2_CARRY, O2_FWD + 1),
        (XOR, O2_REV + 1, O2_CARRY, O2_REV + 0),
        (XOR, O2_REV + 0, O2_CARRY, O2_REV + 1),
        (AND, O2_FWD, O2_REV, O2_CARRY),
        (OR_, O2_PUB, O2_CARRY, O2_PUB),
    ]
    for i, (op, a, b, o) in enumerate(ring2):
        struct.pack_into("<BQQQ", buf, O2_RING + i * 25, op, a, b, o)
    col = [
        (OR_, OCC + 0, OCC + 1, OCC + 2),
        (OR_, OCC + 2, OCC + 3, OCC + 2),
        (OR_, OCC + 2, O2_PUB, OCC + 4),
    ]
    for i, (op, a, b, o) in enumerate(col):
        struct.pack_into("<BQQQ", buf, COL + i * 25, op, a, b, o)

    wire, wlen = 288, 84
    h = hashlib.sha256()
    h.update(buf[0:192])
    h.update(buf[224:wire])
    h.update(b"\0" * wlen)
    h.update(buf[wire + wlen:])
    buf[192:224] = h.digest()
    open(dst, "wb").write(buf)
    return len(buf)


def inject_or(path, a, b):
    """Bounded OR. new = old | mask. Both senses. One bit at recv. Select names the address."""
    mask = bytes(((a >> i) & 1) for i in range(8)) + bytes(((b >> i) & 1) for i in range(8))
    drive = 0x01
    with open(path, "r+b") as f:
        f.seek(FWD)
        old_f = f.read(CELLS)
        f.seek(REV)
        old_r = f.read(CELLS)
        f.seek(OPND)
        old_o = f.read(16)
        f.seek(PUB)
        old_p = f.read(1)
        new_f = bytes(old_f[i] | (mask[i] if i < 16 else drive) for i in range(CELLS))
        new_r = bytes(old_r[i] | (mask[i] if i < 16 else drive) for i in range(CELLS))
        new_o = bytes(old_o[i] | mask[i] for i in range(16))
        new_p = bytes((old_p[0] | 0x01,))
        f.seek(FWD)
        f.write(new_f)
        f.seek(REV)
        f.write(new_r)
        f.seek(OPND)
        f.write(new_o)
        f.seek(SEL)
        f.write(bytes([a, b]))
        f.seek(PUB)
        f.write(new_p)
        f.flush()
        os.fsync(f.fileno())
    return mask, new_f, new_r, new_p


def main():
    if "--inject" in sys.argv:
        print("REFUSE: --inject 0x01 is a wipe. Law is new=old|mask.")
        return 2

    live = surface(SEED)
    print("SEED0 surface")
    print("  path   %s" % SEED)
    print("  size   %d" % live["size"])
    print("  magic  %s" % live["magic"])
    print("  recv   %s" % format(live["recv"], "08b"))
    print("  sel    %s addr %d" % (live["sel"], live["at"]))
    print("  ans    %d" % live["ans"])
    print("  pubp   %d" % live["pubp"])
    print("  o2pub  %s" % format(live["o2"], "08b"))

    shutil.copyfile(SEED, MIRROR)
    print("copied SEED0 -> SEED0_MIRROR  size %d" % os.path.getsize(MIRROR))

    latched = (live["recv"] == 1 and live["sel"] == [A, B] and live["ans"] == 8)
    print("latched %s" % ("y" if latched else "n"))

    if latched:
        print("organ latched — will not recompute a new OR shot. re-fab virgin.")
        n = fab_virgin(VIRGIN)
        shutil.copyfile(VIRGIN, MIRROR)
        print("fab virgin %s size %d" % (VIRGIN, n))
        print("virgin copied -> %s" % MIRROR)
        left, right = VIRGIN, MIRROR
    else:
        left, right = SEED, MIRROR

    vL = surface(left)
    vR = surface(right)
    print("VIRGIN_LEFT  recv %s sel %s ans %d" % (format(vL["recv"], "08b"), vL["sel"], vL["ans"]))
    print("VIRGIN_RIGHT recv %s sel %s ans %d" % (format(vR["recv"], "08b"), vR["sel"], vR["ans"]))

    mask, nf, nr, np = inject_or(left, A, B)
    inject_or(right, A, B)
    print("INJECT both files")
    print("  A,B    %d,%d  addr %d" % (A, B, ADDR))
    print("  mask   %s" % bits(mask))
    print("  recv   old|00000001")
    print("  law    new=old|mask  both senses")

    sL = surface(left)
    sR = surface(right)
    match = (sL["ans"] == sR["ans"] and sL["pubp"] == sR["pubp"]
             and sL["recv"] == sR["recv"] and sL["at"] == sR["at"]
             and sL["size"] == sR["size"] == TOTAL)
    print("LEFT   %s" % left)
    print("  size %d  recv %s  sel %s  at %d  ans %d  pubp %d"
          % (sL["size"], format(sL["recv"], "08b"), sL["sel"], sL["at"], sL["ans"], sL["pubp"]))
    print("RIGHT  %s" % right)
    print("  size %d  recv %s  sel %s  at %d  ans %d  pubp %d"
          % (sR["size"], format(sR["recv"], "08b"), sR["sel"], sR["at"], sR["ans"], sR["pubp"]))
    print("MATCH %s" % ("y" if match else "n"))
    print("LATCHED_HAD_TO_REFAB %s" % ("y" if latched else "n"))
    print("SEALED_DISTRO %d (read only)" % os.path.getsize(SEALED))
    print("button dies")
    return 0 if match else 1


if __name__ == "__main__":
    raise SystemExit(main())
