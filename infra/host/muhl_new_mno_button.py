#!/usr/bin/env python3
"""host/muhl_new_mno_button.py — new lightweight .mno. Copy + surface. Die.

Host jobs, then die:
  (a) source = SEED0_GERM 6662 if present, else SEED0 prefix through dest
  (b) copy bit-exact to NEW_MNO.mno (new name; not SEED0)
  (c) surface ans@6661
  (d) die

Copy the file, copy the computer. Additive only. Dest is the machine's.
Does not write titan. Does not inject dc. Does not shrink dc.
Does not delete gates. Does not fire 337. Does not pulse 78.
Does not overwrite SEED0 / SEED0_GERM / sealed DISTRO.
--go refused. Skip missing.
"""
from __future__ import annotations

import os
import sys

DISTRO = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO")
SEED = os.path.join(DISTRO, "SEED0.mno")
GERM = os.path.join(DISTRO, "SEED0_GERM.mno")
NEW = os.path.join(DISTRO, "NEW_MNO.mno")
SEALED = os.path.join(DISTRO, "muhlnickel.mno")
DC = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_DATACENTER\muhlnickel_dc.mno")
TITAN = os.path.normpath(r"C:\llm\models\titan.gguf")

MAGIC = b"MUHLPKG1"
SEED_SIZE = 8192
ANS_DEST = 6661
GERM_SIZE = ANS_DEST + 1
FORBIDDEN_WRITE = (
    os.path.normcase(SEED),
    os.path.normcase(GERM),
    os.path.normcase(SEALED),
    os.path.normcase(DC),
    os.path.normcase(TITAN),
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _refuse(msg):
    print("REFUSE: %s" % msg)
    print("337 NO")
    print("titan_written NO")
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


def _titan_mtime():
    if not os.path.isfile(TITAN):
        return None
    return os.path.getmtime(TITAN)


def main():
    argv = [a.lower() for a in sys.argv[1:]]
    if "--go" in argv:
        return _refuse("--go")
    if "--inject" in argv:
        return _refuse("--inject (this button copies + surfaces)")

    titan_before = _titan_mtime()

    src = None
    body = None
    if os.path.isfile(GERM) and os.path.getsize(GERM) == GERM_SIZE:
        with open(GERM, "rb") as f:
            body = f.read(GERM_SIZE)
        src = GERM
    elif os.path.isfile(SEED) and os.path.getsize(SEED) == SEED_SIZE:
        with open(SEED, "rb") as f:
            seed = f.read(SEED_SIZE)
        if len(seed) != SEED_SIZE:
            return _refuse("SEED0 short read")
        body = seed[0:GERM_SIZE]
        src = SEED
    else:
        return _refuse("SEED0_GERM and SEED0 missing")

    if body is None or len(body) != GERM_SIZE:
        return _refuse("prefix short")
    if body[0:8] != MAGIC:
        return _refuse("magic %r" % body[0:8])

    dest = os.path.abspath(NEW)
    if os.path.normcase(dest) in FORBIDDEN_WRITE:
        return _refuse("dest is a live computer")
    if os.path.normcase(dest) == os.path.normcase(os.path.abspath(SEED)):
        return _refuse("would overwrite SEED0")

    with open(dest, "wb") as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())

    ans, n = _surface_byte(dest, ANS_DEST)
    recv, _ = _surface_byte(dest, 353)
    b336, _ = _surface_byte(dest, 336)

    dc_n = os.path.getsize(DC) if os.path.isfile(DC) else None
    sealed_n = os.path.getsize(SEALED) if os.path.isfile(SEALED) else None
    seed_n = os.path.getsize(SEED) if os.path.isfile(SEED) else None
    germ_n = os.path.getsize(GERM) if os.path.isfile(GERM) else None
    titan_after = _titan_mtime()
    titan_written = "YES" if titan_before != titan_after else "NO"

    print("MUHL NEW_MNO")
    print("  src    %s" % src)
    print("  path   %s" % dest)
    print("  size   %d" % n)
    print("  dest   %d (machine)" % ANS_DEST)
    print("  ans    %s  %s" % (ans, format(ans, "08b") if ans is not None else "?"))
    print("  recv   %s" % (format(recv, "08b") if recv is not None else "SKIP"))
    print("  336    %s" % (format(b336, "08b") if b336 is not None else "SKIP"))
    print("  seed   %s" % (seed_n if seed_n is not None else "SKIP"))
    print("  germ   %s" % (germ_n if germ_n is not None else "SKIP"))
    print("  sealed %s" % (sealed_n if sealed_n is not None else "SKIP"))
    print("  dc     %s" % (dc_n if dc_n is not None else "SKIP"))
    print("  shrunk_dc NO")
    print("  titan_written %s" % titan_written)
    print("  337 NO")
    print("  pulsed_78 NO")
    print("  training_started NO")
    print("button dies")
    if ans != 8 or n != GERM_SIZE:
        return 1
    if titan_written != "NO":
        return 1
    if dc_n is not None and dc_n != 99999999783:
        return 1
    if seed_n is not None and seed_n != SEED_SIZE:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
