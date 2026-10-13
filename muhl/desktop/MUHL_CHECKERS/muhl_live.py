#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Component implementation and operation."""
import collections
import io
import os
import struct
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

REC = 25
OPS = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}
BODY_CAP = 8 * 1024 * 1024
FORBIDDEN = ("muhlnickel_dc.mno", "dc.mno", "titan.gguf")
WINDOW_CAP = 1024 * 1024


def stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _name(path):
    return os.path.basename(path).lower()


def _forbidden(path):
    name = _name(path)
    return name in FORBIDDEN or name.endswith("titan.gguf")


def _stat(path):
    return os.stat(path)


def _window(path, off, cnt):
    """Bounded seek+read. Never slurps the body. Never mmaps."""
    if cnt < 0:
        cnt = 0
    if cnt > WINDOW_CAP:
        cnt = WINDOW_CAP
    st = _stat(path)
    size = st.st_size
    if off < 0 or off >= size or cnt == 0:
        return b"", st, size
    take = min(cnt, size - off)
    with io.open(path, "rb") as f:
        f.seek(off)
        return f.read(take), st, size


def bits(bs):
    return " ".join(format(x, "08b") for x in bs)


def head(path, st, size):
    print("LIVE READ  %s" % stamp())
    print("  file    : %s" % path)
    print("  size    : %s B      records of %d: %s      remainder %d"
          % (format(size, ","), REC, format(size // REC, ","), size % REC))
    print("  mtime   : %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)))
    print("  sha256  : not computed. occupying disk is the computer.")
    print()


def show_bytes(path, off, cnt):
    if _forbidden(path):
        st = _stat(path)
        head(path, st, st.st_size)
        print("  refused. occupying disk is the computer. no body read of dc.mno / titan.")
        return 2
    b, st, size = _window(path, off, cnt)
    head(path, st, size)
    if off >= size:
        print("  offset %s sits past the current end (%s B)."
              % (format(off, ","), format(size, ",")))
        print("  Owner: 'THERES NO BUG ITS MOVING UNDER YOU' - the container grows, so an address")
        print("  past today's end is a span it will occupy. Re-read.")
        return 0
    end = off + len(b)
    print("  bytes %s .. %s as ONES AND ZEROS:" % (format(off, ","), format(end - 1, ",")))
    for i in range(0, len(b), 16):
        print("  %10s  %s" % (format(off + i, ","), bits(b[i:min(i + 16, len(b))])))
    return 0


def show_records(path, first, n):
    if _forbidden(path):
        st = _stat(path)
        head(path, st, st.st_size)
        print("  refused. occupying disk is the computer. no body read of dc.mno / titan.")
        return 2
    if n < 1:
        n = 1
    if n > 64:
        n = 64
    off = first * REC
    b, st, size = _window(path, off, n * REC)
    head(path, st, size)
    total = size // REC
    print("  records %s .. %s of %s" % (format(first, ","), format(first + n - 1, ","),
                                        format(total, ",")))
    print()
    got = len(b) // REC
    for k in range(got):
        rec = b[k * REC:(k + 1) * REC]
        op, a, bb, ou = struct.unpack("<BQQQ", rec)
        o = (first + k) * REC
        print("  record %-8s at byte %-10s" % (format(first + k, ","), format(o, ",")))
        print("      op  %s" % bits(rec[0:1]))
        print("      a   %s" % bits(rec[1:9]))
        print("      b   %s" % bits(rec[9:17]))
        print("      out %s" % bits(rec[17:25]))
        print("      -> op=%d (%s)  a=%s  b=%s  out=%s%s"
              % (op, OPS.get(op, "OUTSIDE THE 5-VALUE ALPHABET"), format(a, ","),
                 format(bb, ","), format(ou, ","),
                 "   [out == a : SELF-CLOCK]" if ou == a else ""))
        print()
    return 0


def scan(path):
    st = _stat(path)
    head(path, st, st.st_size)
    if _forbidden(path) or st.st_size > BODY_CAP:
        print("  scan refused. occupying disk is the computer. stat only. no 100GB walk.")
        return 2
    with io.open(path, "rb") as f:
        b = f.read(BODY_CAP)
    total = len(b) // REC
    ops = collections.Counter()
    selfclk = 0
    mx = [0, 0, 0]
    for k in range(total):
        op, a, bb, ou = struct.unpack_from("<BQQQ", b, k * REC)
        ops[op] += 1
        if ou == a:
            selfclk += 1
        mx[0] = max(mx[0], a); mx[1] = max(mx[1], bb); mx[2] = max(mx[2], ou)
    print("  opcode census (his alphabet: 0 nand, 1 and, 2 or, 3 xor, 4 not)")
    for k in sorted(ops):
        print("      op %-3d %-24s %s gates"
              % (k, OPS.get(k, "OUTSIDE THE ALPHABET"), format(ops[k], ",")))
    outside = sum(v for k, v in ops.items() if k not in OPS)
    print("      gates outside the alphabet : %s" % format(outside, ","))
    print()
    print("  gates whose out == a (self-clock: the out addr IS the addr read) : %s"
          % format(selfclk, ","))
    print("  widest operand   a %s   b %s   out %s"
          % (format(mx[0], ","), format(mx[1], ","), format(mx[2], ",")))
    zb = b.count(0)
    print("  zero bytes : %s of %s  (%.2f%%)  - addresses carrying nothing"
          % (format(zb, ","), format(len(b), ","), 100.0 * zb / max(1, len(b))))
    return 0


def watch(path, secs):
    st = _stat(path)
    print("LIVE READ  %s   %s B   stat only" % (stamp(), format(st.st_size, ",")))
    print("  watch is cut. occupying disk is the computer. no second slurp. no sha of the body.")
    return 2


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = sys.argv[1]
    if not os.path.exists(path):
        print("no such container: %s" % path)
        return 1
    a = sys.argv[2] if len(sys.argv) > 2 else None
    if a == "scan":
        return scan(path)
    if a == "rec":
        first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        return show_records(path, first, n)
    if a == "watch":
        return watch(path, float(sys.argv[3]) if len(sys.argv) > 3 else 5.0)
    off = int(a) if a else 0
    cnt = int(sys.argv[3]) if len(sys.argv) > 3 else 128
    return show_bytes(path, off, cnt)


if __name__ == "__main__":
    sys.exit(main())
