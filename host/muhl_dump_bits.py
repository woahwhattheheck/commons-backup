#!/usr/bin/env python3
# host/muhl_dump_bits.py
# Bounded 1s/0s from a LIVE file. Address, print, die.
# This is the chicken-egg breaker: the binary gate cannot require bits before
# the command that dumps them. 64 bytes = 512 bits. No mmap of dc. No titan.
#   python host/muhl_dump_bits.py C:\Users\lucys\Desktop\MUHL_COMMONS\table_mail.mno
#   python host/muhl_dump_bits.py PATH --off 701 --n 64

import os, sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

FORBIDDEN = ("muhlnickel_dc.mno", "dc.mno", "titan.gguf")


def arg(flag, default=None):
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv):
        print("NEED — %s value" % flag)
        raise SystemExit(1)
    return sys.argv[i + 1]


def main():
    path = None
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a in ("--off", "--n"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        path = a
        break
    if not path:
        print("NEED_BRYCE — name a .mno")
        return 1
    path = os.path.normpath(os.path.abspath(path))
    base = os.path.basename(path).lower()
    if base in FORBIDDEN:
        print("REFUSE — not titan, not dc")
        return 2
    off = int(arg("--off", "0"))
    n = int(arg("--n", "64"))
    if n < 64:
        n = 64
    if n > 256:
        n = 256
    with open(path, "rb") as f:
        f.seek(off)
        raw = f.read(n)
    if len(raw) < 64:
        print("NEED — file shorter than 64 bytes at that off")
        return 1
    bits = "".join(format(b, "08b") for b in raw)
    print("DUMP_BITS LIVE")
    print("  path", path)
    print("  off", off, "n", len(raw), "digits", len(bits))
    # 64 groups of 8
    chunks = [bits[i:i + 8] for i in range(0, len(bits), 8)]
    for row in range(0, len(chunks), 8):
        print("  " + " ".join(chunks[row:row + 8]))
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
