#!/usr/bin/env python3
# muhl_route_keyb.py
# Address one KEYB01 frame FROM FILE, OR-start the published commit, die.
# Host does not decode. Host does not clear old bits. new=old|mask.
#   python infra/host/muhl_route_keyb.py --go --text HELP
# Cite p/bryce-keyboard-addressed-fire-muhlnickel-shell-20260821-01.md

from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_fab_keyb01 as fab

PKG = fab.OUT
MAGIC = fab.MAGIC

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask.")
    raise SystemExit(2)


def arg(flag, default=None):
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv):
        print("NEED — %s value" % flag)
        raise SystemExit(1)
    return sys.argv[i + 1]


def _or_bit(f, addr, mask=0x01):
    f.seek(addr)
    old = f.read(1)
    if len(old) != 1:
        raise ValueError("NEED — dest %d missing" % addr)
    o = old[0]
    n = o | mask
    f.seek(addr)
    f.write(bytes((n,)))
    return o, n


def main():
    if "--go" not in sys.argv:
        print("NEED — python infra/host/muhl_route_keyb.py --go --text HELP")
        print("ONE frame. dests FROM FILE. then die.")
        return 1
    text = arg("--text")
    path_in = arg("--file")
    if path_in:
        with open(path_in, encoding="utf-8") as fh:
            text = fh.read()
    if text is None:
        print("NEED — --text or --file")
        return 1
    text = text.replace("\r\n", "\n")
    if "\n" in text:
        text = text.split("\n", 1)[0]
    if not os.path.isfile(PKG):
        print("NEED — live %s. Git copy does not run. Fab first." % PKG)
        return 1
    try:
        inj = fab.encode_frame(text)
    except (ValueError, UnicodeEncodeError) as e:
        print("NEED — %s" % e)
        return 1
    with open(PKG, "r+b") as f:
        raw = f.read(96)
        if raw[:8] != MAGIC:
            print("REFUSE — magic %r" % raw[:8])
            return 2
        n_in = struct.unpack_from("<I", raw, 8)[0]
        inj_base = struct.unpack_from("<Q", raw, 60)[0]
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        if n_in != fab.N_FRAME or n_rings != 1:
            print("REFUSE — header n_in/n_rings not KEYB01")
            return 2
        shots = []
        for i, bit in enumerate(inj):
            if not bit:
                continue
            addr = inj_base + i
            old, new = _or_bit(f, addr)
            shots.append(("inj", addr, old, new))
        fwd = ring0
        rev = ring0 + cells
        for tag, addr in (("fwd", fwd), ("rev", rev)):
            old, new = _or_bit(f, addr)
            shots.append((tag, addr, old, new))
        f.flush()
        os.fsync(f.fileno())
    print("KEYB01 ROUTE")
    print("  path", PKG)
    print("  text", repr(text))
    print("  char_base", inj_base)
    print("  commit_fwd", fwd)
    print("  commit_rev", rev)
    print("  shots", len(shots))
    for tag, addr, old, new in shots:
        print("  %s@%d %d->%d" % (tag, addr, old, new))
    print("  fire_occurred YES")
    print("  commons.mno UNTOUCHED")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
