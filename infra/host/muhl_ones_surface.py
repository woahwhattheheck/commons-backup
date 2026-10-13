#!/usr/bin/env python3
"""host/muhl_ones_surface.py — bounded 1-count on a named .mno. Dies.

Host = surface ∨ die. No inject. No dc. No titan. No 337.
LSB-first. No numpy. No mmap of 100GB.

  python host/muhl_ones_surface.py SEED0.mno
  python host/muhl_ones_surface.py C:\\Users\\lucys\\Desktop\\MUHLNICKEL_DISTRO\\SEED0.mno
"""
from __future__ import annotations

import os
import sys

DISTRO = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO")
FORBIDDEN = ("muhlnickel_dc.mno", "dc.mno", "titan.gguf")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _path(name):
    p = os.path.expanduser(str(name))
    if not os.path.isabs(p):
        p = os.path.join(DISTRO, p)
    return os.path.normpath(p)


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if not a:
        print("NEED_BRYCE — name a .mno")
        print("  (button dies)")
        return 1
    path = _path(a[0])
    base = os.path.basename(path).lower()
    if base in FORBIDDEN:
        print("REFUSED — not dc. not titan.")
        print("  (button dies)")
        return 2
    if not os.path.isfile(path):
        print("skip missing: %s" % path)
        print("  (button dies)")
        return 0
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        print("NEED_BRYCE — read fail: %s" % exc)
        print("  (button dies)")
        return 1
    n = len(raw)
    ones = 0
    for b in raw:
        ones += bin(b).count("1")
    bits = n * 8
    zeros = bits - ones
    print("ONES")
    print("  path   %s" % path)
    print("  size   %s" % n)
    print("  bits   %s" % bits)
    print("  ones   %s" % ones)
    print("  zeros  %s" % zeros)
    print("  (button dies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
