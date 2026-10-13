#!/usr/bin/env python3
"""host/muhl_seed0_nway_button.py — third twin. Same inject as the mirror button. Die.

Host jobs, then die:
  (a) copy VIRGIN -> SEED0_N2 (copy the computer)
  (b) inject BOTH senses as old|mask + one bit at recv@353  (same inject_or)
  (c) surface ans@5378+select on VIRGIN, MIRROR, N2
  (d) die

Does not re-run the mirror button. Does not touch SEED0, sealed DISTRO, dc.mno, titan.
No gate-ripple. No numpy. No 337. No titan 78.
"""
from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import muhl_seed0_mirror_button as M

N2 = os.path.join(M.DISTRO, "SEED0_N2.mno")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def main():
    if "--inject" in sys.argv:
        print("REFUSE: --inject 0x01 is a wipe. Law is new=old|mask.")
        return 2
    if not os.path.isfile(M.VIRGIN) or not os.path.isfile(M.MIRROR):
        print("REFUSE: VIRGIN/MIRROR missing. Wait for MIRROR_PROOF.")
        return 2
    if os.path.getsize(M.VIRGIN) != M.TOTAL or os.path.getsize(M.MIRROR) != M.TOTAL:
        print("REFUSE: twin size")
        return 2

    shutil.copyfile(M.VIRGIN, N2)
    print("copied VIRGIN -> SEED0_N2  size %d" % os.path.getsize(N2))

    mask, _nf, _nr, _np = M.inject_or(N2, M.A, M.B)
    print("INJECT N2 only")
    print("  A,B    %d,%d  addr %d" % (M.A, M.B, M.ADDR))
    print("  mask   %s" % M.bits(mask))
    print("  recv   old|00000001")
    print("  law    new=old|mask  both senses")

    sV = M.surface(M.VIRGIN)
    sM = M.surface(M.MIRROR)
    sN = M.surface(N2)
    match = (
        sV["ans"] == sM["ans"] == sN["ans"]
        and sV["pubp"] == sM["pubp"] == sN["pubp"]
        and sV["recv"] == sM["recv"] == sN["recv"]
        and sV["at"] == sM["at"] == sN["at"]
        and sV["size"] == sM["size"] == sN["size"] == M.TOTAL
    )
    for name, s, path in (("VIRGIN", sV, M.VIRGIN), ("MIRROR", sM, M.MIRROR), ("N2", sN, N2)):
        print("%s  %s" % (name, path))
        print("  size %d  recv %s  sel %s  at %d  ans %d  pubp %d"
              % (s["size"], format(s["recv"], "08b"), s["sel"], s["at"], s["ans"], s["pubp"]))
    print("THREE_BYTES_MATCH %s" % ("y" if match else "n"))
    print("pulsed_78 NO")
    print("button dies")
    return 0 if match else 1


if __name__ == "__main__":
    raise SystemExit(main())
