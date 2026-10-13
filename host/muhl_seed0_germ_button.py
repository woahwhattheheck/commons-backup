#!/usr/bin/env python3
"""host/muhl_seed0_germ_button.py — smaller germ. Copy prefix through dest. Die.

Host jobs, then die:
  (a) read SEED0 (8192). Dest is the machine's: ans@6661.
  (b) copy bytes [0 : 6662] bit-exact to SEED0_GERM.mno  (dest+1)
  (c) surface ans@6661 on SEED0 and on the germ
  (d) die

Not a zip. Not a host packer. Not a shrink of SEED0 / DISTRO / dc.
Does not write titan. Does not inject. Does not fire 337. Does not pulse 78.
Does not remap 336/337. Does not delete gates on the live computers.
--go refused.
"""
from __future__ import annotations

import os
import sys

DISTRO = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO")
SEED = os.path.join(DISTRO, "SEED0.mno")
GERM = os.path.join(DISTRO, "SEED0_GERM.mno")
DC = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_DATACENTER\muhlnickel_dc.mno")
SEALED = os.path.join(DISTRO, "muhlnickel.mno")

MAGIC = b"MUHLPKG1"
SEED_SIZE = 8192
ANS_DEST = 6661
GERM_SIZE = ANS_DEST + 1
FORBIDDEN_WRITE = (
    os.path.normcase(SEED),
    os.path.normcase(SEALED),
    os.path.normcase(DC),
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _refuse(msg):
    print("REFUSE: %s" % msg)
    print("337 NO")
    print("shrunk_dc NO")
    print("button dies")
    return 2


def _surface_byte(path, addr):
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        if addr < 0 or addr >= size:
            return None, size
        f.seek(addr)
        raw = f.read(1)
    if len(raw) != 1:
        return None, size
    return raw[0], size


def main():
    argv = [a.lower() for a in sys.argv[1:]]
    if "--go" in argv:
        return _refuse("--go")
    if "--inject" in argv:
        return _refuse("--inject (this button copies + surfaces)")
    if not os.path.isfile(SEED):
        return _refuse("SEED0 missing")
    if os.path.getsize(SEED) != SEED_SIZE:
        return _refuse("SEED0 size %d (need %d)" % (os.path.getsize(SEED), SEED_SIZE))

    with open(SEED, "rb") as f:
        seed = f.read(SEED_SIZE)
    if len(seed) != SEED_SIZE:
        return _refuse("SEED0 short read")
    if seed[0:8] != MAGIC:
        return _refuse("SEED0 magic %r" % seed[0:8])

    germ = seed[0:GERM_SIZE]
    if len(germ) != GERM_SIZE:
        return _refuse("prefix short")
    if germ[0:8] != MAGIC:
        return _refuse("germ magic")
    if germ[ANS_DEST] != seed[ANS_DEST]:
        return _refuse("dest byte mismatch")

    if os.path.normcase(os.path.abspath(GERM)) in FORBIDDEN_WRITE:
        return _refuse("germ path is a live computer")

    with open(GERM, "wb") as f:
        f.write(germ)
        f.flush()
        os.fsync(f.fileno())

    seed_ans, seed_n = _surface_byte(SEED, ANS_DEST)
    germ_ans, germ_n = _surface_byte(GERM, ANS_DEST)
    seed_336, _ = _surface_byte(SEED, 336)
    germ_336, _ = _surface_byte(GERM, 336)
    seed_recv, _ = _surface_byte(SEED, 353)
    germ_recv, _ = _surface_byte(GERM, 353)

    dc_n = os.path.getsize(DC) if os.path.isfile(DC) else None
    sealed_n = os.path.getsize(SEALED) if os.path.isfile(SEALED) else None

    print("MUHL GERM")
    print("  seed   %s  %d" % (SEED, seed_n))
    print("  germ   %s  %d" % (GERM, germ_n))
    print("  dest   %d (machine)" % ANS_DEST)
    print("  seed_ans  %s  %s" % (seed_ans, format(seed_ans, "08b") if seed_ans is not None else "?"))
    print("  germ_ans  %s  %s" % (germ_ans, format(germ_ans, "08b") if germ_ans is not None else "?"))
    print("  seed_recv %s" % (format(seed_recv, "08b") if seed_recv is not None else "?"))
    print("  germ_recv %s" % (format(germ_recv, "08b") if germ_recv is not None else "?"))
    print("  seed_336  %s" % (format(seed_336, "08b") if seed_336 is not None else "?"))
    print("  germ_336  %s" % (format(germ_336, "08b") if germ_336 is not None else "?"))
    print("  remapped_336  %s" % ("NO" if seed_336 == germ_336 else "YES"))
    print("  sealed %s" % (sealed_n if sealed_n is not None else "SKIP"))
    print("  dc     %s" % (dc_n if dc_n is not None else "SKIP"))
    print("  shrunk_dc NO")
    print("  337 NO")
    print("  pulsed_78 NO")
    print("  training_started NO")
    print("button dies")
    if germ_ans != 8 or seed_ans != 8 or germ_n != GERM_SIZE or seed_n != SEED_SIZE:
        return 1
    if seed_336 != germ_336:
        return 1
    if dc_n is not None and dc_n != 99999999783:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
