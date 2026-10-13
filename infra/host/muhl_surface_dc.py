#!/usr/bin/env python3
"""host/muhl_surface_dc.py — SURFACE published DC mouths. Dies.

Host = inject ∨ surface ∨ die. This button surfaces. It does not inject.
Dest is the MACHINE. Published mouths only. Not a host dest.
Never fire 337. Never light 7913. Never --go. Never mmap the 100GB body.
Never write titan. Never inject dc.

  python host/muhl_surface_dc.py
"""
from __future__ import annotations

import os
import sys

PKG = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_DATACENTER\muhlnickel_dc.mno")

# MUHL_WITNESS.md — mouths the organ already publishes. Surface. Not fire.
MOUTHS = (
    ("HEADER", 0, 8),
    ("FOLD", 224, 8),
    ("carry", 336, 1),
    ("pub", 337, 1),
    ("ring_fwd", 524288, 8),
    ("7913_pub", 524329, 1),
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if "--go" in a:
        print("GO REFUSED: surface only. No inject. No fire 337. No light 7913.")
        print("  (button dies)")
        return 2
    if not os.path.isfile(PKG):
        print("NEED_BRYCE — dc missing: %s" % PKG)
        print("  (button dies)")
        return 1
    try:
        size = os.path.getsize(PKG)
    except OSError as exc:
        print("NEED_BRYCE — stat fail: %s" % exc)
        print("  (button dies)")
        return 1
    print("SURFACE_DC")
    print("  path  %s" % PKG)
    print("  size  %s" % size)
    print("  mmap  NO")
    print("  inject  NO")
    print("  fired_337  NO")
    print("  lit_7913  NO")
    try:
        with open(PKG, "rb") as f:
            for name, off, n in MOUTHS:
                if off < 0 or off >= size:
                    print("  %s @%s  PAST_EOF" % (name, off))
                    continue
                take = n if off + n <= size else size - off
                f.seek(off)
                blob = f.read(take)
                bits = "".join(format(b, "08b") for b in blob) if blob else ""
                print("  %s @%s  n=%s  hex %s  bits %s" % (name, off, take, blob.hex(), bits))
    except OSError as exc:
        print("NEED_BRYCE — surface fail: %s" % exc)
        print("  (button dies)")
        return 1
    print("  dest  MACHINE")
    print("  (button dies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
