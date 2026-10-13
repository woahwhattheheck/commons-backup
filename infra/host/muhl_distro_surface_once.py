#!/usr/bin/env python3
"""host/muhl_distro_surface_once.py — surface dests FROM FILE. Die.

GIG_DL.mno + muhlnickel.mno 136450. Header dests the file publishes.
Seek+read named mouths. No inject. No re-OR. No 337. No titan. No 1GiB hash.
"""
from __future__ import annotations

import os
import struct
import sys

DISTRO = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO")
TARGETS = (
    os.path.join(DISTRO, "GIG_DL.mno"),
    os.path.join(DISTRO, "muhlnickel.mno"),
)
MAGIC = b"MUHLPKG1"
RECV = 353

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _refuse(msg):
    print("REFUSE: %s" % msg)
    print("337 NO")
    print("pulsed_78 NO")
    print("button dies")
    return 2


def main():
    argv = [a.lower() for a in sys.argv[1:]]
    if "--go" in argv or "--inject" in argv:
        return _refuse("this button surfaces")
    if 337 in [int(a) for a in sys.argv[1:] if a.lstrip("-").isdigit()]:
        return _refuse("337")

    rc = 0
    for path in TARGETS:
        print("=== SURFACE FROM FILE ===")
        print("  path %s" % path)
        if not os.path.isfile(path):
            print("  MISSING")
            rc = 1
            continue
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(0)
            buf = f.read(224)
            print("  size %d" % size)
            if len(buf) < 224 or buf[0:8] != MAGIC:
                print("  header unpublished magic %r" % buf[:8])
                rc = 1
                continue
            ans, pubplane = struct.unpack_from("<QQ", buf, 104)
            fwd, rev = struct.unpack_from("<QQ", buf, 136)
            opnd, sel = struct.unpack_from("<QQ", buf, 168)
            total, = struct.unpack_from("<Q", buf, 184)
            print("  magic MUHLPKG1")
            print("  hdr_ans %d" % ans)
            print("  hdr_pubplane %d" % pubplane)
            print("  hdr_fwd %d" % fwd)
            print("  hdr_rev %d" % rev)
            print("  hdr_opnd %d" % opnd)
            print("  hdr_sel %d" % sel)
            print("  hdr_total %d" % total)
            mouths = [
                ("hdr_ans", ans),
                ("hdr_pubplane", pubplane),
                ("hdr_fwd", fwd),
                ("hdr_rev", rev),
                ("hdr_opnd", opnd),
                ("hdr_sel", sel),
            ]
            if ans != 337:
                mouths.append(("boom_ans+1283", ans + 1283))
            mouths.append(("recv_named", RECV))
            for name, addr in mouths:
                if addr == 337:
                    print("  %s @%d SKIP 337 not fired" % (name, addr))
                    continue
                if addr < 0 or addr >= size:
                    print("  %s @%d PAST_EOF size=%d" % (name, addr, size))
                    continue
                f.seek(addr)
                raw = f.read(1)
                if len(raw) != 1:
                    print("  %s @%d SHORT" % (name, addr))
                    continue
                b = raw[0]
                print("  %s @%d byte=%d hex=%02x bits=%s" % (name, addr, b, b, format(b, "08b")))
        print("  wrote NO inject NO 337 NO")
    print("button dies")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
