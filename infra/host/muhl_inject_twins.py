#!/usr/bin/env python3
"""host/muhl_inject_twins.py — the wire is the inject mask. One button. Die.

Same mask into SEED0_MIRROR.mno and SEED0_N2.mno.
Bounded OR 3+5 both senses, one bit at recv@353 both, surface +1283 both, print both bytes, die.
If already both 8, still run (old|) and report match.

Not a TCP socket. No listen. No bind. The mask is the wire.
No gate-ripple. No dc.mno. No titan. No numpy. No 337. No titan 78.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import muhl_seed0_mirror_button as M

LEFT = os.path.join(M.DISTRO, "SEED0_MIRROR.mno")
RIGHT = os.path.join(M.DISTRO, "SEED0_N2.mno")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def skip(why):
    print("SKIP %s" % why)
    print("left    -")
    print("right   -")
    print("match   n")
    print("tcp     NO")
    print("button dies")
    return 0


def main():
    if "--inject" in sys.argv:
        print("REFUSE: --inject 0x01 is a wipe. Law is new=old|mask.")
        return 2
    if not os.path.isfile(LEFT):
        return skip("SEED0_MIRROR.mno missing")
    if not os.path.isfile(RIGHT):
        return skip("SEED0_N2.mno missing")
    if os.path.getsize(LEFT) != M.TOTAL or os.path.getsize(RIGHT) != M.TOTAL:
        return skip("twin size")

    mask, _nf, _nr, _np = M.inject_or(LEFT, M.A, M.B)
    M.inject_or(RIGHT, M.A, M.B)

    sL = M.surface(LEFT)
    sR = M.surface(RIGHT)
    left = sL["ans"]
    right = sR["ans"]
    match = (
        left == right
        and sL["pubp"] == sR["pubp"]
        and sL["recv"] == sR["recv"]
        and sL["at"] == sR["at"] == M.ADDR
        and sL["size"] == sR["size"] == M.TOTAL
    )

    print("INJECT both files  A,B %d,%d  addr %d" % (M.A, M.B, M.ADDR))
    print("  mask   %s" % M.bits(mask))
    print("  recv   old|00000001")
    print("  law    new=old|mask  both senses")
    print("  wire   inject mask  (not TCP)")
    print("LEFT   %s" % LEFT)
    print("  size %d  recv %s  sel %s  at %d  ans %d  pubp %d"
          % (sL["size"], format(sL["recv"], "08b"), sL["sel"], sL["at"], sL["ans"], sL["pubp"]))
    print("RIGHT  %s" % RIGHT)
    print("  size %d  recv %s  sel %s  at %d  ans %d  pubp %d"
          % (sR["size"], format(sR["recv"], "08b"), sR["sel"], sR["at"], sR["ans"], sR["pubp"]))
    print("left    %d" % left)
    print("right   %d" % right)
    print("match   %s" % ("y" if match else "n"))
    print("tcp     NO")
    print("button dies")
    return 0 if match else 1


if __name__ == "__main__":
    raise SystemExit(main())
